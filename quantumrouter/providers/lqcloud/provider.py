"""LQCloud provider.

Concrete :class:`Provider` for the LQCloud quantum-cloud.  Uses only
LQCloud's remote request compute service (submit / poll) via
:class:`LQCloudApiClient`; circuit definition stays in Qiskit — the
upstream ``lqcloud`` package and its own ``QuantumCircuit`` are never
imported.  Self-registers with :class:`ProviderRegistry` so that
``ProviderRegistry.get("lqcloud")`` resolves once this package is
imported.
"""

from __future__ import annotations

from ...backend.base import Backend
from ...backend.configuration import BackendConfiguration
from ...config import ConnectionConfig
from ...exceptions import BackendNotFoundError
from ...provider.base import Provider
from ...provider.registry import ProviderRegistry
from ...types import BackendStatus, BackendType
from .backend import LQCloudBackend, LQCloudSimulatorBackend
from .backend.utils import resolve_native_gates
from .client import LQCloudApiClient

#: LQCloud QPU ``status`` strings -> BackendStatus.  The live cloud
#: reports ``"active"`` for schedulable devices; anything else is treated
#: conservatively as offline/unknown so ``online=True`` filtering (which
#: keeps RUNNING / ONLINE / UNKNOWN) drops them.
_STATUS_MAP = {
    "active": BackendStatus.ONLINE,
    "online": BackendStatus.ONLINE,
    "running": BackendStatus.RUNNING,
    "offline": BackendStatus.OFFLINE,
    "maintenance": BackendStatus.OFFLINE,
    "disabled": BackendStatus.OFFLINE,
}


class LQCloudProvider(Provider):
    """Cloud-provider implementation for LQCloud."""

    def __init__(
        self,
        connection: ConnectionConfig,
        *,
        token: str | None = None,
    ) -> None:
        super().__init__(connection=connection, token=token)

    @classmethod
    def name(cls) -> str:
        return "lqcloud"

    def _create_api_client(self) -> LQCloudApiClient:
        # The official cloud is fixed; an optional connection.base_url
        # would allow pointing at a mirror/proxy during development.
        base_url = getattr(self.connection, "base_url", None) or None
        return LQCloudApiClient(
            token=self.token or "",
            base_url=base_url or "https://cloud.logicalqubit.com",
        )

    @staticmethod
    def _parse_lqcloud_config(raw: dict) -> BackendConfiguration:
        """Normalize a raw LQCloud backend dict into a BackendConfiguration."""
        backend_name = raw["name"]
        # ``type`` is authoritative: the live cloud uses ``"real_qpu"`` for
        # hardware; anything else (e.g. ``"simulator"``) is a simulator.
        raw_type = raw.get("type", "")
        backend_type = (
            BackendType.quantum_computer
            if raw_type == "real_qpu"
            else BackendType.simulator
        )
        simulator = backend_type == BackendType.simulator
        status = _STATUS_MAP.get(raw.get("status", ""), BackendStatus.UNKNOWN)

        topology = raw.get("topology") if isinstance(raw.get("topology"), dict) else {}
        coupling_map = topology.get("coupling_map") or []
        if not isinstance(coupling_map, list):
            coupling_map = []

        # ``native_gates`` is the machine's declared gate set when the
        # platform populates it (currently ``None`` on every live backend);
        # resolve it against the platform IR vocabulary with the default
        # full vocabulary as fallback — see resolve_native_gates().
        basis_gates = resolve_native_gates(raw.get("native_gates"))

        construct_data = {
            "backend_type": backend_type,
            "topology": topology,
            "native_gates": raw.get("native_gates"),
            "supported_measurement_types": raw.get("supported_measurement_types"),
            "supported_modes": raw.get("supported_modes"),
            "raw": raw,
        }
        cfg = BackendConfiguration.from_dict(
            {
                "backend_name": backend_name,
                "n_qubits": int(raw.get("qubits", 0)),
                "simulator": simulator,
                "coupling_map": coupling_map,
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
        """List LQCloud backends with optional filtering."""
        raw_backends = self._api_client.get_backends()
        result: list[Backend] = []
        for raw in raw_backends:
            cfg = self._parse_lqcloud_config(raw)
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
                LQCloudSimulatorBackend if cfg.simulator else LQCloudBackend
            )
            result.append(
                backend_cls(configuration=cfg, api_client=self._api_client)
            )
        return result

    def backend(self, name: str) -> Backend:
        """Retrieve a single LQCloud backend by name."""
        for raw in self._api_client.get_backends():
            if raw.get("name") != name:
                continue
            cfg = self._parse_lqcloud_config(raw)
            backend_cls = (
                LQCloudSimulatorBackend if cfg.simulator else LQCloudBackend
            )
            return backend_cls(configuration=cfg, api_client=self._api_client)
        raise BackendNotFoundError(name)


# Self-register once the module is imported.
ProviderRegistry.register(LQCloudProvider)
