"""Provider registry.

A single process-wide map from vendor id (``"lingyun"``, ...) to
provider class. Vendors self-register on import::

    # in providers/lingyun/__init__.py
    from ..provider.registry import ProviderRegistry
    from .provider import LingYunProvider
    ProviderRegistry.register(LingYunProvider)

User code (or the API client) then resolves by name without knowing
the concrete class.
"""

from __future__ import annotations

from ..config import ConnectionConfig
from ..exceptions import ProviderNotFoundError
from .base import Provider


class ProviderRegistry:
    """Process-wide registry of cloud providers."""

    _providers: dict[str, type[Provider]] = {}

    @classmethod
    def register(cls, provider_cls: type[Provider]) -> type[Provider]:
        """Register a provider class under its ``name()`` id.

        Re-registering the same name replaces the prior entry, so
        reloading a vendor module works.
        """
        name = provider_cls.name()
        cls._providers[name] = provider_cls
        return provider_cls

    @classmethod
    def get(cls, name: str) -> type[Provider]:
        """Look up a registered provider class by id."""
        try:
            return cls._providers[name]
        except KeyError as exc:
            raise ProviderNotFoundError(name) from exc

    @classmethod
    def all(cls) -> dict[str, type[Provider]]:
        """Return all registered providers."""
        return dict(cls._providers)


def register_provider(provider_cls: type[Provider]) -> type[Provider]:
    """Module-level convenience wrapper around ``ProviderRegistry.register``."""
    return ProviderRegistry.register(provider_cls)


def get_provider(name: str) -> type[Provider]:
    """Module-level convenience wrapper around ``ProviderRegistry.get``."""
    return ProviderRegistry.get(name)


def create_provider(
    backend: str,
    *,
    url: str | None = None,
    token: str | None = None,
    instance: str | None = None,
    **connection_overrides,
) -> Provider:
    """Build a configured, ready-to-use :class:`Provider` instance.

    This is the single entry point for switching cloud vendors: the
    caller picks a backend by name and (optionally) supplies the
    connection URL and auth token. Switching from LingYun to another
    vendor is a one-line change.

    Parameters
    ----------
    backend:
        Registered provider id, e.g. ``"lingyun"``.
    url:
        Connection string consumed by
        :class:`quantumrouter.config.ConnectionConfig.from_url`.
        When omitted, the provider may fall back to a vendor default.
    token:
        Auth token forwarded to the provider's client.
    instance:
        Optional provider-instance specifier (e.g. IBM Quantum
        ``ibmquantum/open/...``). Carried on ``ConnectionConfig.extra``.
    **connection_overrides:
        Extra fields forwarded to :meth:`ConnectionConfig.from_url`
        for vendor-specific needs.

    Raises
    ------
    ProviderNotFoundError
        If ``backend`` has not been registered.

    Example
    -------
    >>> p = create_provider("lingyun", url="http://xx.xxxx.xx:xxxx")
    >>> backends = p.backends()

    Switching to another vendor::

        p = create_provider("ibm", url="https://...")

    """
    provider_cls = ProviderRegistry.get(backend)
    if instance is not None:
        connection_overrides.setdefault("instance", instance)

    connection = (
        ConnectionConfig.from_url(url, **connection_overrides)
    )
    return provider_cls(connection=connection, token=token)
