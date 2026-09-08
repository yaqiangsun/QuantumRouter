"""WuYue (Mobile Cloud Quantum) API client.
Wrap official wuyue.plugin.runner.Runner, strip all low-level Ecloud HTTP/Transport/sign logic.
ALL computation requests go to remote WuYue cloud cluster via Runner.run(), NO local Backend local simulation.
Only do WuYue vendor parameter mapping & response wrapping; raw AK/SK HTTP request delegated to inner WuyueClient inside Runner.
All public methods match WuYuenApiClient interface for QuantumRouter vendor interchange.
"""
from __future__ import annotations
from typing import List, Dict, Optional, Union
from enum import Enum
from wuyue.plugin.runner import Runner
from wuyue.plugin.model import QueryTaskInfoResponse


class WuYueQuantumLanguage(Enum):
    QCIS = "qcis"
    OPENQASM2 = "openqasm2"
    OPENQASM3 = "openqasm3"


class WuYueApiClient:
    """
    Standardized high-level client for WuYue mobile quantum cloud, compatible with QuantumRouter provider layer.
    All job submission use Runner.run() to dispatch task to REMOTE cloud server, no local amplitude simulation.
    All network signature, http transport, request body assembly encapsulated inside Runner -> WuyueClient.

    Params
    ------
    access_key: Mobile cloud Ecloud AccessKey ID
    secret_key: Mobile cloud Ecloud AccessKey Secret
    auto_retry: enable http auto retry for WuyueClient inner http client
    endpoint: custom cloud platform api endpoint, None = official default
    """
    def __init__(
        self,
        access_key: str,
        secret_key: str,
        auto_retry: bool = False,
        endpoint: Optional[str] = None
    ) -> None:
        self.access_key = access_key
        self.secret_key = secret_key
        self._runner = Runner(
            access_key=access_key,
            secret_key=secret_key,
            auto_retry=auto_retry,
            endpoint=endpoint
        )

    def get_backends(self) -> List[dict]:
        """Get all available remote simulator & physical QPU devices for current user.
        Temporary static device list since WuyueClient has no device-list http API yet.
        """
        # 云端设备
        device_list = [
            {
                "code": "WuYue-QPUSim-FullAmpSim",
                "name": "WuYue-QPUSim-FullAmpSim",
                "simulator": True,
                "n_qubits": 16,
                "description": "Cloud full amplitude simulator",
                "labels": '0'
            },
            {
                "code": "WuYue-QPUSim-SingleAmpSim",
                "name": "WuYue-QPUSim-SingleAmpSim",
                "simulator": True,
                "n_qubits": 32,
                "description": "Cloud single amplitude simulator",
                "labels": '0'
            },
            {
                "code": "WuYue-QPU-002-V6", # 五岳2号
                "name": "WuYue-QPU-002-V6",
                "simulator": False,
                "n_qubits": 12,
                "description": "12-qubit real physical quantum chip",
                "labels": '1'
            },
            {
                "code": "WuYue-QPU-Shishan-002", # 狮山2号
                "name": "WuYue-QPU-Shishan-002",
                "simulator": False,
                "n_qubits": 19,
                "description": "19-qubit real physical quantum chip",
                "labels": '1'
            }
        ]
        return device_list


    def submit_job(
        self,
        circuits: List[str],
        machine: str,
        *,
        shots: int = 1024,
        timeout: int = 100,
        **extra_args
    ) -> List[str]:
        """Batch submit raw circuit text to REMOTE WuYue cloud cluster, return task_id list."""
        task_ids = []
        for circ_text in circuits:
            qubit_count = circ_text.num_qubits
            print("[INFO] CLIENT.py----qubit_count:", qubit_count)
            # 传入文本线路
            run_res = self._runner.run(
                qc=circ_text,
                device_id=machine,
                qubits=qubit_count,
                shots=shots,
                timeout=timeout,
                **extra_args
            )
            task_ids.append(run_res.task_id)
        return task_ids

    def query_job(self, task_ids: List[str]) -> List[dict]:
        """Batch query remote cloud task status, counts, probability & amplitude results."""
        print(f"[INFO] WuYueClient INTO query_job task_ids={task_ids}")
        result_set = []
        for tid in task_ids:
            resp: QueryTaskInfoResponse = self._runner.wuyue_client.query_task_info(tid)
            if resp.code == 1:
                result_set.append(vars(resp.data))
            else:
                result_set.append({
                    "task_id": tid,
                    "success": False,
                    "error_code": resp.error_code,
                    "message": resp.msg
                })
        print(f"[INFO][INFO] WuYueClient OUT query_job result {result_set}")
        return result_set

    def run_circuit_object(self, qc, device_id: str, shots: int = 1024, timeout: int = 100, qubits: int = None, **kwargs):
        return self._runner.run(
            qc=qc,
            device_id=device_id,
            shots=shots,
            timeout=timeout,
            qubits=qubits,
            **kwargs
        )
