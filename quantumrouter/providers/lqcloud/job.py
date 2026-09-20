"""Job implementation for the LQCloud provider.

:class:`LQCloudJob` adapts LQCloud's asynchronous task flow (submit a
``run_circuit`` command to ``/api/v1/tasks/async``, poll ``GET
/api/v1/tasks/async/{task_id}`` until ``status == "completed"``) to
Qiskit's :class:`JobV1` contract.  Each submitted circuit is its own
task; a multi-circuit ``run()`` yields one task id per circuit, and the
job joins them (mirroring :class:`~quantumrouter.providers.quafu.job.QuafuJob`).

The server's per-shot bitstrings (``bitstring[i]`` = outcome of classical
bit ``i``) are converted to Qiskit's hex-key convention here, so
``result.get_counts()`` and the :class:`quantumrouter.Sampler`'s memory
reader both see standard Qiskit data.
"""

from __future__ import annotations

import time
from typing import Any

from qiskit.providers import JobStatus, JobV1
from qiskit.result import Result

from .client import LQCloudApiClient
from .backend.utils import ir_counts_to_qiskit, ir_memory_to_qiskit

#: Polling ceiling (seconds) for result(). ``None`` means wait forever.
#: LQCloud tasks always reach a terminal status ("completed" / "failed" /
#: "cancelled"), so the timeout only guards against a genuinely stuck
#: server or a very long queue.
DEFAULT_RESULT_TIMEOUT: float | None = 300.0

#: Terminal task statuses from the LQCloud server.
_COMPLETED = "completed"
_FAILED = "failed"
_CANCELLED = "cancelled"


class LQCloudJob(JobV1):
    """A job executing on the LQCloud cloud, one task per circuit."""

    def __init__(
        self,
        backend: Any,
        task_ids: list[str],
        api_client: LQCloudApiClient,
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
        raise NotImplementedError("LQCloud cloud does not support job cancel")

    def status(self) -> JobStatus:
        """Map LQCloud task statuses onto Qiskit's :class:`JobStatus`."""
        statuses = [self._api_client.query_job(tid).get("status") for tid in self._task_ids]
        if all(s == _COMPLETED for s in statuses):
            return JobStatus.DONE
        if any(s in (_FAILED, _CANCELLED) for s in statuses):
            return JobStatus.ERROR
        return JobStatus.RUNNING if any(s in ("running", "queued") for s in statuses) else JobStatus.QUEUED

    def result(self, timeout: float | None = DEFAULT_RESULT_TIMEOUT) -> Result:
        """Poll until all tasks complete, then return a Qiskit :class:`Result`.

        Raises
        ------
        Exception
            On task failure/cancellation or when the poll exceeds
            ``timeout`` seconds.
        """
        deadline = None if timeout is None else time.monotonic() + timeout
        envelopes: list[dict] = []
        while True:
            envelopes = [
                self._api_client.query_job(tid) for tid in self._task_ids
            ]
            statuses = [e.get("status") for e in envelopes]
            if all(s == _COMPLETED for s in statuses):
                break
            failed = [
                (e.get("task_id"), e.get("status"), e.get("error"), e.get("error_type"))
                for e in envelopes
                if e.get("status") in (_FAILED, _CANCELLED)
            ]
            if failed:
                task_id, status, error, error_type = failed[0]
                raise Exception(
                    f"LQCloud task {task_id} {status}: {error or 'unknown error'}"
                    f"{f' ({error_type})' if error_type else ''}"
                )
            if deadline is not None and time.monotonic() >= deadline:
                raise Exception(
                    f"Waiting for LQCloud task(s) {self._task_ids} timed out "
                    f"after {timeout:g}s. "
                    "If the queue is long, pass a larger timeout (e.g. result(timeout=None))."
                )
            time.sleep(1)

        results = []
        for env in envelopes:
            raw = env.get("result")
            if not isinstance(raw, dict):
                raise Exception(
                    f"LQCloud task {env.get('task_id')} completed without a "
                    f"result payload: {env!r}"
                )
            shots = int(raw.get("shots") or self._shots)
            memory = ir_memory_to_qiskit(raw.get("memory") or [])
            counts = ir_counts_to_qiskit(raw.get("counts") or {})
            # The server always echoes both ``counts`` and ``memory`` for
            # result_format="memory"; if only one came back, derive the other.
            if memory and not counts:
                for key in memory:
                    counts[key] = counts.get(key, 0) + 1
            if counts and not memory:
                for key, cnt in counts.items():
                    memory.extend([key] * cnt)
            results.append(
                {
                    "shots": shots,
                    "success": bool(raw.get("success", True)),
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
