"""WuYue (Mobile Cloud Quantum) API client.
Wrap official wuyue.plugin.runner.Runner, strip all low-level Ecloud HTTP/Transport/sign logic.
ALL computation requests go to remote WuYue cloud cluster via Runner.run(), NO local Backend local simulation.
Only do WuYue vendor parameter mapping & response wrapping; raw AK/SK HTTP request delegated to inner WuyueClient inside Runner.
All public methods match WuYuenApiClient interface for QuantumRouter vendor interchange.
"""
from __future__ import annotations
import json
import json
from typing import List, Dict, Optional, Union, Any
from enum import Enum
import traceback
import requests
from wuyue.plugin.runner import Runner
from wuyue.plugin.model import QueryTaskInfoResponse
from wuyue.plugin.ecloud.request import ApiParams, Query
from wuyue.plugin.ecloud.config import RuntimeConfig
from wuyue.plugin.ecloud.utils import sanitize_for_serialization
from wuyue.plugin.ecloud.errors import ServerResponseException



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

        self._ENGINE_LIST_API_PATH = "/api/openapi/wyqcloud/task/engine/list"


    def _fetch_all_engines(self) -> List[dict]:
        try:
            api_params = ApiParams(
                action="listEngine",
                protocol="http",
                uri=self._ENGINE_LIST_API_PATH,
                method="GET",
                content_type=""
            )
            raw_json = None

            try:
                resp = self._runner.wuyue_client.api_client.excute(api_params, None, QueryTaskInfoResponse)
                print(f"[INFO] WuYueClient _fetch_all_engines dto resp: {resp}")
                if resp.code == 1:
                    raw_json = {"code": resp.code, "body": resp.data}

            except ServerResponseException as parse_err:
                raw_body_str = None
                # 常见SDK存储响应体的字段名，匹配
                candidate_fields = ["body", "response", "response_text", "response_body", "raw", "raw_body"]
                for field in candidate_fields:
                    if field in parse_err.__dict__ and parse_err.__dict__[field]:
                        raw_body_str = parse_err.__dict__[field]
                        break

                if raw_body_str:
                    try:
                        raw_json = json.loads(raw_body_str)
                    except json.JSONDecodeError as json_e:
                        print(f"[WARN] Raw body is not valid json: {raw_body_str}, err={json_e}")
                else:
                    print("[WARN] Cannot find raw http body field in ServerResponseException")

            if raw_json is None:
                print("[WARN] Engine list api get no valid response data")
                return []
            if raw_json.get("code") != 1:
                print(f"[WARN] Fetch engine list failed, code={raw_json.get('code')}, msg={raw_json.get('msg')}")
                return []

            raw_engine_body = raw_json.get("body", [])
            return raw_engine_body

        except Exception as e:
            print(f"[ERROR] Exception occurred when fetching engine resource: {str(e)}")
            traceback.print_exc()
            return []


    def get_backends(self) -> List[dict]:
        """
        Get all available remote simulator & physical QPU devices for current user.
        Real-time fetch online hardware resource via abstract internal engine fetch method,
        normalize raw cloud data to unified QuantumRouter backend dict format.
        """
        # Only call semantic abstract method, NO hardcode url/api path anywhere
        raw_engine_data_list = self._fetch_all_engines()
        print("[INFO] client.py get_backends raw_engine_data_list: ", raw_engine_data_list, len(raw_engine_data_list))
        standardized_backend_list: List[dict] = []

        for engine_item in raw_engine_data_list:
            # Filter only online devices (status=1 online, 0 under maintenance)
            device_status = engine_item.get("status", 0)
            if device_status != 1:
                continue

            dev_code = engine_item.get("deviceId", "")
            dev_display_name = engine_item.get("engName", "")
            qubit_count = engine_item.get("bits", 0)

            queue_task_count = engine_item.get("engQueueTaskNum", 0)

            # Distinguish simulator / physical quantum chip
            is_sim_device = "Sim" in dev_code or "Sim" in dev_display_name
            dev_description = f"{dev_display_name}, pending queue tasks: {queue_task_count}"
            # Keep labels field consistent with original static hardcode data
            label_tag = "0" if is_sim_device else "1"

            backend_normalized_info = {
                "code": dev_code,
                "name": dev_display_name,
                "simulator": is_sim_device,
                "n_qubits": qubit_count,
                "description": dev_description,
                "labels": label_tag,
            }
            standardized_backend_list.append(backend_normalized_info)

        return standardized_backend_list

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
        target_qubit_num = extra_args.pop("qubits", 0)
        for circ_text in circuits:
            print("[INFO] CLIENT.py----qubit_count:", target_qubit_num)
            run_res = self._runner.run(
                qc=circ_text,
                device_id=machine,
                qubits=target_qubit_num,
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
        print(f"[INFO] WuYueClient OUT query_job result {result_set}")
        return result_set

    def run_circuit_object(self, qc, device_id: str, shots: int = 1024, timeout: int = 100, qubits: int = None, **kwargs):
        return self._runner.run(
            qc=qc,
            device_id=device_id,
            shots=shots,
            timeout=timeout,
            qubits=qubits,** kwargs
        )
