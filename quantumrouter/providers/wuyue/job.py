
from __future__ import annotations
import time
from typing import List, Dict, Any
from wuyue.plugin.result import Result as WuYueRawResult
from qiskit.result import Result
from qiskit.providers import JobStatus, JobV1

class WuYueJob(JobV1):
    def __init__(
        self,
        backend_inst,
        task_id_list: List[str],
        api_client,
        shots: int,
        readout_calibration: bool,
        raw_result_list: List[WuYueRawResult],
        **kwargs
    ):
        # 避免和backend循环导入
        from .backend.base import WuYueBackend
        backend_inst: WuYueBackend
        combined_job_id = ",".join(task_id_list)
        super().__init__(backend=backend_inst, job_id=combined_job_id)

        self._backend_obj = backend_inst
        self._task_ids = task_id_list
        self._api_client = api_client
        self._shots = shots
        self._readout_cal = readout_calibration
        self._extra_args = kwargs
        self._raw_results: List[WuYueRawResult] = raw_result_list
        self._cached_qiskit_result: Result | None = None

    def submit(self):
        """JobV1 强制抽象方法，本任务已同步提交完成，无需二次提交"""
        return self

    def job_id(self) -> str:
        return self._job_id

    
    def status(self) -> JobStatus:
        # task_ids = self._job_id.split(',')
        data = self._api_client.query_job(self._task_ids)
        ld = len(data)

        if ld == len(self._task_ids):
            return JobStatus.DONE
        if ld > 0:
            return JobStatus.RUNNING
        return JobStatus.QUEUED


    def result(self, timeout=None, wait=2) -> Result:
        """Return Qiskit Result"""
        task_ids = self._job_id.split(',')
        while True:
            status = self.status()
            if status == JobStatus.DONE:
                break
            time.sleep(wait)

        results = []
        for raw_res in self._raw_results:
            shots = self._shots
            counts = raw_res._counts
            memory_list = list(counts.keys())
            results.append({
                'shots': shots,
                'success': raw_res._success,
                'data': {
                    'counts': counts,
                    'memory': memory_list
                }
            })
        print("[INFO] WuYueJob.result() returning Qiskit Result object with results: ", results)

        backend_name = self._backend_obj.configuration.backend_name
        return Result.from_dict({
            "backend_name": backend_name,
            "backend_version": "1.0",
            "qobj_id": id(self._job_id),
            "job_id": self._job_id,
            "success": True,
            'status': JobStatus.DONE,
            "results": results,
        })



    def cancel(self):
        raise NotImplementedError("WuYue cloud does not support cancel task")

    def get_counts(self):
        return self.result().results[0]["counts"] if self.result().results else {}
