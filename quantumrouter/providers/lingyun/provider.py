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
from ...types import BackendStatus
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
        self.connection = connection
        self.token = token or ""
        self._transport = create_transport(connection)
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
            cfg = BackendConfiguration.from_api(data, self._api_client)

            if online and cfg.status not in (
                BackendStatus.RUNNING,
                BackendStatus.ONLINE,
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
            cfg = BackendConfiguration.from_api(data, self._api_client)
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
