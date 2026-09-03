"""Backend implementations for the TianYan provider.

This module holds the two backend subclasses
(:class:`TianYanQuantumBackend` and :class:`TianYanSimulatorBackend`)
that bind the generic backend contract to the TianYan REST surface.
"""

from __future__ import annotations

from typing import Any

from ....backend.base import Backend
from ....backend.configuration import BackendConfiguration
from ..client import TianYanApiClient
from cqlib_adapter.qiskit_ext.job import TianYanJob
from qiskit.providers import BackendV2 as Backend, JobV1, Options
from qiskit.circuit import QuantumCircuit
from qiskit.transpiler import generate_preset_pass_manager, Target
from cqlib_adapter.utils.converter import qiskit_to_cqlib


class TianYanBackend(Backend):
    """Base for TianYan backends; owns the API client.

    Subclasses set :attr:`_is_simulator` to distinguish the
    quantum / simulator variants.
    """

    _is_simulator: bool = False

    def __init__(
        self,
        configuration: BackendConfiguration,
        api_client: TianYanApiClient,
    ) -> None:
        # has error
        # super().__init__(configuration=configuration, api_client=api_client)

        super().__init__()
        self._backend_config = configuration
        self._api_client = api_client
        self._target = None
        # add
        self.simulator = configuration.simulator

    # 用@property对外暴露配置，替代之前父类入参传入
    @property
    def configuration(self):
        return self._backend_config

    @property
    def api_client(self):
        return self._api_client


    @property
    def is_simulator(self) -> bool:
        return self._is_simulator

    def fetch_configuration(self) -> dict:
        """Download the full hardware/calibration configuration."""
        return self.api_client.get_quantum_machine_config(
            self.configuration.backend_name
        )

    def submit_job(
        self,
        circuits: list[str],
        *,
        shots: int = 1000,
        **kwargs: Any,
    ) -> list[str]:
        """Submit a job and return the assigned task IDs."""
        return self.api_client.submit_job(
            circuits=circuits,
            machine=self.configuration.backend_name,
            shots=shots,
            language=kwargs.get("language", "qcis"),
        )

    def query_job(self, task_ids: list[str]) -> list[dict]:
        """Fetch results for previously submitted task IDs."""
        result = self.api_client.query_job(task_ids)
        # TianYan wraps results in an object with different keys
        # depending on the endpoint version; normalize to a list.
        if isinstance(result, dict):
            return result.get("experimentResultModelList", [])
        return result or []


    def run(
            self,
            run_input,
            shots: int = 1024,
            readout_calibration: bool = True,
            auto_transpile: bool = True,
            **options
    ) -> JobV1:
        """Submits a job to the backend.

        Args:
            run_input (QuantumCircuit | list[QuantumCircuit]): The circuit(s) to execute.
            shots (int, optional): The number of shots to execute. Defaults to 1024.
            readout_calibration (bool, optional): Whether to perform readout calibration.
                Defaults to True.
            auto_transpile (bool, optional): Automatically perform circuit compile on the backend.
            **options: Additional options for the job.

        Returns:
            JobV1: The submitted job.

        Raises:
            TypeError: If the input type is not supported.
        """
        if isinstance(run_input, QuantumCircuit):
            circuits = [run_input]
        elif isinstance(run_input, list):
            circuits = run_input
        else:
            raise TypeError(f"Unsupported input type: {type(run_input)}")

        # FIXME：
        # if auto_transpile:
        #     pm = generate_preset_pass_manager(backend=self)
        #     circuits = [pm.run(qc) for qc in circuits]

        trans_cqlib_list = [qiskit_to_cqlib(circ) for circ in circuits]
        print("[INFO][base.py] trans_cqlib_list: ", trans_cqlib_list)

        circuit_str_list = [c.as_str() for c in trans_cqlib_list]

        task_ids = self._api_client.submit_job(
            circuit_str_list,
            machine=self.configuration.backend_name,
            shots=shots,
        )
        return TianYanJob(
            backend=self,
            job_id=','.join(task_ids),
            api_client=self._api_client,
            shots=shots,
            readout_calibration=readout_calibration,
            **options
        )

    @property
    def max_circuits(self):
        """Returns the maximum number of circuits that can be executed in a single job.

        Returns:
            int: The maximum number of circuits.
        """
        return 50
    
    @classmethod
    def _default_options(cls):
        """Returns the default options for the backend.

        Returns:
            Options: The default options.
        """
        return Options()

    @property
    def target(self):
        """Returns the target for the backend.

        Returns:
            Target: The target for the backend.
        """
        return self._target
    

class TianYanQuantumBackend(TianYanBackend):
    """A real quantum computer on the TianYan platform."""
    _is_simulator = False
    # def __init__(
    #         self,
    #         configuration: BackendConfiguration,
    #         api_client: 'ApiClient',
    # ) -> None:
    #     """
    #     Args:
    #         configuration (BackendConfiguration): The configuration of the backend.
    #         api_client (ApiClient): The client for interacting with the API.
    #     """
    #     super().__init__(configuration=configuration, api_client=api_client)
    #     self._machine_config = self._api_client.get_quantum_machine_config(
    #         self.configuration.backend_name
    #     )
    #     target = Target(
    #         num_qubits=configuration.n_qubits,
    #         description=configuration.backend_name,
    #         qubit_properties=self._make_qubit_properties()
    #     )
    #     self._update_cz_gate(target)
    #     self._update_single_gates(target)
    #     self._update_measure_gate(target)
    #     self._update_barrier_gate(target)
    #     self._target = target
    


class TianYanSimulatorBackend(TianYanBackend):
    _is_simulator = True
    """A cloud-hosted simulator on the TianYan platform."""
    # def __init__(
    #             self,
    #             configuration: BackendConfiguration,
    #             api_client: 'ApiClient',
    #     ) -> None:
    #         """
    #         Args:
    #             configuration (BackendConfiguration): The configuration of the simulator backend.
    #             api_client (ApiClient): The client for interacting with the API.
    #         """
    #         super().__init__(configuration=configuration, api_client=api_client)
    #         target = Target(
    #             num_qubits=configuration.n_qubits,
    #             description=configuration.backend_name,
    #         )
    #         self._update_gates(target)
    #         self._target = target
    
