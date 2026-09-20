"""Job implementation for the WuYue provider.

:class:`WuYueJob` adapts WuYue's asynchronous task flow (submit a circuit
to ``/sdk/submit``, poll ``GET /sdk/info?taskId=...`` until
``taskStatus`` is 5 (success) / 6 (failure)) to Qiskit's :class:`JobV1`
contract.  Each submitted circuit is its own task; a multi-circuit
``run()`` yields one task id per circuit and the job joins them
(mirroring :class:`~quantumrouter.providers.quafu.job.QuafuJob`).

The server's ``outCounts`` is a JSON string of ``{bitstring: count}``
where ``bitstring[i]`` is the outcome of classical bit ``i`` (verified
empirically, 2026-09).  That is exactly Qiskit's convention, so the hex
key is ``sum(1 << i)`` over set bits — no measurement-layout remap is
needed (in contrast with Quafu).
"""

from __future__ import annotations

import ast
import json
import time
from typing import Any

from qiskit.providers import JobStatus, JobV1
from qiskit.result import Result

from .client import WuYueApiClient

#: Polling ceiling (seconds) for ``result()``. ``None`` means wait forever.
#: WuYue tasks always reach a terminal status (5 / 6), so the timeout only
#: guards against a genuinely stuck server or a very long queue.
DEFAULT_RESULT_TIMEOUT: float | None = 300.0

#: Terminal task statuses from the WuYue server.
_STATUS_SUCCESS = 5
_STATUS_FAILED = 6


class WuYueJob(JobV1):
    """A job executing on the WuYue cloud, one task per circuit."""

    def __init__(
        self,
        backend: Any,
        task_ids: list[str],
        api_client: WuYueApiClient,
        shots: int = 1024,
        **metadata: Any,
    ) -> None:
        """Store the task ids and a reference to the API client."""
        self._backend_obj = backend
        self._task_ids = list(task_ids)
        self._api_client = api_client
        self._shots = shots
        self._extra = metadata
        super().__init__(backend=backend, job_id=",".join(self._task_ids))

    # ------------------------------------------------------------------ #
    # JobV1 contract
    # ------------------------------------------------------------------ #
    def submit(self):
        """Job was already submitted when created; nothing to do."""
        return self

    def cancel(self):
        raise NotImplementedError("WuYue cloud does not support job cancel")

    def status(self) -> JobStatus:
        """Map WuYue task statuses onto Qiskit's :class:`JobStatus`."""
        data = self._api_client.query_job(self._task_ids)
        codes = [item.get("task_status") for item in data]
        if all(code == _STATUS_SUCCESS for code in codes):
            return JobStatus.DONE
        if any(code == _STATUS_FAILED for code in codes):
            return JobStatus.ERROR
        return JobStatus.RUNNING if any(code is not None for code in codes) else JobStatus.QUEUED

    def result(self, timeout: float | None = DEFAULT_RESULT_TIMEOUT) -> Result:
        """Poll until all tasks complete, then return a Qiskit :class:`Result`.

        Raises
        ------
        Exception
            On task failure (status 6) or when the poll exceeds
            ``timeout`` seconds.
        """
        deadline = None if timeout is None else time.monotonic() + timeout
        data: list[dict] = []
        while True:
            data = self._api_client.query_job(self._task_ids)
            codes = [item.get("task_status") for item in data]
            if all(code == _STATUS_SUCCESS for code in codes):
                break
            failed = [item for item in data if item.get("task_status") == _STATUS_FAILED]
            if failed:
                raise Exception(
                    f"WuYue task(s) {self._task_ids} ended with status "
                    f"{_STATUS_FAILED}: {(failed[0].get('error') or 'server error')}"
                )
            if deadline is not None and time.monotonic() >= deadline:
                raise Exception(
                    f"Waiting for WuYue task(s) {self._task_ids} timed out "
                    f"after {timeout:g}s. "
                    "If the queue is long, pass a larger timeout (e.g. result(timeout=None))."
                )
            time.sleep(1)

        results = []
        for item in data:
            shots = self._shots
            counts = _counts_to_hex(item.get("out_counts"), item.get("out_data"))
            memory = _counts_to_memory(counts)
            results.append(
                {
                    "shots": shots,
                    "success": item.get("success", True),
                    "data": {"counts": counts, "memory": memory},
                }
            )

        backend_name = self._backend_obj.configuration.backend_name
        return Result.from_dict(
            {
                "backend_name": backend_name,
                "backend_version": "1.0",
                "qobj_id": str(id(self._job_id)),
                "job_id": self._job_id,
                "success": True,
                "status": JobStatus.DONE,
                "results": results,
            }
        )


# ---------------------------------------------------------------------- #
# Parsing helpers (exposed for reuse by tests)
# ---------------------------------------------------------------------- #
def _counts_to_hex(out_counts: Any, out_data: Any) -> dict[str, int]:
    """Convert WuYue's ``{bitstring: count}`` into qiskit hex counts.

    ``bitstring[i]`` = outcome of classical bit ``i``, so the qiskit key is
    ``hex(sum(1 << i for i where bitstring[i] == '1'))``.

    ``outCounts`` is a JSON string (``{"00":"506","11":"518"}``) on the
    live cloud; ``outData`` is a python-dict repr (``{'11': 518, ...}``)
    that some builds return instead.  Parse whichever is present.
    """
    raw = out_counts or out_data
    if raw is None:
        return {}
    if isinstance(raw, dict):  # already parsed
        parsed = raw
    elif isinstance(raw, str):
        text = raw.strip()
        try:
            parsed = json.loads(text)
        except json.JSONDecodeError:
            # Python-repr fallback (the SDK parses it with literal_eval):
            # {'11': 518, '00': 506}
            try:
                parsed = ast.literal_eval(text)
            except (SyntaxError, ValueError):
                parsed = {}
    else:
        parsed = {}

    counts: dict[str, int] = {}
    if not isinstance(parsed, dict):
        return counts
    for bitstring, count in parsed.items():
        if not isinstance(bitstring, str):
            continue
        k = 0
        for i, ch in enumerate(bitstring):
            if ch == "1":
                k |= 1 << i
        counts[hex(k)] = counts.get(hex(k), 0) + int(count or 0)
    return counts


def _counts_to_memory(counts: dict[str, int]) -> list[str]:
    """Expand hex counts into a per-shot hex memory list (qiskit format)."""
    return [key for key, cnt in counts.items() for _ in range(int(cnt))]
