"""Quafu provider.

Concrete :class:`Provider` for the Quafu quantum-cloud. Uses only
Quafu's remote request compute service (submit / recall); circuit
definition stays in Qiskit. Self-registers with
:class:`ProviderRegistry` so that ``ProviderRegistry.get("quafu")``
resolves once this package is imported.
"""

from __future__ import annotations

from ...backend.base import Backend
from ...backend.configuration import BackendConfiguration
from ...config import ConnectionConfig
from ...exceptions import BackendNotFoundError
from ...provider.base import Provider
from ...provider.registry import ProviderRegistry
from ...types import BackendStatus, BackendType
from .backend import QuafuQuantumBackend, QuafuSimulatorBackend
from .client import QuafuApiClient


# Quafu status strings -> BackendStatus. Quafu also reports "Obsolete"
# for retired systems; that collapses to OFFLINE so ``online=True``
# filtering (which keeps RUNNING / ONLINE / UNKNOWN) drops them.
_STATUS_MAP = {
    "Online": BackendStatus.ONLINE,
    "online": BackendStatus.ONLINE,
    "Offline": BackendStatus.OFFLINE,
    "offline": BackendStatus.OFFLINE,
    "Obsolete": BackendStatus.OFFLINE,
    "obsolete": BackendStatus.OFFLINE,
}


class QuafuProvider(Provider):
    """Cloud-provider implementation for Quafu."""

    def __init__(
        self,
        connection: ConnectionConfig,
        *,
        token: str | None = None,
    ) -> None:
        self.connection = connection
        self.token = token or ""
        self._api_client = self._create_api_client()

    @classmethod
    def name(cls) -> str:
        return "quafu"

    def _create_api_client(self) -> QuafuApiClient:
        # Quafu's server is fixed; the optional connection.base_url would
        # allow pointing at a mirror/proxy during development.
        base_url = getattr(self.connection, "base_url", None) or None
        return QuafuApiClient(token=self.token, base_url=base_url or "https://quafu.baqis.ac.cn/")

    @staticmethod
    def _parse_quafu_config(raw: dict) -> BackendConfiguration:
        """Normalize a raw Quafu backend dict into a BackendConfiguration."""
        system_name = raw["system_name"]
        backend_type = (
            BackendType.simulator if "Sim" in system_name else BackendType.quantum_computer
        )
        simulator = backend_type == BackendType.simulator
        raw_status = raw.get("status", "")
        status = _STATUS_MAP.get(raw_status, BackendStatus.UNKNOWN)
        basis_gates = [g.lower() for g in (raw.get("valid_gates") or [])]

        construct_data = {
            "system_id": raw.get("system_id", 0),
            "valid_gates": basis_gates,
            "backend_type": backend_type,
        }
        cfg = BackendConfiguration.from_dict(
            {
                "backend_name": system_name,
                "n_qubits": int(raw["qubits"]),
                "simulator": simulator,
                "coupling_map": None,
                "basis_gates": basis_gates,
                "status": status,
                "data": construct_data,
            }
        )
        return cfg

    def backends(
        self,
        *,
        simulator: bool | None = None,
        online: bool = True,
        name: str | None = None,
    ) -> list[Backend]:
        """List Quafu backends with optional filtering."""
        raw_backends = self._api_client.get_backends()
        result: list[Backend] = []
        for raw in raw_backends:
            cfg = self._parse_quafu_config(raw)
            if online and cfg.status not in (
                BackendStatus.RUNNING,
                BackendStatus.ONLINE,
                BackendStatus.UNKNOWN,
            ):
                continue
            if simulator is not None and cfg.simulator != simulator:
                continue
            if name is not None and cfg.backend_name != name:
                continue
            backend_cls = (
                QuafuSimulatorBackend if cfg.simulator else QuafuQuantumBackend
            )
            result.append(
                backend_cls(configuration=cfg, api_client=self._api_client)
            )
        return result

    def backend(self, name: str) -> Backend:
        """Retrieve a single Quafu backend by name."""
        for raw in self._api_client.get_backends():
            if raw.get("system_name") != name:
                continue
            cfg = self._parse_quafu_config(raw)
            backend_cls = (
                QuafuSimulatorBackend if cfg.simulator else QuafuQuantumBackend
            )
            return backend_cls(configuration=cfg, api_client=self._api_client)
        raise BackendNotFoundError(name)


# Self-register once the module is imported.
ProviderRegistry.register(QuafuProvider)
