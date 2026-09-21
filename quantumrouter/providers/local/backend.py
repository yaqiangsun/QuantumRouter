"""Backend for the local Qiskit simulator provider.

This module binds the generic Qiskit ``BackendV2`` contract to
Qiskit's *core* simulator — :class:`qiskit.providers.basic_provider.BasicSimulator` —
with no extra third-party dependency (``qiskit-aer`` is deliberately *not* used).

The provider is the ``local`` entry in ``quantumrouter/providers/``. It exists so
the same calling code that talks to LingYun / TianYan / ... can also run
fully offline: no URL, no token, no server.

Two classes:

* :class:`LocalSimulatorBackend` — a ``BackendV2`` whose ``target`` mirrors
  exactly what ``BasicSimulator`` can run (all-to-all, universal gate set), so
  ``transpile(qc, backend=...)`` output is always runnable by the inner simulator.
* :class:`LocalSimulatorJob` — wraps the inner :class:`BasicProviderJob` so the
  exposed ``Result`` reports this backend's name instead of ``basic_simulator``.
"""

from __future__ import annotations

from typing import Any

from qiskit.circuit import QuantumCircuit
from qiskit.providers import BackendV2 as Backend, JobV1, JobStatus, Options
from qiskit.providers.basic_provider import BasicSimulator
from qiskit.result import Result
from qiskit.transpiler import Target, generate_preset_pass_manager

from ...backend.configuration import BackendConfiguration

__all__ = ["LocalSimulatorBackend", "LocalSimulatorJob"]


def _build_target(num_qubits: int, description: str) -> Target:
    """Build an all-to-all ``Target`` mirroring ``BasicSimulator``'s op set.

    ``BasicSimulator`` only ever runs instructions it declared in its own target,
    so mirroring that exact set (with ``num_qubits`` fixed) guarantees whatever
    ``transpile`` produces can be executed by the inner simulator.
    """
    target = Target(num_qubits=num_qubits, description=description)
    for inst, _qargs in BasicSimulator().target.instructions:
        if isinstance(inst, str):
            # 'measure' / 'reset' / 'barrier' / 'delay' are installed by name.
            target.add_instruction(inst, name=inst, properties={None: None})
        elif isinstance(inst, type):
            # UnitaryGate / Delay are installed globally by class; properties
            # may not be set in that case.
            target.add_instruction(inst, name=inst.__name__)
        elif inst.name == "global_phase":
            # Zero-qubit global op takes an empty properties dict.
            target.add_instruction(inst, properties={})
        else:
            # Everything else: a gate instance usable on any qargs (all-to-all).
            target.add_instruction(inst, properties={None: None})
    return target


class LocalSimulatorBackend(Backend):
    """A QuantumRouter backend that runs circuits on the local Qiskit simulator.

    The circuit never leaves the machine — no HTTP, no transport, no cloud
    token. ``readout_calibration`` / ``auto_transpile`` keep the same signature
    as every other QuantumRouter backend (the ``Sampler`` passes them in), but
    on an ideal local simulator they are semantic no-ops.
    """

    _is_simulator = True

    def __init__(
        self,
        configuration: BackendConfiguration,
        api_client: Any = None,
    ) -> None:
        super().__init__(name=configuration.backend_name)
        self._backend_config = configuration
        # Kept for interface parity with the other QuantumRouter backends;
        # a local simulator has no API client to reach.
        self._api_client = api_client
        self._simulator = BasicSimulator()
        self._target = _build_target(
            num_qubits=configuration.n_qubits,
            description=configuration.backend_name,
        )

    # ------------------------------------------------------------------ #
    # Metadata
    # ------------------------------------------------------------------ #
    @property
    def configuration(self) -> BackendConfiguration:
        return self._backend_config

    @property
    def api_client(self) -> Any:
        return self._api_client

    @property
    def is_simulator(self) -> bool:
        return True

    @property
    def target(self) -> Target:
        return self._target

    @property
    def num_qubits(self) -> int:
        return self._backend_config.n_qubits

    @property
    def max_circuits(self) -> int:
        """Simulate every circuit in one job — no batching limit needed."""
        return None

    @classmethod
    def _default_options(cls) -> Options:
        return Options(shots=1024)

    # ------------------------------------------------------------------ #
    # Execution
    # ------------------------------------------------------------------ #
    def run(
        self,
        run_input,
        shots: int = 1024,
        readout_calibration: bool = True,
        auto_transpile: bool = True,
        **options: Any,
    ) -> LocalSimulatorJob:
        """Run circuit(s) on the local simulator and return a job handle.

        Mirrors the ``run()`` contract of the other QuantumRouter backends:
        accepts ``readout_calibration`` / ``auto_transpile`` explicitly, then
        forwards the rest of the options the ``Sampler`` may supply (``memory``,
        ``seed_simulator``, ...). The local simulator is ideal, so the readout
        switch is a no-op; ``auto_transpile`` still transpiles against this
        backend's target for consistency with cloud behavior.
        """
        if isinstance(run_input, QuantumCircuit):
            circuits = [run_input]
        elif isinstance(run_input, list):
            circuits = list(run_input)
        else:
            raise TypeError(f"Unsupported input type: {type(run_input)}")

        if auto_transpile:
            pm = generate_preset_pass_manager(backend=self)
            circuits = [pm.run(qc) for qc in circuits]

        # Forward only what the core simulator understands; absorb the rest
        # (seed_simulator and any vendor-private keys) so nothing leaks through
        # to BasicSimulator's "option not used" warnings.
        sim_kwargs = {"shots": shots}
        if options.pop("memory", False):
            sim_kwargs["memory"] = True
        options.pop("seed_simulator", None)

        job = self._simulator.run(circuits, **sim_kwargs)
        return LocalSimulatorJob(
            backend=self,
            job_id=job.job_id(),
            inner_job=job,
            shots=shots,
            readout_calibration=readout_calibration,
            **options,
        )


class LocalSimulatorJob(JobV1):
    """Job handle for :class:`LocalSimulatorBackend`.

    The simulation itself is delegated to the inner ``BasicProviderJob``; this
    wrapper only makes the exposed ``Result`` report this backend's identity
    instead of ``basic_simulator``.
    """

    def __init__(
        self,
        backend: LocalSimulatorBackend,
        job_id: str,
        inner_job: JobV1 | None = None,
        **kwargs: Any,
    ) -> None:
        super().__init__(backend=backend, job_id=job_id, **kwargs)
        self._inner_job = inner_job
        self._result: Result | None = None

    def submit(self) -> None:
        """Simulation already ran synchronously in ``run()``; nothing to do."""

    def cancel(self) -> None:
        """A finished local job cannot be cancelled."""

    def status(self) -> JobStatus:
        if self._result is not None:
            return JobStatus.DONE
        return JobStatus.RUNNING

    def result(self, timeout: float | None = None) -> Result:
        if self._result is None:
            data = self._inner_job.result().to_dict()
            data["backend_name"] = self.backend().name
            data["job_id"] = self._job_id
            self._result = Result.from_dict(data)
        return self._result
