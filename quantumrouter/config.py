"""Connection configuration for QuantumRouter.

A single ``ConnectionConfig`` describes everything a transport needs to
reach a quantum service, regardless of whether that service lives behind
an HTTP endpoint or a PCIe device. Use :meth:`from_url` for the common
case, or construct directly for fine-grained control.

Examples
--------
>>> cfg = ConnectionConfig.from_url("http://xx.xxxx.xx:xxxx")
>>> cfg.transport_type
<TransportType.HTTP: 'http'>

>>> cfg = ConnectionConfig.from_url("pcie:///dev/quantum0")
>>> cfg.transport_type
<TransportType.PCIE: 'pcie'>
"""

from __future__ import annotations

from dataclasses import dataclass, field
from urllib.parse import urlparse

from .exceptions import QuantumRouterError
from .types import TransportType


@dataclass
class ConnectionConfig:
    """Everything a transport needs to reach a quantum service.

    Parameters
    ----------
    transport_type:
        The wire mechanism to use. Determines which of the remaining
        fields are meaningful.
    host:
        Network hostname. Used for ``HTTP`` transports.
    port:
        Network port. Optional for ``HTTP`` transports.
    base_url:
        Fully-formed base URL. Takes precedence over ``host``/``port``
        when both are set. Used for ``HTTP`` transports.
    scheme:
        URL scheme override. Defaults inferred from ``transport_type``.
    pcie_device:
        Path to the PCIe device node. Used for ``PCIE`` transports.
    pcie_vendor_id, pcie_device_id:
        Optional identifiers to disambiguate multiple cards.
    timeout:
        Request deadline, in seconds. Shared by all transport types.
    extra:
        Free-form provider-specific options. Transport implementations
        should ignore keys they don't understand.
    """

    transport_type: TransportType
    host: str | None = None
    port: int | None = None
    base_url: str | None = None
    scheme: str | None = None
    pcie_device: str | None = None
    pcie_vendor_id: int | None = None
    pcie_device_id: int | None = None
    timeout: float = 30.0
    extra: dict = field(default_factory=dict)

    # ------------------------------------------------------------------ #
    # Construction helpers
    # ------------------------------------------------------------------ #
    @classmethod
    def from_url(cls, url: str, **overrides) -> "ConnectionConfig":
        """Parse a connection string into a config.

        Supported forms
        ---------------
        - ``http://host[:port]`` and ``https://host[:port]``
        - ``pcie://<device_path>`` (e.g. ``pcie:///dev/quantum0``)
        """
        if not isinstance(url, str) or not url:
            raise ValueError("url must be a non-empty string")

        parsed = urlparse(url)
        if not parsed.scheme:
            raise ValueError(f"Missing scheme in url: {url!r}")

        transport_type = TransportType.from_url(url)
        scheme = overrides.pop("scheme", parsed.scheme)
        timeout = overrides.pop("timeout", 30.0)

        if transport_type is TransportType.HTTP:
            host = overrides.pop("host", parsed.hostname)
            port = overrides.pop("port", parsed.port)
            return cls(
                transport_type=transport_type,
                host=host,
                port=port,
                base_url=f"{parsed.scheme}://{parsed.netloc}",
                scheme=scheme,
                timeout=timeout,
                extra=overrides,
            )

        # PCIe
        device = overrides.pop("pcie_device", None)
        if device is None:
            # ``pcie:///dev/quantum0`` -> parsed.path == "/dev/quantum0"
            device = parsed.path or None
        return cls(
            transport_type=transport_type,
            pcie_device=device,
            scheme=scheme,
            timeout=timeout,
            extra=overrides,
        )

    # ------------------------------------------------------------------ #
    # Runtime accessors
    # ------------------------------------------------------------------ #
    @property
    def url(self) -> str:
        """The fully-formed URL, for HTTP transports."""
        if self.base_url is not None:
            return self.base_url
        if self.host is None:
            raise QuantumRouterError("No host configured for HTTP transport")
        default_scheme = "https" if self.port == 443 else "http"
        scheme = self.scheme or default_scheme
        netloc = self.host if self.port is None else f"{self.host}:{self.port}"
        return f"{scheme}://{netloc}"

    def __post_init__(self) -> None:
        """Cross-validate fields after construction."""
        if self.transport_type is TransportType.HTTP and self.host is None and self.base_url is None:
            raise ValueError("HTTP transport needs a host or base_url")
        if self.transport_type is TransportType.PCIE and self.pcie_device is None:
            raise ValueError("PCIe transport needs a pcie_device")

    def __repr__(self) -> str:  # pragma: no cover - cosmetic
        if self.transport_type is TransportType.HTTP:
            return f"ConnectionConfig({self.url!r})"
        return f"ConnectionConfig(pcie://{self.pcie_device!r})"
