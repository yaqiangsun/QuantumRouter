"""Backend implementations for the LingYun provider.
This module holds the two backend subclasses
(:class:`LingYunQuantumBackend` and :class:`LingYunSimulatorBackend`)
that bind the generic backend contract to the LingYun REST surface.
"""
from __future__ import annotations
from typing import Any, Optional, List
from ....backend.base import Backend
from ....backend.configuration import BackendConfiguration
from ..client import LingYunApiClient
from ..job import LingYunJob
from .utils import qiskit_to_qasm

from qiskit.providers import BackendV2 as Backend, JobV1, Options, QubitProperties
from qiskit.circuit import QuantumCircuit, Measure, Barrier, Parameter
from qiskit.circuit.library import standard_gates
from qiskit.circuit.library.standard_gates import CZGate, RZGate, HGate, \
    GlobalPhaseGate, CXGate, IGate
from qiskit.transpiler import generate_preset_pass_manager, Target, InstructionProperties


class LingYunBackend(Backend):
    """Base for LingYun backends; owns the API client.
    Subclasses set :attr:`_is_simulator` to distinguish the
    quantum / simulator variants.
    """
    _is_simulator: bool = False

    def __init__(
        self,
        configuration: BackendConfiguration,
        api_client: LingYunApiClient,
    ) -> None:
        super().__init__(name=configuration.backend_name)
        self._backend_config = configuration
        self._api_client = api_client
        self._target: Optional[Target] = None
        self.simulator = configuration.simulator

    @property
    def configuration(self) -> BackendConfiguration:
        return self._backend_config

    @property
    def api_client(self) -> LingYunApiClient:
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
            language=kwargs.get("language", "openqasm3"),
        )

    def query_job(self, task_ids: list[str]) -> list[dict]:
        """Fetch results for previously submitted task IDs."""
        result = self.api_client.query_job(task_ids)

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

        if auto_transpile:
            pm = generate_preset_pass_manager(backend=self)
            circuits = [pm.run(qc) for qc in circuits]

        trans_str_list = [qiskit_to_qasm(circ) for circ in circuits]
        print("[INFO][base.py] trans_str_list: ", trans_str_list)
        task_ids = self._api_client.submit_job(
            trans_str_list,
            machine=self.configuration.backend_name,
            shots=shots,
        )
        return LingYunJob(
            backend=self,
            job_id=','.join(task_ids),
            api_client=self._api_client,
            shots=shots,
            readout_calibration=readout_calibration,
            **options
        )

    @property
    def max_circuits(self) -> int:
        """Returns the maximum number of circuits that can be executed in a single job.
        Returns:
            int: The maximum number of circuits.
        """
        return 50

    @classmethod
    def _default_options(cls) -> Options:
        """Returns the default options for the backend.
        Returns:
            Options: The default options.
        """
        return Options()

    @property
    def target(self) -> Optional[Target]:
        """Returns the target for the backend.
        Returns:
            Target: The target for the backend.
        """
        return self._target

    def _make_qubit_properties(self):
        """Creates qubit properties from the machine configuration.
        Returns:
            list[QubitProperties | None]: The list of qubit properties.
        """
        t1 = self._machine_config['qubit']['relatime']['T1']
        t1_qubits = t1['qubit_used']
        t1_values = t1['param_list']
        t1_unit = time_units.get(t1['unit'].lower())
        t2 = self._machine_config['qubit']['relatime']['T2']
        t2_qubits = t2['qubit_used']
        t2_values = t2['param_list']
        t2_unit = time_units.get(t2['unit'].lower())
        frequency = self._machine_config['qubit']['frequency']['f01']
        frequency_qubits = frequency['qubit_used']
        frequency_values = frequency['param_list']
        frequency_unit = frequency_units.get(frequency['unit'].lower())
        if not (t1_qubits == t2_qubits == frequency_qubits):
            raise ValueError("t1/t2/frequency qubits are not the same")
        qubit_properties = [
            QubitProperties() for _ in range(self.configuration.n_qubits)
        ]
        for i, q in enumerate(t1_qubits):
            qubit_properties[int(q[1:]) - 1] = QubitProperties(
                t1=t1_values[i] * t1_unit,
                t2=t2_values[i] * t2_unit,
                frequency=frequency_values[i] * frequency_unit
            )
        return qubit_properties

    def _update_cz_gate(self, target: Target):
        """Updates the CZ gate in the target.
        Args:
            target (Target): The target to update.
        """
        cz_props = {}
        coupler_map = self._machine_config['overview']['coupler_map']
        gate_errors = self._machine_config['twoQubitGate']['czGate']['gate error']
        error_qubits = gate_errors['qubit_used']
        error_values = gate_errors['param_list']
        error_unit = number_units[gate_errors['unit']]
        supported_qubits = self._supported_operation_qubits()
        for i, q in enumerate(error_qubits):
            q0, q1 = coupler_map[q]
            q0, q1 = int(q0[1:]), int(q1[1:])
            if q0 not in supported_qubits or q1 not in supported_qubits:
                continue
            p = InstructionProperties(error=error_values[i] * error_unit, duration=1e-8)
            cz_props[q0, q1] = p
            cz_props[q1, q0] = p
        if 'cz' in self.configuration.basis_gates:
            target.add_instruction(CZGate(), cz_props)

    def _supported_operation_qubits(self):
        """Returns physical qubits with both single-qubit gates and readout support."""
        single_qubits = self._machine_config['qubit']['singleQubit']['gate error']['qubit_used']
        readout_qubits = self._machine_config['readout']['readoutArray']['Readout Error']['qubit_used']
        return {int(q[1:]) for q in single_qubits} & {int(q[1:]) for q in readout_qubits}

    def _update_single_gates(self, target: Target):
        """Updates the single-qubit gates in the target.
        This method adds single-qubit gates (e.g., RZ, X2P, X2M, Y2P, Y2M, XY2P, XY2M)
        to the target based on the backend's configuration. It also includes the HGate
        and GlobalPhaseGate.
        Args:
            target (Target): The target to update with single-qubit gates.
        """
        rz_props = {}
        single_props = {}
        gate_params = self._machine_config['qubit']['singleQubit']['gate error']
        gate_values = gate_params['param_list']
        gate_qubits = gate_params['qubit_used']
        gate_unit = number_units[gate_params['unit']]
        for i, q in enumerate(gate_qubits):
            q_index = (int(q[1:]),)
            rz_props[q_index] = InstructionProperties(error=0, duration=0)
            single_props[q_index] = InstructionProperties(
                error=gate_values[i] * gate_unit,
                duration=0
            )
        if 'rz' in self.configuration.basis_gates:
            target.add_instruction(RZGate(Parameter('theta')), rz_props)
        if 'id' in self.configuration.basis_gates:
            target.add_instruction(IGate(), single_props.copy())


        target.add_instruction(GlobalPhaseGate(Parameter('phase')))

    def _update_measure_gate(self, target: Target):
        """Updates the measurement gate in the target.
        This method adds the measurement gate to the target based on the backend's
        configuration and readout error data.
        Args:
            target (Target): The target to update with the measurement gate.
        """
        gate_params = self._machine_config['readout']['readoutArray']['Readout Error']
        gate_values = gate_params['param_list']
        gate_qubits = gate_params['qubit_used']
        gate_unit = number_units[gate_params['unit']]
        props = {
            (int(q[1:]),): InstructionProperties(error=gate_values[i] * gate_unit, duration=0)
            for i, q in enumerate(gate_qubits)
        }
        target.add_instruction(Measure(), props)

    def _update_barrier_gate(self, target: Target):
        """Updates the barrier gate in the target.
        This method adds the barrier gate to the target if it is supported by the
        backend's configuration.
        Args:
            target (Target): The target to update with the barrier gate.
        """
        if 'barrier' in self.configuration.basis_gates:
            target.add_instruction(Barrier, name="barrier")


