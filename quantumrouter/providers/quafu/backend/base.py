"""Backend implementations for the Quafu provider.

:class:`QuafuBackend` (qiskit :class:`BackendV2`) binds the generic
backend contract to the Quafu REST surface. Both the simulator and
quantum variants share this class; they only differ in how the
:class:`~qiskit.transpiler.Target` is built.

Topology note: Quafu does not expose per-backend coupling via its
listing endpoint, and the on-scope device (ScQ-Sim10) is a simulator,
so the Target is built fully-connected. Upstream pyquafu additionally
compiles on the server (``compile=True``), which re-routes onto the
real device topology anyway — so a fully-connected client-side Target
is safe for the simulator and acceptable as a first cut for real
hardware.
"""

from __future__ import annotations

from typing import Any, Optional, Union

from ....backend.configuration import BackendConfiguration
from ..client import QuafuApiClient
from ..job import QuafuJob
from .utils import qiskit_to_qasm2

from qiskit import QuantumCircuit
from qiskit.circuit import Parameter
from qiskit.circuit.library import (
    CZGate,
    CXGate,
    HGate,
    IGate,
    Measure,
    RXGate,
    RYGate,
    RZGate,
    SGate,
    SdgGate,
    TGate,
    TdgGate,
    XGate,
    YGate,
    ZGate,
    Barrier,
)
from qiskit.providers import BackendV2 as Backend, JobV1, Options
from qiskit.transpiler import Target, generate_preset_pass_manager


class QuafuBackend(Backend):
    """Base class for Quafu backends; owns the API client."""

    _is_simulator: bool = False

    def __init__(
        self,
        configuration: BackendConfiguration,
        api_client: QuafuApiClient,
    ) -> None:
        super().__init__(name=configuration.backend_name)
        self._backend_config = configuration
        self._api_client = api_client
        self._system_id: int = (configuration.data or {}).get("system_id", 0)
        self.simulator = configuration.simulator
        self._target = self._build_target()

    # ------------------------------------------------------------------ #
    # Metadata
    # ------------------------------------------------------------------ #
    @property
    def configuration(self) -> BackendConfiguration:
        return self._backend_config

    @property
    def api_client(self) -> QuafuApiClient:
        return self._api_client

    @property
    def is_simulator(self) -> bool:
        return self._is_simulator

    @property
    def target(self) -> Target:
        return self._target

    @property
    def max_circuits(self) -> int:
        """Max circuits per ``run()`` batch (one Quafu task per circuit)."""
        return 50

    @classmethod
    def _default_options(cls) -> Options:
        return Options()

    # ------------------------------------------------------------------ #
    # Target construction
    # ------------------------------------------------------------------ #
    def _build_target(self) -> Target:
        """Build a fully-connected Target from the backend listing data.

        Gates mirror the OpenQASM 2 baseline the Quafu server compiles
        (its ``valid_gates`` listed ``cx, cz, rx, ry, rz, x, y, z, h``).
        """
        n_qubits = self._backend_config.n_qubits
        target = Target(num_qubits=n_qubits, description=self._backend_config.backend_name)
        q_props = {(q,): None for q in range(n_qubits)}
        two_q_props = {
            (i, j): None
            for i in range(n_qubits)
            for j in range(n_qubits)
            if i != j
        }

        for cls in (RXGate, RYGate, RZGate):
            target.add_instruction(cls(Parameter("theta")), q_props)
        for cls in (HGate, XGate, YGate, ZGate, SGate, SdgGate, TGate, TdgGate, IGate):
            target.add_instruction(cls(), q_props)
        target.add_instruction(CXGate(), two_q_props)
        target.add_instruction(CZGate(), two_q_props)
        target.add_instruction(Measure(), q_props)
        target.add_instruction(Barrier, name="barrier")
        return target

    # ------------------------------------------------------------------ #
    # Operations
    # ------------------------------------------------------------------ #
    def fetch_configuration(self) -> dict:
        """Download the raw backend info the provider parsed at listing time."""
        # The listing payload (system_id, valid_gates, ...) is kept in the
        # configuration; Quafu's per-chip calibration endpoint is not needed
        # for the on-scope simulator.
        return dict(self._backend_config.data or {})

    def submit_job(
        self,
        circuits: list[str],
        *,
        shots: int = 1024,
        **kwargs: Any,
    ) -> list[str]:
        """Submit OpenQASM 2 circuits; return the assigned task ids."""
        return self.api_client.submit_job(
            circuits=circuits,
            shots=shots,
            system_id=self._system_id,
            compile=kwargs.get("compile", True),
            priority=kwargs.get("priority", 2),
        )

    def query_job(self, task_ids: list[str]) -> list[dict]:
        """Fetch results for previously submitted task ids."""
        return self.api_client.query_job(task_ids)

    def run(
        self,
        run_input: Union[QuantumCircuit, list[QuantumCircuit]],
        shots: int = 1024,
        readout_calibration: bool = True,
        auto_transpile: bool = True,
        **options: Any,
    ) -> JobV1:
        """Transpile (optionally) and submit a batch of circuits to Quafu.

        Args:
            run_input: The circuit(s) to execute.
            shots: Number of shots per circuit.
            readout_calibration: Accepted for interface parity; the Quafu
                simulator has no readout-error calibration.
            auto_transpile: When True, run each circuit through a preset
                pass manager built from this backend's Target first.

        Returns:
            A :class:`QuafuJob` whose ``result()`` polls and returns a
            qiskit :class:`~qiskit.result.Result`.
        """
        if isinstance(run_input, QuantumCircuit):
            circuits = [run_input]
        elif isinstance(run_input, list):
            circuits = run_input
        else:
            raise TypeError(f"Unsupported run_input type: {type(run_input)}")

        if auto_transpile:
            pm = generate_preset_pass_manager(backend=self)
            circuits = [pm.run(qc) for qc in circuits]

        qasms: list[str] = []
        widths: list[int] = []
        for circ in circuits:
            qasm, width = qiskit_to_qasm2(circ)
            if width > self._backend_config.n_qubits:
                raise ValueError(
                    f"Circuit uses {width} qubits but backend "
                    f"{self._backend_config.backend_name} has "
                    f"{self._backend_config.n_qubits}"
                )
            qasms.append(qasm)
            widths.append(width)

        task_ids = self.api_client.submit_job(
            circuits=qasms,
            shots=shots,
            system_id=self._system_id,
            compile=True,
            priority=2,
        )
        return QuafuJob(
            backend=self,
            task_ids=task_ids,
            api_client=self._api_client,
            shots=shots,
            **options,
        )


class QuafuQuantumBackend(QuafuBackend):
    """A real quantum computer on the Quafu platform."""

    _is_simulator = False


class QuafuSimulatorBackend(QuafuBackend):
    """A cloud-hosted simulator on the Quafu platform (e.g. ScQ-Sim10)."""

    _is_simulator = True
