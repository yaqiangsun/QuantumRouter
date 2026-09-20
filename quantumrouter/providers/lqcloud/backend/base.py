"""Backend implementation for the LQCloud provider.

:class:`LQCloudBackend` (a Qiskit :class:`~qiskit.providers.BackendV2`)
binds the generic backend contract to the LQCloud REST surface.  The
Qiskit circuit is transpiled onto the backend's real topology, converted
to the LQCloud instruction IR (see :mod:`quantumrouter.providers.lqcloud.backend.utils`)
and shipped to the cloud via :class:`~quantumrouter.providers.lqcloud.client.LQCloudApiClient`;
the returned :class:`~quantumrouter.providers.lqcloud.job.LQCloudJob`
polls the queued task and recovers a standard Qiskit :class:`~qiskit.result.Result`.

The ``configuration.data`` carried by the provider's parsed config holds
the raw backend dict from ``/api/v1/qpus`` (qubits, topology, ...), so
the target can be built without an extra network round-trip at
construction time.
"""

from __future__ import annotations

from typing import Any, Optional, Union

from ....backend.configuration import BackendConfiguration
from ..client import LQCloudApiClient
from ..job import LQCloudJob
from .utils import LQCloudCircuitError, qiskit_circuit_to_ir

from qiskit import QuantumCircuit
from qiskit.circuit.library import Barrier
from qiskit.providers import BackendV2 as Backend, JobV1, Options
from qiskit.transpiler import CouplingMap, Target, generate_preset_pass_manager


def _undirected_coupling(raw: Any) -> list[list[int]]:
    """Expand the server's (possibly one-directional) coupling list into
    an undirected Qiskit coupling map ``[[a, b], ...]``."""
    edges: set[frozenset[int]] = set()
    if isinstance(raw, list):
        for pair in raw:
            if not isinstance(pair, (list, tuple)) or len(pair) != 2:
                continue
            try:
                a, b = int(pair[0]), int(pair[1])
            except (TypeError, ValueError):
                continue
            if a != b:
                edges.add(frozenset((a, b)))
    return [list(e) for e in sorted(edges)]