class LingYunQuantumBackend(LingYunBackend):
    """A real quantum computer on the LingYun platform."""
    _is_simulator = False

    def __init__(
        self,
        configuration: BackendConfiguration,
        api_client: LingYunApiClient,
    ) -> None:
        super().__init__(configuration=configuration, api_client=api_client)
        self._machine_config = self._api_client.get_quantum_machine_config(
            self.configuration.backend_name
        )
        target = Target(
            num_qubits=configuration.n_qubits,
            description=configuration.backend_name,
            qubit_properties=self._make_qubit_properties()
        )
        self._update_cz_gate(target)
        self._update_single_gates(target)
        self._update_measure_gate(target)
        self._update_barrier_gate(target)
        self._target = target


class LingYunSimulatorBackend(LingYunBackend):
    _is_simulator = True
    """A cloud-hosted simulator on the LingYun platform."""

    def __init__(
        self,
        configuration: BackendConfiguration,
        api_client: LingYunApiClient,
    ) -> None:
        super().__init__(configuration=configuration, api_client=api_client)
        target = Target(
            num_qubits=configuration.n_qubits,
            description=configuration.backend_name,
        )
        self._update_gates(target)
        self._target = target

    
    def _update_gates(self, target):
        """Updates the gates in the target for the simulator backend.
        This method adds all supported gates (single-qubit, two-qubit, and measurement gates)
        to the target based on the backend's configuration.
        Args:
            target (Target): The target to update with the gates.
        """
        q_props = {(q,): None for q in range(self.configuration.n_qubits)}

        derivative_gates = self.configuration.data["derivative_gates"]
        gates = set(self.configuration.basis_gates + derivative_gates)
        print("[INFO] basis_gates contains h ?", self.configuration.basis_gates)

        ins_mapping_list = {
            'rx': [standard_gates.RXGate(Parameter('theta')), q_props],
            'ry': [standard_gates.RYGate(Parameter('theta')), q_props],
            'rz': [standard_gates.RZGate(Parameter('theta')), q_props],
            'id': [standard_gates.IGate(), q_props],
            'h': [standard_gates.HGate(), q_props],
            'x': [standard_gates.XGate(), q_props],
            'y': [standard_gates.YGate(), q_props],
            'z': [standard_gates.ZGate(), q_props],
            's': [standard_gates.SGate(), q_props],
            'sd': [standard_gates.SdgGate(), q_props],
            't': [standard_gates.TGate(), q_props],
            'td': [standard_gates.TdgGate(), q_props],
            'measure': [Measure(), q_props],
        }
        ins_mapping_dict = {
            'cz': {'instruction': CZGate(), 'properties': {None: None}},
            'cx': {'instruction': CXGate(), 'properties': {None: None}},
            'barrier': {'instruction': Barrier, 'name': 'barrier'}
        }
        for gate in gates:
            if gate in ins_mapping_list:
                target.add_instruction(*ins_mapping_list[gate])
            elif gate in ins_mapping_dict:
                target.add_instruction(**ins_mapping_dict[gate])
            elif gate == 'id':
                pass
            # else:
            #     warnings.warn(f'{gate} is not supported in simulator backend.')


time_units = {
    's': 1,
    'ms': 1e-3,
    'us': 1e-6,
    'μs': 1e-6,
    'ns': 1e-9
}
frequency_units = {
    'hz': 1,
    'khz': 1e3,
    'mhz': 1e6,
    'ghz': 1e9
}
number_units = {
    '%': 1e-2,
    '': 1
}