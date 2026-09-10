"""WuYue provider.
Concrete :class:`Provider` for the WuYue quantum-cloud.
All low-level Transport logic removed; network, auth, request assembly
delegated to WuYuePlatform wrapped inside WuYueApiClient.
Self-registers with :class:`ProviderRegistry` so that
``ProviderRegistry.get("WuYue")`` resolves once this package is imported.
"""
from __future__ import annotations
from ...provider.base import Provider
from ...provider.registry import ProviderRegistry
from ...backend.base import Backend
from ...backend.configuration import BackendConfiguration
from ...config import ConnectionConfig
from ...exceptions import BackendNotFoundError
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
        return "wuyue" # lower case

    def _create_api_client(self) -> WuYueApiClient:
        access_key = self.token.split("+")[0] if "+" in self.token else self.token
        secret_key = self.token.split("+")[1] if "+" in self.token else ""
        return WuYueApiClient(access_key=access_key, secret_key=secret_key)

    def backends(
        self,
        *,
        simulator: bool | None = None,
        online: bool = True,
        name: str | None = None,
    ) -> list[Backend]:
        """List WuYue backends with optional filtering."""
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
                result.append(
                    WuYueSimulatorBackend(
                        configuration=cfg,
                        api_client=self._api_client,
                    )
                )
            else:
                result.append(
                    WuYueQuantumBackend(
                        configuration=cfg,
                        api_client=self._api_client,
                    )
                )
        print("[INFO] provider.py result: ", result)
        return result

    def backend(self, name: str) -> Backend:
        """Retrieve a single WuYue backend by name."""
        for data in self._api_client.get_backends():
            if data.get("code") != name:
                continue
            cfg = BackendConfiguration.from_api(data, self._api_client)
            if cfg.simulator:
                return WuYueSimulatorBackend(
                    configuration=cfg,
                    api_client=self._api_client,
                )
            return WuYueQuantumBackend(
                configuration=cfg,
                api_client=self._api_client,
            )
        raise BackendNotFoundError(name)


# Self-register once the module is imported.
ProviderRegistry.register(WuYueProvider)
