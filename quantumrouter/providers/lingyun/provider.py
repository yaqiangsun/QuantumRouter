"""LingYun provider (凌云).
Concrete :class:`Provider` for the LingYun quantum-cloud. Builds an
open :class:`Transport` from the connection config, hands it to a
:class:`LingYunApiClient`, and lists backends via the client.
Self-registers with :class:`ProviderRegistry` so that
``ProviderRegistry.get("lingyun")`` resolves once this package is
imported.
"""
from __future__ import annotations
from ...provider.base import Provider
from ...provider.registry import ProviderRegistry
from ...backend.base import Backend
from ...backend.configuration import BackendConfiguration
from ...config import ConnectionConfig
from ...exceptions import BackendNotFoundError
from ...transport.factory import create_transport
from ...types import BackendStatus, BackendType
from .backend import LingYunQuantumBackend, LingYunSimulatorBackend
from .client import LingYunApiClient



class LingYunProvider(Provider):
    """Cloud-provider implementation for LingYun (凌云)."""
    def __init__(
        self,
        connection: ConnectionConfig,
        *,
        token: str | None = None,
    ) -> None:
        self.token = token or ""
        
        if connection.base_url and isinstance(connection.base_url, str):
            # 已经存在url时，不要覆盖
            self.connection = connection
        else:
            # 上层url为None时，使用指定地址
            default_url = "http://0.0.0.0:8000"
            self.connection = ConnectionConfig.from_url(default_url, **connection.extra)
        self._transport = create_transport(self.connection)
        self._transport.open()
        self._api_client = self._create_api_client()

    @classmethod
    def name(cls) -> str:
        return "lingyun"

    def _create_api_client(self) -> LingYunApiClient:
        return LingYunApiClient(
            transport=self._transport,
            token=self.token,
        )

    @staticmethod
    def _parse_lingyun_config(raw_api_data: dict, api_client: LingYunApiClient) -> BackendConfiguration:
        """凌云专属配置解析"""
        backend_name = raw_api_data["code"]
        n_qubits = raw_api_data["bitWidth"]
        backend_id = raw_api_data['id']
        raw_status = raw_api_data.get("status", "unknown")
        try:
            status = BackendStatus(raw_status)
        except ValueError:
            status = BackendStatus.UNKNOWN
        if raw_api_data.get("labels") == "1":
            backend_type = BackendType.quantum_computer
        else:
            backend_type = BackendType.simulator
        simulator = backend_type == BackendType.simulator
        basis_gates = []
        gate_list = raw_api_data.get("baseGate", [])
        if gate_list:
            for gate in gate_list:
                g_name = gate.get("qasm", "").lower()
                if g_name == "i":
                    g_name = "id"
                elif g_name == "m":
                    g_name = "measure"
                basis_gates.append(g_name)

        coupling_map = raw_api_data.get("coupler_map", [])
        if not isinstance(coupling_map, list):
            coupling_map = []
        derivative_gates = []
        derivative_gates_raw = raw_api_data['derivativeGate']
        
        for gate in derivative_gates_raw:
            name = gate['qasm'].lower()
            if name not in basis_gates:
                derivative_gates.append(name)

        construct_data = {'derivative_gates': derivative_gates,
                                  'backend_id': backend_id,
                                  'backend_type': backend_type}

        cfg_build_dict = {
            "backend_name": backend_name,
            "n_qubits": n_qubits,
            "simulator": simulator,
            "coupling_map": coupling_map,
            "basis_gates": basis_gates,
            "status": status,
            "data": construct_data,
        }
        cfg = BackendConfiguration.from_dict(cfg_build_dict)

        return cfg

    def backends(
        self,
        *,
        simulator: bool | None = None,
        online: bool = True,
        name: str | None = None,
    ) -> list[Backend]:
        """List LingYun backends with optional filtering."""
        raw_backends = self._api_client.get_backends()
        result: list[Backend] = []
        for data in raw_backends:
            cfg = self._parse_lingyun_config(data, self._api_client)
            if online and cfg.status not in (
                BackendStatus.RUNNING,
                BackendStatus.ONLINE,
                BackendStatus.UNKNOWN
            ):
                continue
            if simulator is not None and cfg.simulator != simulator:
                continue
            if name is not None and cfg.backend_name != name:
                continue
            if cfg.simulator:
                result.append(
                    LingYunSimulatorBackend(
                        configuration=cfg,
                        api_client=self._api_client,
                    )
                )
            else:
                result.append(
                    LingYunQuantumBackend(
                        configuration=cfg,
                        api_client=self._api_client,
                    )
                )
        return result

    def backend(self, name: str) -> Backend:
        """Retrieve a single LingYun backend by name."""
        for data in self._api_client.get_backends():
            if data.get("code") != name:
                continue
            cfg = self._parse_lingyun_config(data, self._api_client)
            if cfg.simulator:
                return LingYunSimulatorBackend(
                    configuration=cfg,
                    api_client=self._api_client,
                )
            return LingYunQuantumBackend(
                configuration=cfg,
                api_client=self._api_client,
            )
        raise BackendNotFoundError(name)


# Self-register once the module is imported.
ProviderRegistry.register(LingYunProvider)
