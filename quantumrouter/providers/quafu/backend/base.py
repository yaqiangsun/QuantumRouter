"""Backend implementations for the Quafu provider.

:class:`QuafuBackend` (qiskit :class:`BackendV2`) binds the generic
backend contract to the Quafu REST surface. Both the simulator and
quantum variants share this class; they only differ in how the
:class:`~qiskit.transpiler.Target` is built.

Topology note: Quafu does not expose per-backend coupling via its
listing endpoint, and the on-scope device (ScQ-Sim10) is a simulator,
so the Target is built fully-connected regardless of machine. The
native gate set, by contrast, is taken from the listing's
``valid_gates`` field (normalised by the provider), so the Target
tracks the machine actually serving the token (ScQ-Sim10, Baihua,
ScQ-P5, ...). Gate names that cannot be mapped to a Qiskit instruction
are skipped with a warning rather than guessed; if the listing carries
no gate list a fixed OpenQASM-2 baseline is used. Upstream pyquafu additionally
compiles on the server (``compile=True``), which re-routes onto the
real device topology anyway — so a fully-connected client-side Target
is safe for the simulator and acceptable as a first cut for real
hardware.
"""

from __future__ import annotations

import logging
from typing import Any, Optional, Union

from ....backend.configuration import BackendConfiguration
from ..client import QuafuApiClient
from ..job import QuafuJob
from .utils import qiskit_to_qasm2

import qiskit
from qiskit import QuantumCircuit
from qiskit.circuit.library import Barrier, CXGate, IGate, Measure
from qiskit.circuit.library.standard_gates import get_standard_gate_name_mapping
from qiskit.providers import BackendV2 as Backend, JobV1, Options
from qiskit.transpiler import Target, generate_preset_pass_manager

logger = logging.getLogger(__name__)

# Gate-name resolution for the Target: everything runs through qiskit's
# own maintained standard-gate registry (``get_standard_gate_name_mapping()``,
# 54 gates incl. parametric rx/ry/rz, iswap, sxdg, ccx, reset, ...) instead
# of a hand-copied subset, so the recognised set tracks qiskit releases.
# Only the alias spellings Quafu's ``valid_gates`` listing emits that qiskit
# does not know are listed here; they are instantiated fresh per backend.
# Parametric gates come out of the mapping already bound to placeholder
# ``Parameter``s, matching the previous factory behaviour.
_GATE_ALIASES: dict[str, type] = {
    "cnot": CXGate,
    "i": IGate,
}

# Fixed OpenQASM-2 baseline used when the listing carries no gate list,
# reproducing the previous hardcoded set: RX/RY/RZ + H/X/Y/Z/S/Sdg/T/Tdg/
# I single-qubit, CX/CZ two-qubit. Measure/Barrier are added separately.
_FALLBACK_GATES = [
    "rx", "ry", "rz",
    "h", "x", "y", "z", "s", "sdg", "t", "tdg", "id",
    "cx", "cz",
]


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
        """Build a Target driven by the cloud's ``valid_gates`` listing.

        Gates are materialised onto a fully-connected graph (Quafu does
        not publish coupling maps; the server re-routes via
        ``compile=True`` anyway). Gate names the listing reports but that
        resolve to no instruction are skipped with a warning, so the
        transpiler never emits a gate the server does not accept. When the
        listing carries no gate list, a fixed OpenQASM-2 baseline
        (``_FALLBACK_GATES``) is used so a bare config still yields a
        usable target. Measure and barrier are added unconditionally.
        """
        n_qubits = self._backend_config.n_qubits
        target = Target(
            num_qubits=n_qubits, description=self._backend_config.backend_name
        )
        q_props = {(q,): None for q in range(n_qubits)}
        two_q_props = {
            (i, j): None
            for i in range(n_qubits)
            for j in range(n_qubits)
            if i != j
        }

        gate_names = get_standard_gate_name_mapping()
        gate_names.update({name: cls() for name, cls in _GATE_ALIASES.items()})
        gates = self._backend_config.basis_gates or _FALLBACK_GATES
        registered: set[str] = set()
        for name in gates:
            if name in ("measure", "barrier"):
                # Added unconditionally below; resolve there, not here, so a
                # listing that advertises them never trips the unknown-gate
                # warning below.
                continue
            gate = gate_names.get(name)
            if gate is None:
                # Server advertises a gate neither qiskit nor the aliases can
                # represent (e.g. ``sy`` on ScQ-P5 in qiskit 2.5): it cannot
                # enter the Target. Warn so the omission is visible — a
                # circuit using this gate verbatim fails at transpile time
                # instead of silently misbehaving.
                logger.warning(
                    "backend %s advertises gate %r, which qiskit %s has no "
                    "instruction for; excluding it from the Target",
                    self._backend_config.backend_name,
                    name,
                    qiskit.__version__,
                )
                continue
            # Dedup on the instruction's own name so aliases resolve to one
            # registration (e.g. ``cnot`` -> CXGate, whose name is ``cx``).
            instr_name = getattr(gate, "name", name)
            if instr_name in registered:
                continue
            target.add_instruction(
                gate, q_props if gate.num_qubits == 1 else two_q_props
            )
            registered.add(instr_name)

        # Measurement and barrier are universal; barrier is also required
        # by the transpiler's routing passes regardless of the listing.
        if "measure" not in registered:
            target.add_instruction(Measure(), q_props)
        if "barrier" not in registered:
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
