"""TianYan provider.
Concrete :class:`Provider` for the TianYan quantum-cloud.
All low-level Transport logic removed; network, auth, request assembly
delegated to cqlib.TianYanPlatform wrapped inside TianYanApiClient.
Self-registers with :class:`ProviderRegistry` so that
``ProviderRegistry.get("TianYan")`` resolves once this package is imported.
"""
from __future__ import annotations
from ...provider.base import Provider
from ...provider.registry import ProviderRegistry
from ...backend.base import Backend
from ...backend.configuration import BackendConfiguration
from ...config import ConnectionConfig
from ...exceptions import BackendNotFoundError
from .backend import TianYanQuantumBackend, TianYanSimulatorBackend
from .client import TianYanApiClient


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
        return "TianYan"

    def _create_api_client(self) -> TianYanApiClient:
        return TianYanApiClient(token=self.token)

    def backends(
        self,
        *,
        simulator: bool | None = None,
        online: bool = True,
        name: str | None = None,
    ) -> list[Backend]:
        """List TianYan backends with optional filtering."""
        raw_backends = self._api_client.get_backends()
        print("[INFO] provider.py raw_backends: ", raw_backends)
        result: list[Backend] = []
        for data in raw_backends:
            cfg = BackendConfiguration.from_api(data, self._api_client)

            # if online and cfg.status not in (
            #     BackendStatus.RUNNING,
            #     BackendStatus.ONLINE,
            #     BackendStatus.UNKNOWN
            # ):
            #     continue
            if simulator is not None and cfg.simulator != simulator:
                continue
            if name is not None and cfg.backend_name != name:
                continue
            print("[INFO] provider.py cfg.simulator: ", cfg.simulator)
            if cfg.simulator:
                print("[INFO] provider.py This is a simulator", TianYanSimulatorBackend(
                                        configuration=cfg,
                                        api_client=self._api_client,
                                    ))
                result.append(
                    TianYanSimulatorBackend(
                        configuration=cfg,
                        api_client=self._api_client,
                    )
                )
            else:
                print("[INFO] provider.py This is not a simulator", TianYanQuantumBackend(
                                        configuration=cfg,
                                        api_client=self._api_client,
                                    ))
                result.append(
                    TianYanQuantumBackend(
                        configuration=cfg,
                        api_client=self._api_client,
                    )
                )
        print("[INFO] provider.py result: ", result)
        return result

    def backend(self, name: str) -> Backend:
        """Retrieve a single TianYan backend by name."""
        for data in self._api_client.get_backends():
            if data.get("code") != name:
                continue
            cfg = BackendConfiguration.from_api(data, self._api_client)
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


# Self-register once the module is imported.
ProviderRegistry.register(TianYanProvider)
