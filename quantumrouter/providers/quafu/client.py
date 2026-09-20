"""Quafu API client.

Plain-``requests`` bridge to the Quafu REST surface declared in
:mod:`config`. Mirrors the wire behavior of upstream pyquafu
(``quafu/tasks/tasks.py`` + ``quafu/users/userapi.py``) but without
importing the upstream package or its bundled circuit/simulator code:
circuits are Qiskit-defined and travel here already converted to
OpenQASM 2 text (see :mod:`quantumrouter.providers.quafu.backend.utils`).

Every method raises :class:`~quantumrouter.exceptions.ProviderError`
when the cloud rejects the request, mirroring upstream's
``ClientWrapper`` / ``validate_server_resp`` behaviour.

The token is sent as the ``api_token`` form header exactly like
upstream ``User.api_token``.
"""

from __future__ import annotations

import json
import re
from typing import Optional
from urllib.parse import urlencode

import requests

from ...exceptions import ProviderError
from . import config as endpoints


class QuafuApiClient:
    """Token-authenticated client for the Quafu cloud.

    Parameters
    ----------
    token:
        Quafu API token (``QUANFU_TOKEN`` in the environment).
    base_url:
        Server root, defaults to the official Quafu cloud.
    """

    def __init__(self, token: str, base_url: str = endpoints.BASE_URL) -> None:
        if not token:
            raise ProviderError(
                "Quafu API token is required (set QUANFU_TOKEN in .env)"
            )
        self.token = token
        self.base_url = base_url.rstrip("/") + "/"

    # ------------------------------------------------------------------ #
    # Transport helper
    # ------------------------------------------------------------------ #
    def _post(self, path: str, data: dict) -> dict:
        """POST form-encoded data, mirroring upstream's request shape."""
        headers = {
            "Content-Type": "application/x-www-form-urlencoded;charset=UTF-8",
            "api_token": self.token,
        }
        # Upstream url-encodes by hand and un-escapes single quotes because
        # the server expects them raw in OpenQASM text (e.g. gate params).
        body = urlencode(data)
        body = body.replace("%27", "'")
        try:
            resp = requests.post(
                self.base_url + path, headers=headers, data=body, timeout=60
            )
            resp.raise_for_status()
        except requests.RequestException as exc:
            raise ProviderError(
                f"Failed to communicate with Quafu cloud "
                f"({self.base_url}{path}): {exc}"
            ) from exc
        try:
            payload = resp.json()
        except ValueError as exc:
            raise ProviderError(
                f"Quafu returned non-JSON response: {resp.text[:200]!r}"
            ) from exc
        if not isinstance(payload, dict) or not payload.get("ok", True):
            msg = payload.get("message") if isinstance(payload, dict) else None
            raise ProviderError(f"Quafu request failed: code={payload.get('status')}, msg={msg}")
        return payload

    # ------------------------------------------------------------------ #
    # Endpoints
    # ------------------------------------------------------------------ #
    def get_backends(self) -> list[dict]:
        """List available backends for the current token."""
        payload = self._post(endpoints.BACKENDS, data={})
        data = payload.get("data")
        if isinstance(data, str):
            data = json.loads(data) if data else []
        return data or []

    def submit_job(
        self,
        circuits: list[str],
        *,
        shots: int = 1024,
        qubits: Optional[int] = None,
        system_id: int = 0,
        compile: bool = True,  # noqa: A002  # pylint: disable=redefined-builtin
        priority: int = 2,
        task_name: str = "",
        runtime_job_id: str = "",
    ) -> list[str]:
        """Submit each OpenQASM 2 circuit as its own task.

        Returns the assigned task ids, one per circuit, in order.
        """
        task_ids: list[str] = []
        for qasm in circuits:
            data = {
                "qtasm": qasm,
                "shots": shots,
                "qubits": qubits if qubits is not None else _qasm_qubit_count(qasm),
                "scan": 0,
                "tomo": 0,
                "selected_server": system_id,
                "compile": int(compile),
                "priority": priority,
                "task_name": task_name,
                "pyquafu_version": "0.4.5",
                "runtime_job_id": runtime_job_id,
            }
            payload = self._post(endpoints.EXEC_ASYNC, data)
            task_ids.append(str(payload["task_id"]))
        return task_ids

    def query_job(self, task_ids: list[str]) -> list[dict]:
        """Recall the result dicts for previously submitted task ids."""
        results: list[dict] = []
        for task_id in task_ids:
            payload = self._post(
                endpoints.EXEC_RECALL, data={"task_id": task_id}
            )
            results.append(payload)
        return results


# ---------------------------------------------------------------------- #
# Parsing helpers (exposed for reuse by the job layer and unit tests)
# ---------------------------------------------------------------------- #
_QREG_RE = re.compile(r"qreg\s+q\[(\d+)\];")
_MEASURE_RE = re.compile(r"measure\s+q\[(\d+)\]\s*->\s*c\[(\d+)\];")


def _qasm_qubit_count(qasm: str) -> int:
    """Return the declared width ``qreg q[N]`` of an OpenQASM 2 circuit."""
    match = _QREG_RE.search(qasm or "")
    return int(match.group(1)) if match else 0


def _parse_measures(qasm: str) -> list[tuple[int, int]]:
    """Return ``(qubit, clbit)`` pairs of each measure statement, in order.

    Mirrors upstream ``ExecResult``'s use of the returned (transpiled)
    OpenQASM to find which physical qubit feeds each classical bit.
    """
    if not qasm:
        return []
    return [(int(q), int(c)) for q, c in _MEASURE_RE.findall(qasm)]


def _res_to_counts(res: Optional[str], measures: list[tuple[int, int]]) -> dict:
    """Convert a Quafu ``res`` string to qiskit-style hex counts.

    Quafu's ``res`` is a JSON string of ``{bitstring: count}`` where
    ``bitstring[i]`` is the outcome of the i-th measure statement (=
    classical bit ``measures[i][1]``, verified empirically against
    ScQ-Sim10). Qiskit keys a ``Result`` count by an integer whose bit
    ``j`` is classical bit ``j``'s outcome, so

        k = sum(1 << clbit_i  for i where bitstring[i] == '1')

    ``measures`` may be empty when no OpenQASM came back; then the
    server already returned positions in clbit order and the bitstring
    is used verbatim.
    """
    if not res:
        return {}
    try:
        raw = json.loads(res)
    except json.JSONDecodeError:
        # Upstream tolerates a handful of malformed shapes; be defensive.
        raw = {}
    if not isinstance(raw, dict):
        raw = {}
    counts: dict = {}
    for bitstring, count in raw.items():
        if not isinstance(bitstring, str):
            continue
        k = 0
        for pos, ch in enumerate(bitstring):
            if ch == "1":
                clbit = measures[pos][1] if pos < len(measures) else pos
                k |= 1 << clbit
        key = hex(k)
        counts[key] = counts.get(key, 0) + int(count)
    return counts


def _counts_to_memory(counts: dict) -> list[str]:
    """Expand hex counts into a per-shot hex memory list (qiskit format)."""
    return [key for key, cnt in counts.items() for _ in range(int(cnt))]
