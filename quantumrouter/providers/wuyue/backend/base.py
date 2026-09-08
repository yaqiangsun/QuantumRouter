"""Backend implementations for the WuYue mobile cloud provider."""
from typing import Any, Union, List
from ....backend.base import Backend
from ....backend.configuration import BackendConfiguration
from ..client import WuYueApiClient

from ..job import WuYueJob
from wuyue.plugin.result import Result as WuYueRawResult
from qiskit.providers import BackendV2 as Backend, JobV1, Options
from qiskit.circuit import QuantumCircuit
from qiskit.transpiler import Target


class WuYueBackend(Backend):
    _is_simulator: bool = False

    def __init__(
        self,
        configuration: BackendConfiguration,
        api_client: WuYueApiClient,
    ) -> None:
        super().__init__()
        self._backend_config = configuration
        self._api_client = api_client
        self._target: Target | None = None
        self.simulator = configuration.simulator

    @property
    def configuration(self):
        return self._backend_config

    @property
    def api_client(self) -> WuYueApiClient:
        return self._api_client

    @property
    def is_simulator(self) -> bool:
        return self._is_simulator


    def submit_job(
        self,
        circuits: list[str],
        *,
        shots: int = 1000,
        **kwargs: Any,
    ) -> list[str]:
        language = kwargs.get("language", "qcis")
        timeout = kwargs.get("timeout", 100)
        return self.api_client.submit_job(
            circuits=circuits,
            machine=self.configuration.backend_name,
            shots=shots,
            language=language,
            timeout=timeout,
            **kwargs
        )

    def query_job(self, task_ids: list[str]) -> list[dict]:
        result = self.api_client.query_job(task_ids)
        return result or []

    def run(
        self,
        run_input: Union[QuantumCircuit, list[QuantumCircuit]],
        shots: int = 1024,
        readout_calibration: bool = True,
        auto_transpile: bool = True,
        **options
    ) -> JobV1:
        if isinstance(run_input, QuantumCircuit):
            circuits = [run_input]
        elif isinstance(run_input, list):
            circuits = run_input
        else:
            raise TypeError(f"Unsupported run_input type: {type(run_input)}")

        raw_result_list: List[WuYueRawResult] = []
        task_id_list: List[str] = []
        device_id = self.configuration.backend_name
        timeout = options.get("timeout", 100)

        for qc in circuits:
            qubit_count = qc.num_qubits
            # 平台比特数限制校验
            if not (1 <= qubit_count <= 30):
                raise ValueError(f"Qubit count {qubit_count} out of limit 1~30")

            safe_options = {k: v for k, v in options.items() if k not in ("qubits")}
            # 调用底层Runner提交云端任务
            raw_res: WuYueRawResult = self.api_client.run_circuit_object(
                qc=qc,
                device_id=device_id,
                shots=shots,
                qubits=qubit_count,
                **safe_options,
            )
            raw_result_list.append(raw_res)
            task_id_list.append(raw_res._task_id)
        print("[INFO] base.py run returned task IDs: ", task_id_list)

        return WuYueJob(
            backend_inst=self,
            task_id_list=task_id_list,
            api_client=self._api_client,
            shots=shots,
            readout_calibration=readout_calibration,
            raw_result_list=raw_result_list,
            **options
        )

    @property
    def max_circuits(self) -> int:
        return 50

    @classmethod
    def _default_options(cls) -> Options:
        return Options()

    @property
    def target(self) -> Target | None:
        return self._target


class WuYueQuantumBackend(WuYueBackend):
    _is_simulator = False


class WuYueSimulatorBackend(WuYueBackend):
    _is_simulator = True
