"""TianYan provider.
Concrete :class:`Provider` for the TianYan quantum-cloud.
All low-level Transport logic removed; network, auth, request assembly
delegated to cqlib.TianYanPlatform wrapped inside TianYanApiClient.
Self-registers with :class:`ProviderRegistry` so that
``ProviderRegistry.get("TianYan")`` resolves once this package is imported.
"""
from __future__ import annotations
import json
from datetime import datetime
from ...provider.base import Provider
from ...provider.registry import ProviderRegistry
from ...backend.base import Backend
from ...backend.configuration import BackendConfiguration
from ...config import ConnectionConfig
from ...exceptions import BackendNotFoundError
from ...types import BackendStatus, BackendType
from .backend import TianYanQuantumBackend, TianYanSimulatorBackend
from .client import TianYanApiClient


GateConfig = tuple[str, list[str], list[list[int]]]
gate_parameters = {
    'rx': 1,
    'ry': 1,
    'rz': 1,
    'rxy': 2,
    'xy2p': 1,
    'xy2m': 1,
}


class TianYanProvider(Provider):
    """Cloud-provider implementation for TianYan."""
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
        return "tianyan"

    def _create_api_client(self) -> TianYanApiClient:
        return TianYanApiClient(token=self.token)

    @staticmethod
    def _parse_tianyan_config(raw_api_data: dict, api_client: TianYanApiClient) -> BackendConfiguration:
        """TianYan exclusive config parser, fully restore original business logic."""
        disabled_qubits = [q for q in raw_api_data['disabledQubits'].split(',') if q]
        disabled_couplers = [g for g in raw_api_data['disabledCouplers'].split(',') if g]
        backend_id = raw_api_data['id']
        n_qubits = raw_api_data['bitWidth']
        if raw_api_data['labels'] == '1':
            backend_type = BackendType.quantum_computer
        else:
            backend_type = BackendType.simulator
        coupling_map = []
        if backend_type == BackendType.quantum_computer:
            qpu = api_client.get_quantum_computer_config(backend_id)
            qubits = [int(q[1:]) for q in qpu['qubits'] if q not in disabled_qubits]
            for k, q in qpu['coupler_map'].items():
                if k in disabled_couplers:
                    continue
                q0, q1 = q
                if q0 in disabled_qubits or q1 in disabled_qubits:
                    continue
                coupling_map.append([int(q0[1:]), int(q1[1:])])
        else:
            qubits = list(range(n_qubits))
            coupling_map = [[i, j] for i in range(min(n_qubits, 100)) for j in range(i)]
        basis_gates = []
        derivative_gates = []
        gates = []
        for gate in raw_api_data['baseGate']:
            name = gate['qcis'].lower()
            rule = gate['rule']
            # qcis name mapping same as original
            if name == 'i':
                name = 'id'
            elif name == 'b':
                name = 'barrier'
            elif name == 'm':
                name = 'measure'
            basis_gates.append(name)
            try:
                rule = json.loads(rule)
            except json.JSONDecodeError:
                pass
            if isinstance(rule, dict) and 'topology' in rule:
                gate_coupling_map = coupling_map
            else:
                gate_coupling_map = [[q] for q in qubits]
            param_cnt = gate_parameters.get(name, 0)
            gates.append((name, [f'p_{i}' for i in range(param_cnt)], gate_coupling_map))
        for gate in raw_api_data['derivativeGate']:
            name = gate['qcis'].lower()
            if name not in basis_gates:
                derivative_gates.append(name)

        construct_data = {'derivative_gates': derivative_gates,
                          'backend_id': backend_id,
                          'backend_type': backend_type}
        cfg_build_dict = {
            "backend_name": raw_api_data['code'],
            "n_qubits": n_qubits,
            "simulator": backend_type in [BackendType.simulator],
            "coupling_map": coupling_map,
            "basis_gates": basis_gates,
            "status": BackendStatus.RUNNING,
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
        """List TianYan backends with optional filtering."""
        raw_backends = self._api_client.get_backends()
        # print("[INFO] provider.py raw_backends: ", raw_backends)

        result: list[Backend] = []
        for data in raw_backends:
            cfg = self._parse_tianyan_config(data, self._api_client)
            if simulator is not None and cfg.simulator != simulator:
                continue
            if name is not None and cfg.backend_name != name:
                continue

            if cfg.simulator:
                sim_backend = TianYanSimulatorBackend(
                    configuration=cfg,
                    api_client=self._api_client,
                )

                result.append(sim_backend)
            else:
                qpu_backend = TianYanQuantumBackend(
                    configuration=cfg,
                    api_client=self._api_client,
                )

                result.append(qpu_backend)
        # print("[INFO] provider.py result: ", result)
        return result


    def backend(self, name: str) -> Backend:
        """Retrieve a single TianYan backend by name."""
        for data in self._api_client.get_backends():
            if data.get("code") != name:
                continue
            cfg = self._parse_tianyan_config(data, self._api_client)
            if cfg.simulator:
                return TianYanSimulatorBackend(
                    configuration=cfg,
                    api_client=self._api_client,
                )
            return TianYanQuantumBackend(
                configuration=cfg,
                api_client=self._api_client,
            )
        raise BackendNotFoundError(name)


ProviderRegistry.register(TianYanProvider)
