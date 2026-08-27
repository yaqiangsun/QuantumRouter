"""Abstract provider contract.

A provider represents one quantum-cloud vendor. It owns the
connection configuration, builds (or is handed) a transport, and
exposes ``backends()`` / ``backend()`` that return vendor-agnostic
``Backend`` instances.

Subclasses implement ``name()`` (vendor id) and the internal
``_create_api_client()`` hook that builds the vendor-specific client
which knows the endpoint paths and auth scheme. This base class
handles the rest.

This module is **vendor-agnostic**; concrete vendors live under
``quantumrouter/providers/<vendor>/``.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any

from ..config import ConnectionConfig
from ..exceptions import BackendNotFoundError
from ..backend.base import Backend  # noqa: F401 - re-exported for subclasses


class Provider(ABC):
    """Abstract base class for all cloud-provider implementations.

    Subclasses implement ``name()`` (vendor id) and
    ``_create_api_client()`` to build a transport-backed client. The
    public ``backends()`` / ``backend()`` methods are concrete and
    should not be overridden.
    """

    def __init__(
        self,
        connection: ConnectionConfig,
        *,
        token: str | None = None,
    ) -> None:
        self.connection = connection
        self.token = token
        self._api_client = self._create_api_client()

    # ------------------------------------------------------------------ #
    # Hooks for subclasses
    # ------------------------------------------------------------------ #
    @classmethod
    @abstractmethod
    def name(cls) -> str:
        """Return the provider's registry id (e.g. ``lingyun``)."""

    @abstractmethod
    def _create_api_client(self) -> Any:
        """Build the vendor-specific, transport-backed API client.

        The returned object is stored as ``self._api_client`` and
        passed to backends. Its type is vendor-specific, hence ``Any``.
        """

    # ------------------------------------------------------------------ #
    # Public API
    # ------------------------------------------------------------------ #
    @abstractmethod
    def backends(
        self,
        *,
        simulator: bool | None = None,
        online: bool = True,
        name: str | None = None,
    ) -> list[Backend]:
        """List backends offered by this provider.

        Parameters
        ----------
        simulator:
            Filter for simulator backends. None = no filter.
        online:
            When True, drop backends not in RUNNING/ONLINE state.
        name:
            Filter by backend name. None = no filter.
        """

    def backend(self, name: str) -> Backend:
        """Retrieve a single backend by name.

        Raises
        ------
        BackendNotFoundError
            If no backend with this name is found.
        """
        for backend in self.backends(online=False):
            if backend.name == name:
                return backend
        raise BackendNotFoundError(name)
