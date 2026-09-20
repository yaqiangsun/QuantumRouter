"""WuYue provider.

Concrete :class:`Provider` for the WuYue quantum-cloud.  Uses only the
WuYue remote request compute service (list engines / submit / poll) via
:class:`WuYueApiClient`; circuit definition and transpilation stay in
Qiskit — the upstream ``wuyue`` package is never imported.  Self-registers
with :class:`ProviderRegistry` so that ``ProviderRegistry.get("wuyue")``
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
from .backend import WuYueQuantumBackend, WuYueSimulatorBackend
from .client import WuYueApiClient


class WuYueProvider(Provider):
    """Cloud-provider implementation for WuYue."""

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
        return "wuyue"

    def _create_api_client(self) -> WuYueApiClient:
        # WUYUE_TOKEN is the "accessKey+secretKey" pair the Ecloud AK/SK
        # scheme needs ("xxxx+yyyy", see .env-example).
        access_key = self.token.split("+")[0] if "+" in self.token else self.token
        secret_key = self.token.split("+")[1] if "+" in self.token else ""
        return WuYueApiClient(access_key=access_key, secret_key=secret_key)

    @staticmethod
    def _parse_wuyue_config(raw_api_data: dict) -> BackendConfiguration:
        """Normalize a raw WuYue engine dict into a BackendConfiguration."""
        backend_code = raw_api_data["code"]
        qubit_count = int(raw_api_data["n_qubits"])
        is_sim = raw_api_data["simulator"]
        label_tag = raw_api_data.get("labels", "1" if not is_sim else "0")

        # Map label field to backend type consistent with TianYan logic.
        backend_type = (
            BackendType.simulator if label_tag == "0" or is_sim
            else BackendType.quantum_computer
        )

        # WuYue's engine-list API returns no per-backend coupling/calibration,
        # so the Target is built fully-connected in the backend class.
        coupling_map = []

        # Basis the WuYue server compiles from standard OpenQASM 2.
        basis_gates = ["id", "h", "x", "y", "z", "rz", "ry", "rx", "cx", "cz", "measure", "barrier"]
        derivative_gates = []

        construct_data = {
            "derivative_gates": derivative_gates,
            "backend_type": backend_type,
            "raw": raw_api_data,
        }

        cfg_build_dict = {
            "backend_name": backend_code,
            "n_qubits": qubit_count,
            "simulator": is_sim,
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
        """List WuYue backends with optional filtering."""
        raw_backends = self._api_client.get_backends()
        result: list[Backend] = []
        for data in raw_backends:
            cfg = self._parse_wuyue_config(data)
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
                WuYueSimulatorBackend if cfg.simulator else WuYueQuantumBackend
            )
            result.append(backend_cls(configuration=cfg, api_client=self._api_client))
        return result

    def backend(self, name: str) -> Backend:
        """Retrieve a single WuYue backend by name."""
        for data in self._api_client.get_backends():
            if data.get("code") != name:
                continue
            cfg = self._parse_wuyue_config(data)
            backend_cls = (
                WuYueSimulatorBackend if cfg.simulator else WuYueQuantumBackend
            )
            return backend_cls(configuration=cfg, api_client=self._api_client)
        raise BackendNotFoundError(name)


# Self-register once the module is imported.
ProviderRegistry.register(WuYueProvider)