class LQCloudBackend(Backend):
    """A real quantum computer on the LQCloud platform (e.g. ``MQ02``)."""

    #: Backend kind — subclasses flip this like the other providers.
    _is_simulator: bool = False

    def __init__(
        self,
        configuration: BackendConfiguration,
        api_client: LQCloudApiClient,
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
    def api_client(self) -> LQCloudApiClient:
        return self._api_client

    @property
    def is_simulator(self) -> bool:
        return self._is_simulator

    @property
    def target(self) -> Target:
        return self._target

    @property
    def max_circuits(self) -> int:
        """Max circuits per ``run()`` batch (one LQCloud task per circuit)."""
        return 50

    @classmethod
    def _default_options(cls) -> Options:
        return Options()

    # ------------------------------------------------------------------ #
    # Target construction
    # ------------------------------------------------------------------ #
    def _build_target(self) -> Target:
        """Build a Target mirroring the resolved LQCloud gate set + topology.

        The basis comes from ``configuration.basis_gates`` (the machine's
        declared ``native_gates`` intersected with the IR vocabulary, the
        full vocabulary when the platform publishes none), restricted to
        the QPU's real coupling map — so transpilation routes two-qubit
        gates onto adjacent physical qubits, exactly what the server's
        topology check enforces.

        The Target is built **declaratively** with
        :meth:`Target.from_configuration`, which resolves standard gate
        *names* (``h``/``x``/``rz``/``cz``/...) into Qiskit gate objects —
        no manual name→class registry is maintained here.  ``barrier`` is
        the one name that helper does not know and is added explicitly.
        """
        raw = self._backend_config.data or {}
        n_qubits = int(self._backend_config.n_qubits)
        basis = [str(g).lower() for g in (self._backend_config.basis_gates or [])]
        topology = raw.get("topology") if isinstance(raw, dict) else None
        coupling = _undirected_coupling(
            topology.get("coupling_map") if isinstance(topology, dict) else None
        )
        # A coupling map that is empty/missing at listing time falls back to
        # fully-connected so routing still has edges to work with.
        if not coupling:
            coupling = [
                [i, j] for i in range(n_qubits) for j in range(n_qubits) if i != j
            ]

        # ``Target.from_configuration`` does not accept ``barrier`` (it is
        # not a first-class standard gate); exclude it from the basis list
        # and add it explicitly after — it only acts as a scheduling fence.
        basis_without_barrier = [name for name in basis if name != "barrier"]
        target = Target.from_configuration(
            basis_gates=basis_without_barrier,
            num_qubits=n_qubits,
            coupling_map=CouplingMap(coupling),
        )
        target.description = self._backend_config.backend_name
        target.add_instruction(Barrier, name="barrier")
        return target

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
        """Placeholder for the abstract backend contract.

        LQCloud does not accept opaque circuit strings on this interface;
        real submissions go through :meth:`run` with Qiskit circuits.
        """
        raise NotImplementedError(
            "LQCloud backend accepts Qiskit circuits via run(); "
            "submit_job(circuits, ...) is not supported."
        )

    def query_job(self, task_ids: list[str]) -> list[dict]:
        """Fetch the current status/result envelopes for task ids."""
        return [self._api_client.query_job(tid) for tid in task_ids]

    def run(
        self,
        run_input: Union[QuantumCircuit, list[QuantumCircuit]],
        shots: int = 1024,
        readout_calibration: bool = True,
        auto_transpile: bool = True,
        **options: Any,
    ) -> JobV1:
        """Transpile (optionally) and submit circuits to the LQCloud cloud.

        Args:
            run_input: The Qiskit circuit(s) to execute.
            shots: Number of shots per circuit.
            readout_calibration: Accepted for interface parity with the
                other QuantumRouter backends; LQCloud applies its own
                server-side readout when requested via ``readout_correction``.
            auto_transpile: When True (default), run each circuit through a
                preset pass manager built from this backend's real topology
                (routing + decomposition onto the LQCloud native gates).
                When False, the circuit is submitted as-is and therefore
                must already be in the native gate set on adjacent qubits.

        Returns:
            A :class:`LQCloudJob` whose ``result()`` polls the cloud and
            returns a :class:`~qiskit.result.Result`.
        """
        if isinstance(run_input, QuantumCircuit):
            circuits = [run_input]
        elif isinstance(run_input, list):
            circuits = run_input
        else:
            raise TypeError(f"Unsupported run_input type: {type(run_input)}")

        if auto_transpile:
            # optimization_level is pinned to 1 on purpose: at level >= 2
            # qiskit's ConsolidateBlocks + UnitarySynthesis mis-synthesizes
            # two-qubit blocks on an {h, cz, rz}-only basis and silently
            # drops the entangling gate (observed on MQ02's chain topology).
            # Level 1 routes/decomposes correctly and keeps every gate.
            pm = generate_preset_pass_manager(backend=self, optimization_level=1)
            circuits = [pm.run(qc) for qc in circuits]

        coupling = self._backend_config.coupling_map

        task_ids: list[str] = []
        for circ in circuits:
            width = circ.num_qubits
            if width > self._backend_config.n_qubits:
                raise ValueError(
                    f"Circuit uses {width} qubits but backend "
                    f"{self._backend_config.backend_name} has "
                    f"{self._backend_config.n_qubits}"
                )
            circuit_section = qiskit_circuit_to_ir(
                circ, coupling_map=coupling, shot_override=shots
            )
            command = {
                "action": "run_circuit",
                "shots": shots,
                "circuit": circuit_section,
            }
            envelope = self._api_client.submit_circuit(command, self.name)
            task_id = envelope.get("task_id") or envelope.get("job_id")
            if not task_id:
                raise LQCloudCircuitError(
                    f"LQCloud submission did not return a task id: {envelope!r}"
                )
            task_ids.append(str(task_id))

        return LQCloudJob(
            backend=self,
            task_ids=task_ids,
            api_client=self._api_client,
            shots=shots,
            **options,
        )


class LQCloudSimulatorBackend(LQCloudBackend):
    """A cloud-hosted simulator on the LQCloud platform (if any)."""

    _is_simulator = True
