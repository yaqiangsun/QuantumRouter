"""IBM Quantum provider.

Concrete :class:`Provider` for IBM Quantum Platform. Uses the
official ``qiskit-ibm-provider`` SDK to reach IBM Quantum, and
self-registers with :class:`ProviderRegistry` so that
``ProviderRegistry.get("ibm")`` resolves once this package is
imported.

The ``ConnectionConfig`` carries the auth token, instance specifier
(in ``extra``), and request deadline. The IBM SDK owns its own
HTTPS transport — see :mod:`.client` for why.
"""

from __future__ import annotations

import os

from ...backend.base import Backend
from ...backend.configuration import BackendConfiguration
from ...config import ConnectionConfig
from ...exceptions import BackendNotFoundError, QuantumRouterError
from ...provider.base import Provider
from ...provider.registry import ProviderRegistry
from ...types import BackendStatus
from .backend import IBMQuantumBackend, IBMSimulatorBackend
from .client import IBMApiClient


class IBMProvider(Provider):
    """Cloud-provider implementation for IBM Quantum."""

    def __init__(
        self,
        connection: ConnectionConfig,
        *,
        token: str | None = None,
    ) -> None:
        # IBM Quantum auth uses an account-level API token. The
        # connection URL is informational — the SDK owns transport —
        # but we honor ``token`` from the call site, then the
        # environment, then raise.
        token = token or os.environ.get("IBM_QUANTUM_TOKEN", "")
        if not token:
            raise QuantumRouterError(
                "IBM provider requires a token. Set IBM_QUANTUM_TOKEN "
                "or pass token=... to create_provider."
            )

        # IBM Quantum instance: e.g. ibmquantum/open/online/dev.
        # Set before super().__init__() — that builds the API client,
        # which needs the instance specifier.
        self._instance = connection.extra.get("instance") or None
        super().__init__(connection=connection, token=token)

    @classmethod
    def name(cls) -> str:
        return "ibm"

    def _create_api_client(self) -> IBMApiClient:
        return IBMApiClient(
            connection=self.connection,
            token=self.token,
            instance=self._instance,
        )

    def backends(
        self,
        *,
        simulator: bool | None = None,
        online: bool = True,
        name: str | None = None,
    ) -> list[Backend]:
        """List IBM Quantum backends with optional filtering."""
        raw_backends = self._api_client.get_backends(
            simulator=simulator if simulator is not None else False,
        )

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
                    IBMSimulatorBackend(
                        configuration=cfg,
                        api_client=self._api_client,
                    )
                )
            else:
                result.append(
                    IBMQuantumBackend(
                        configuration=cfg,
                        api_client=self._api_client,
                    )
                )
        return result

    def backend(self, name: str) -> Backend:
        """Retrieve a single IBM Quantum backend by name."""
        for data in self._api_client.get_backends():
            if data.get("code") != name:
                continue
            cfg = BackendConfiguration.from_api(data, self._api_client)
            if cfg.simulator:
                return IBMSimulatorBackend(
                    configuration=cfg,
                    api_client=self._api_client,
                )
            return IBMQuantumBackend(
                configuration=cfg,
                api_client=self._api_client,
            )
        raise BackendNotFoundError(name)


# Self-register once the module is imported.
ProviderRegistry.register(IBMProvider)
