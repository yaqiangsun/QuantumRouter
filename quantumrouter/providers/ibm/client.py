"""IBM Quantum API client.

This client uses the official ``qiskit-ibm-provider`` SDK to reach
IBM Quantum Platform. The SDK manages its own HTTPS transport (auth
token exchange, instance resolution, request retrying), so the
``ConnectionConfig`` passed in by :class:`IBMProvider` is used only
to carry the token, instance, and request deadline — the actual
wire layer is owned by the IBM SDK.

Why not a raw transport here?
`````````````````````````````
IBM Quantum auth is non-trivial (account-level IBM Quantum Platform
login → access token → per-instance CRN resolution) and changes
between account tiers (legacy / cloud). The IBM SDK abstracts this;
re-implementing it on ``transport/http.py`` would duplicate the SDK
and break on every API change.

Circuit format
``````````````
``circuits`` are OpenQASM strings, the IBM Runtime native serialized
form. The client converts each string to a :class:`QuantumCircuit`
via ``QuantumCircuit.from_qasm_str`` before submission.
"""

from __future__ import annotations

from typing import Any

from ...config import ConnectionConfig
from ...exceptions import ProviderError, QuantumRouterError
from ...types import BackendStatus

# Status values IBM Quantum reports via ``backend.status()``.
# ``operational`` -> RUNNING/ONLINE; everything else maps away.
_OK_STATUSES = {"operational"}


def _to_quantum_circuit(circuit: str) -> Any:
    """Convert an OpenQASM string to a ``QuantumCircuit``.

    Importing qiskit locally lets users who only want the LingYun
    provider skip the qiskit dependency.
    """
    try:
        from qiskit import QuantumCircuit
    except ImportError as exc:  # pragma: no cover - env-dependent
        raise QuantumRouterError(
            "IBM provider requires qiskit. Install with: pip install qiskit"
        ) from exc
    return QuantumCircuit.from_qasm_str(circuit)


class IBMApiClient:
    """SDK-backed client for the IBM Quantum REST surface.

    Parameters
    ----------
    connection:
        A :class:`ConnectionConfig` whose ``extra`` carries the IBM
        Quantum ``instance`` (optional). The auth ``token`` lives on
        the provider.
    token:
        IBM Quantum API token. Required.
    instance:
        IBM Quantum instance specifier, e.g. ``ibmquantum/open/online/dev``.
        When omitted, the IBM SDK uses the account default.
    """

    def __init__(
        self,
        connection: ConnectionConfig,
        token: str,
        instance: str | None = None,
    ) -> None:
        if not token:
            raise QuantumRouterError(
                "IBM provider requires a token (IBM_QUANTUM_TOKEN env var)"
            )
        self.connection = connection
        self.token = token
        self.instance = instance or connection.extra.get("instance")
        self._provider = self._init_sdk()

    # ------------------------------------------------------------------ #
    # SDK lifecycle
    # ------------------------------------------------------------------ #
    def _init_sdk(self) -> Any:
        """Initialize the IBM Qiskit Runtime SDK provider."""
        try:
            from qiskit_ibm_provider import IBMProvider
        except ImportError as exc:  # pragma: no cover - env-dependent
            raise QuantumRouterError(
                "IBM provider requires qiskit-ibm-provider. Install with: "
                "pip install qiskit-ibm-provider"
            ) from exc
        return IBMProvider(
            token=self.token,
            instance=self.instance or None,
        )

    # ------------------------------------------------------------------ #
    # Listing & status
    # ------------------------------------------------------------------ #
    def get_backends(self, *, simulator: bool | None = None) -> list[dict]:
        """Return a list of raw backend dicts.

        Each dict has ``name``, ``simulator``, and ``status`` fields
        for :class:`BackendConfiguration.from_api` to consume.
        """
        sdk_backends = self._provider.backends(
            simulator=simulator if simulator is not None else False,
        )
        result: list[dict] = []
        for b in sdk_backends:
            status = b.status()
            result.append(
                {
                    "code": b.name,
                    "simulator": b.configuration().simulator,
                    "status": "running"
                    if status.operational
                    else "offline",
                }
            )
        return result

    @staticmethod
    def normalize_status(raw: Any) -> BackendStatus:
        """Normalize IBM's ``operational``/``offline`` mapping."""
        if raw == "running":
            return BackendStatus.RUNNING
        if raw == "online":
            return BackendStatus.ONLINE
        if raw == "offline":
            return BackendStatus.OFFLINE
        return BackendStatus.UNKNOWN

    # ------------------------------------------------------------------ #
    # Jobs
    # ------------------------------------------------------------------ #
    def submit_job(
        self,
        circuits: list[str],
        machine: str,
        *,
        shots: int = 1000,
    ) -> list[str]:
        """Submit OpenQASM circuits to ``machine`` and return job IDs."""
        backend = self._provider.get_backend(machine)
        qiskit_circuits = [_to_quantum_circuit(c) for c in circuits]
        job = backend.run(qiskit_circuits, shots=shots)
        return [job.job_id()]

    def query_job(self, task_ids: list[str]) -> dict:
        """Fetch results for previously submitted job IDs."""
        results: dict[str, Any] = {}
        for task_id in task_ids:
            job = self._provider.retrieve_job(task_id)
            try:
                result = job.result()
                results[task_id] = result.to_dict()
            except Exception as exc:  # pragma: no cover - env-dependent
                raise ProviderError(
                    f"Failed to fetch results for job {task_id}: {exc}"
                ) from exc
        return results

    def get_machine_config(self, machine_name: str) -> dict:
        """Fetch the configuration (properties) of a backend."""
        backend = self._provider.get_backend(machine_name)
        return backend.configuration().to_dict()
