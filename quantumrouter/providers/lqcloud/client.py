"""LQCloud API client.

Plain-``requests`` bridge to the LQCloud REST surface declared in
:mod:`config`. Mirrors the wire behavior of the upstream ``lqcloud`` SDK
(``provider/cloud_provider.py`` + ``job/job.py``) but without importing
the SDK: circuits are Qiskit-defined and arrive here already converted to
the LQCloud instruction IR (see
:mod:`quantumrouter.providers.lqcloud.backend.utils`).

The token is sent as ``X-API-Key`` (the header the live gateway accepts
for ``/api/v1/qpus``) plus a redundant ``Authorization: Bearer`` for
older deployments.

Every method raises :class:`~quantumrouter.exceptions.ProviderError`
when the cloud rejects the request or the payload is malformed.
"""

from __future__ import annotations

import json
from typing import Any, Optional

import requests

from ...exceptions import ProviderError
from . import config as endpoints


class LQCloudApiClient:
    """Token-authenticated client for the LQCloud cloud.

    Parameters
    ----------
    token:
        LQCloud token (``LQCLOUD_TOKEN`` in the environment).
    base_url:
        Server root, defaults to the official LQCloud cloud.
    """

    def __init__(self, token: str, base_url: str = endpoints.DEFAULT_URL) -> None:
        if not token:
            raise ProviderError(
                "LQCloud API token is required (set LQCLOUD_TOKEN in .env)"
            )
        self.token = token
        self.base_url = base_url.rstrip("/")

    # ------------------------------------------------------------------ #
    # Transport helper
    # ------------------------------------------------------------------ #
    def _headers(self) -> dict[str, str]:
        """Headers for every request: token + JSON content."""
        return {
            "Content-Type": "application/json",
            "User-Agent": "quantumrouter/lqcloud",
            "X-API-Key": self.token,
            "Authorization": f"Bearer {self.token}",
        }

    def _get(self, path: str, *, timeout: float = 60.0) -> Any:
        """GET ``base_url + path`` and return the parsed JSON body."""
        try:
            resp = requests.get(self.base_url + path, headers=self._headers(), timeout=timeout)
            resp.raise_for_status()
        except requests.RequestException as exc:
            raise ProviderError(
                f"Failed to communicate with LQCloud cloud "
                f"({self.base_url}{path}): {exc}"
            ) from exc
        return self._json(resp, path)

    def _post(self, path: str, payload: dict, *, timeout: float = 120.0) -> Any:
        """POST ``payload`` to ``base_url + path`` and return parsed JSON."""
        try:
            resp = requests.post(
                self.base_url + path,
                headers=self._headers(),
                json=payload,
                timeout=timeout,
            )
            resp.raise_for_status()
        except requests.RequestException as exc:
            raise ProviderError(
                f"Failed to communicate with LQCloud cloud "
                f"({self.base_url}{path}): {exc}"
            ) from exc
        return self._json(resp, path)

    @staticmethod
    def _json(resp: requests.Response, path: str) -> Any:
        """Parse a JSON body, raising ProviderError on malformed payloads."""
        try:
            return resp.json()
        except ValueError as exc:
            raise ProviderError(
                f"LQCloud returned non-JSON response from {path}: "
                f"{resp.text[:200]!r}"
            ) from exc

    # ------------------------------------------------------------------ #
    # Endpoints
    # ------------------------------------------------------------------ #
    def get_backends(self) -> list[dict]:
        """List available backends for the current token."""
        data = self._get(endpoints.QPUS)
        if isinstance(data, dict):
            data = data.get("qpus", data.get("backends", data.get("data", [])))
        if not isinstance(data, list):
            raise ProviderError(
                f"LQCloud backend discovery returned malformed payload: "
                f"{type(data).__name__}"
            )
        return [b for b in data if isinstance(b, dict)]

    def get_backend_config(self, name: str) -> Optional[dict]:
        """Return the config dict for a named backend, or ``None``."""
        for backend in self.get_backends():
            if backend.get("name") == name:
                return backend
        return None

    def submit_circuit(self, command: dict, qpu_name: str) -> dict:
        """Submit a ``run_circuit`` command and return the task envelope.

        ``command`` is the SDK-shaped ``{"action": "run_circuit", ...}``
        dict built by :meth:`LQCloudBackend._make_command` (see
        :mod:`quantumrouter.providers.lqcloud.backend.base`).
        """
        payload = {"command": command, "qpu_name": qpu_name}
        try:
            resp = requests.post(
                self.base_url + endpoints.TASKS_ASYNC,
                headers=self._headers(),
                json=payload,
                timeout=120.0,
            )
            resp.raise_for_status()
        except requests.RequestException as exc:
            # Fold the server's structured error body (when any) into the
            # message so callers see e.g. "invalid_shots" without digging.
            detail = ""
            body = getattr(getattr(exc, "response", None), "text", None)
            if body:
                try:
                    parsed = json.loads(body)
                    detail = str(parsed.get("detail") or parsed)[:300]
                except Exception:
                    detail = body[:300]
            raise ProviderError(
                f"LQCloud circuit submission failed "
                f"({self.base_url}{endpoints.TASKS_ASYNC}): {exc}"
                + (f" — {detail}" if detail else "")
            ) from exc
        return self._json(resp, endpoints.TASKS_ASYNC)

    def query_job(self, task_id: str) -> dict:
        """Fetch the current status/result envelope for one task id."""
        data = self._get(f"{endpoints.TASKS_ASYNC}/{task_id}")
        if not isinstance(data, dict):
            raise ProviderError(
                f"LQCloud task query returned malformed payload for "
                f"{task_id!r}: {type(data).__name__}"
            )
        return data
