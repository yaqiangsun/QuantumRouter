"""Job implementation for the Quafu provider.

:class:`QuafuJob` adapts Quafu's asynchronous submit/recall (task id,
poll until ``status == 2``) to Qiskit's :class:`JobV1` contract so the
result can be handed to ``backend.run(...).result()`` and consumed by
:class:`quantumrouter.sampler.Sampler` (per-shot ``memory`` + hex
``counts``). Mirror of :class:`LingYunJob` / :class:`WuYueJob`.
"""

from __future__ import annotations

import time
from typing import Any

from qiskit.providers import JobV1, JobStatus
from qiskit.result import Result

from .client import QuafuApiClient, _counts_to_memory, _parse_measures, _res_to_counts

# Polling ceiling (seconds) for result(). ``None`` means wait forever.
# Quafu returns ``status in (3, 4)`` for canceled / failed tasks so the
# wait loop always terminates on failure; this timeout only guards
# against a genuinely stuck server.
DEFAULT_RESULT_TIMEOUT: float | None = 300.0

# Quafu task status codes, from upstream ``ExecResult`` status_map.
_STATUS_COMPLETED = 2
_STATUS_FAILED = 4
_STATUS_CANCELED = 3


class QuafuJob(JobV1):
    """A job executing on the Quafu cloud, realized as one task per circuit."""

    def __init__(
        self,
        backend: Any,
        task_ids: list[str],
        api_client: QuafuApiClient,
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
        raise NotImplementedError("Quafu cloud does not support job cancel")

    def status(self) -> JobStatus:
        """Map Quafu task statuses onto Qiskit's :class:`JobStatus`."""
        data = self._api_client.query_job(self._task_ids)
        codes = [item.get("status", 0) for item in data]
        if all(code == _STATUS_COMPLETED for code in codes):
            return JobStatus.DONE
        if any(code in (_STATUS_FAILED, _STATUS_CANCELED) for code in codes):
            return JobStatus.ERROR
        return JobStatus.RUNNING if any(code == 1 for code in codes) else JobStatus.QUEUED

    def result(self, timeout: float | None = DEFAULT_RESULT_TIMEOUT) -> Result:
        """Poll until all tasks complete, then return a qiskit :class:`Result`.

        Raises
        ------
        Exception
            On task failure (status 3/4) or when the poll exceeds
            ``timeout`` seconds.
        """
        deadline = None if timeout is None else time.monotonic() + timeout
        while True:
            data = self._api_client.query_job(self._task_ids)
            codes = [item.get("status", 0) for item in data]
            if all(code == _STATUS_COMPLETED for code in codes):
                break
            failed = [c for c in codes if c in (_STATUS_FAILED, _STATUS_CANCELED)]
            if failed:
                raise Exception(
                    f"Quafu task(s) {self._task_ids} ended with status {failed}: "
                    "the circuit may use unsupported gates or fail server-side."
                )
            if deadline is not None and time.monotonic() >= deadline:
                raise Exception(
                    f"Waiting for Quafu task(s) {self._task_ids} timed out "
                    f"after {timeout:g}s. "
                    "If the queue is long, pass a larger timeout (e.g. result(timeout=None))."
                )
            time.sleep(1)

        results = []
        for item in data:
            shots = self._shots
            measures = _parse_measures(item.get("openqasm") or "")
            counts = _res_to_counts(item.get("res"), measures)
            memory = _counts_to_memory(counts)
            results.append(
                {
                    "shots": shots,
                    "success": True,
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
