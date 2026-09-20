"""Backend implementations for the WuYue provider.

:class:`WuYueBackend` (a Qiskit :class:`~qiskit.providers.BackendV2`)
binds the generic backend contract to the WuYue REST surface.  The Qiskit
circuit is transpiled (optionally) against a fully-connected Target,
converted to OpenQASM 2, and shipped to the cloud via
:class:`~quantumrouter.providers.wuyue.client.WuYueApiClient`; the
returned :class:`~quantumrouter.providers.wuyue.job.WuYueJob` polls the
queued task and recovers a standard Qiskit :class:`~qiskit.result.Result`.

Topology note: WuYue's engine-list endpoint exposes no per-backend
coupling, and the on-scope device (``WuYue-QPUSim-FullAmpSim``) is a
simulator, so the Target is built fully-connected.  The server accepts
standard OpenQASM 2 (``h``, ``cx``, ``cz``, ``rz``, ``ry``, ``u3``, ...)
and executes the submitted text as-is, so a fully-connected client-side
Target is safe for the simulator and acceptable as a first cut for real
hardware (which the server can additionally auto-map).
"""

from __future__ import annotations

import re
from typing import Any, Union

from ....backend.configuration import BackendConfiguration
from ..client import WuYueApiClient
from ..job import WuYueJob
from .utils import qiskit_to_qasm2

from qiskit import QuantumCircuit
from qiskit.circuit import Parameter
from qiskit.circuit.library import (
    Barrier,
    CXGate,
    CZGate,
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
)
from qiskit.providers import BackendV2 as Backend, JobV1, Options
from qiskit.transpiler import Target, generate_preset_pass_manager


class WuYueBackend(Backend):
    """Base class for WuYue backends; owns the API client."""

    _is_simulator: bool = False

    def __init__(
        self,
        configuration: BackendConfiguration,
        api_client: WuYueApiClient,
    ) -> None:
        super().__init__(name=configuration.backend_name)
        self._backend_config = configuration
        self._api_client = api_client
        self.simulator = self._is_simulator or configuration.simulator
        self._target = self._build_target()

    # ------------------------------------------------------------------ #
    # Metadata
    # ------------------------------------------------------------------ #
    @property
    def configuration(self) -> BackendConfiguration:
        return self._backend_config

    @property
    def api_client(self) -> WuYueApiClient:
        return self._api_client

    @property
    def is_simulator(self) -> bool:
        return self._is_simulator

    @property
    def target(self) -> Target:
        return self._target

    @property
    def max_circuits(self) -> int:
        """Max circuits per ``run()`` batch (one WuYue task per circuit)."""
        return 50

    @classmethod
    def _default_options(cls) -> Options:
        return Options()

    # ------------------------------------------------------------------ #
    # Target construction
    # ------------------------------------------------------------------ #
    def _fill_target_with_gates(self, target: Target) -> None:
        """Populate a (possibly compact) Target with the WuYue gate set.

        The gate set mirrors the OpenQASM 2 baseline the WuYue server
        compiles; every gate is fully-connected so routing never needs
        swaps and the pre-transpiled widths stay compact.
        """
        n_qubits = target.num_qubits
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

    def _build_target(self) -> Target:
        """Build a fully-connected Target from the backend listing data.

        Gates mirror the OpenQASM 2 baseline the WuYue server compiles.
        """
        target = Target(
            num_qubits=self._backend_config.n_qubits,
            description=self._backend_config.backend_name,
        )
        self._fill_target_with_gates(target)
        return target

    def _transpile_compact(self, circuit: QuantumCircuit) -> QuantumCircuit:
        """Transpile ``circuit`` against a target of only its own width.

        Transpiling against the backend's real (e.g. 30-qubit) target makes
        qiskit pad the circuit to the full size with idle wires; a 30-qubit
        full-amplitude task then never leaves the queue.  A compact
        fully-connected target of ``min(width, backend.n_qubits)`` performs
        the same {basis-gate, route-nowhere} cleanup without the padding.
        """
        n = min(circuit.num_qubits, self._backend_config.n_qubits)
        compact = Target(num_qubits=n)
        self._fill_target_with_gates(compact)
        pm = generate_preset_pass_manager(optimization_level=1, target=compact)
        return pm.run(circuit)

    # ------------------------------------------------------------------ #
    # Operations
    # ------------------------------------------------------------------ #
    def fetch_configuration(self) -> dict:
        """Download the raw backend info the provider parsed at listing time."""
        return dict(self._backend_config.data or {})

    def submit_job(
        self,
        circuits: list[str],
        *,
        shots: int = 1024,
        **kwargs: Any,
    ) -> list[str]:
        """Submit OpenQASM 2 circuits; return the assigned task ids."""
        qubits = kwargs.pop("qubits", 0) or 0
        task_ids: list[str] = []
        for qasm_text in circuits:
            task_ids.append(
                self.api_client.submit_job(
                    qasm_text,
                    device_id=self.configuration.backend_name,
                    qubits=qubits or _qasm_qubit_count(qasm_text),
                    shots=shots,
                    **kwargs,
                )
            )
        return task_ids

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
        """Transpile (optionally) and submit a batch of circuits to WuYue.

        Args:
            run_input: The circuit(s) to execute.
            shots: Number of shots per circuit.
            readout_calibration: Accepted for interface parity; the WuYue
                simulator has no readout-error calibration.
            auto_transpile: When True, run each circuit through a preset
                pass manager targeting a compact, fully-connected gate set
                spanning only the circuit's own width (see
                :meth:`_transpile_compact`).

        Returns:
            A :class:`WuYueJob` whose ``result()`` polls and returns a
            qiskit :class:`~qiskit.result.Result`.
        """
        if isinstance(run_input, QuantumCircuit):
            circuits = [run_input]
        elif isinstance(run_input, list):
            circuits = run_input
        else:
            raise TypeError(f"Unsupported run_input type: {type(run_input)}")

        if auto_transpile:
            # Transpile onto a compact target spanning only each circuit's
            # own width instead of the backend's full size.  Against the real
            # (e.g. 30-qubit) target qiskit pads the circuit to the full size
            # with idle wires, which makes full-amplitude simulation infeasible
            # and the task sits queued forever.
            circuits = [self._transpile_compact(qc) for qc in circuits]

        task_ids: list[str] = []
        for circ in circuits:
            qasm_text, width = qiskit_to_qasm2(circ)
            if width > self._backend_config.n_qubits:
                raise ValueError(
                    f"Circuit uses {width} qubits but backend "
                    f"{self._backend_config.backend_name} has "
                    f"{self._backend_config.n_qubits}"
                )
            task_ids.append(
                self.api_client.submit_job(
                    qasm_text,
                    device_id=self.configuration.backend_name,
                    qubits=width,
                    shots=shots,
                    **options,
                )
            )

        return WuYueJob(
            backend=self,
            task_ids=task_ids,
            api_client=self._api_client,
            shots=shots,
            **options,
        )


class WuYueQuantumBackend(WuYueBackend):
    """A real quantum computer on the WuYue platform."""

    _is_simulator = False


class WuYueSimulatorBackend(WuYueBackend):
    """A cloud-hosted simulator on the WuYue platform."""

    _is_simulator = True


def _qasm_qubit_count(qasm_text: str) -> int:
    """Return the declared width ``qreg q[N]`` of an OpenQASM 2 circuit."""
    match = re.search(r"qreg\s+q\[(\d+)\];", qasm_text or "")
    return int(match.group(1)) if match else 0
