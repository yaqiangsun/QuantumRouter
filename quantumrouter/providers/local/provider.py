"""Local Qiskit simulator provider.

Concrete :class:`Provider` for running circuits locally with Qiskit's
built-in simulator — no cloud account, no URL, no token, no transport.
It lets ``create_provider("local", ...)`` behave exactly like any other
vendor entry point, so the examples run offline by passing ``--backend
local``.

Self-registers with :class:`ProviderRegistry` so that
``ProviderRegistry.get("local")`` resolves once this package is imported.
"""

from __future__ import annotations

from typing import Any

from ...backend.base import Backend
from ...backend.configuration import BackendConfiguration
from ...config import ConnectionConfig
from ...exceptions import BackendNotFoundError
from ...provider.base import Provider
from ...provider.registry import ProviderRegistry
from ...types import BackendStatus
from .backend import LocalSimulatorBackend

#: Number of qubits exposed by the local simulator unless overridden via
#: ``create_provider("local", n_qubits=...)``. 20 is a comfortable default for
#: Qiskit's pure-Python statevector simulator (it caps at 24); the cost only
#: depends on the *width of the circuit actually run*, not this cap.
DEFAULT_N_QUBITS = 20

#: The single backend this provider exposes.
LOCAL_BACKEND_NAME = "local_simulator"


class LocalProvider(Provider):
    """Provider that runs circuits on Qiskit's local simulator.

    There is intentionally no API client: every backend is built in-process
    and never leaves the machine.
    """

    def __init__(
        self,
        connection: ConnectionConfig,
        *,
        token: str | None = None,
    ) -> None:
        self.connection = connection
        self.token = token or ""
        # Optional per-call override, e.g. create_provider("local", n_qubits=16).
        self.n_qubits = int(connection.extra.get("n_qubits", DEFAULT_N_QUBITS))
        self._api_client = self._create_api_client()

    @classmethod
    def name(cls) -> str:
        return "local"

    def _create_api_client(self) -> Any:
        """No network client exists for a local simulator."""
        return None

    # ------------------------------------------------------------------ #
    # Backend construction
    # ------------------------------------------------------------------ #
    def _build_configuration(self) -> BackendConfiguration:
        """Describe the local simulator as an online, all-to-all backend."""
        return BackendConfiguration(
            backend_name=LOCAL_BACKEND_NAME,
            n_qubits=self.n_qubits,
            simulator=True,
            coupling_map=None,  # all-to-all — no hardware topology
            basis_gates=[
                "rx", "ry", "rz", "h", "x", "y", "z", "s", "sdg", "t", "tdg",
                "id", "cx", "cy", "cz", "swap", "ecr", "measure", "reset",
                "barrier", "delay",
            ],
            status=BackendStatus.RUNNING,
            data={},
        )

    def _make_backend(self) -> LocalSimulatorBackend:
        return LocalSimulatorBackend(configuration=self._build_configuration())

    # ------------------------------------------------------------------ #
    # Public API
    # ------------------------------------------------------------------ #
    def backends(
        self,
        *,
        simulator: bool | None = None,
        online: bool = True,
        name: str | None = None,
    ) -> list[Backend]:
        """Return the local simulator backend(s) with optional filtering."""
        backend = self._make_backend()
        if simulator is not None and backend.is_simulator != simulator:
            return []
        # The local simulator's configuration is always RUNNING, so the
        # ``online`` filter can never drop it (kept for interface parity).
        if name is not None and backend.name != name:
            return []
        return [backend]

    def backend(self, name: str) -> Backend:
        """Retrieve the local simulator backend by name."""
        backend = self._make_backend()
        if backend.name == name:
            return backend
        raise BackendNotFoundError(name)


# Self-register once the module is imported.
ProviderRegistry.register(LocalProvider)
