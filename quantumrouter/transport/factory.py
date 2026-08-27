"""Transport factory.

Selects the right transport implementation based on
:class:`ConnectionConfig.transport_type`. Keeps construction logic out
of the API client and provider layers.
"""

from __future__ import annotations

from ..config import ConnectionConfig
from ..exceptions import ConnectionError, QuantumRouterError
from ..types import TransportType
from .base import Transport
from .http import HttpTransport
from .pcie import PcieTransport


def create_transport(config: ConnectionConfig) -> Transport:
    """Create a transport instance for the given config.

    Parameters
    ----------
    config:
        A :class:`ConnectionConfig` describing how to reach the
        quantum service.

    Returns
    -------
    Transport
        An ``HttpTransport`` or ``PcieTransport`` instance. The caller
        owns the lifecycle — use ``with create_transport(...) as t:``
        or call ``open``/``close`` explicitly.

    Raises
    ------
    QuantumRouterError
        If the transport type is unsupported or the config is invalid
        for that transport.
    """
    if not isinstance(config, ConnectionConfig):
        raise QuantumRouterError(
            f"Expected ConnectionConfig, got {type(config).__name__}"
        )

    if config.transport_type is TransportType.HTTP:
        if not config.url:
            raise ConnectionError("HTTP transport needs a valid URL")
        return HttpTransport(
            base_url=config.url,
            timeout=config.timeout,
        )

    if config.transport_type is TransportType.PCIE:
        return PcieTransport(config=config)

    raise QuantumRouterError(
        f"Unsupported transport type: {config.transport_type!r}"
    )
