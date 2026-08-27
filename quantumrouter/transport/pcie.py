"""PCIe transport.

Placeholder for direct-to-hardware communication over PCIe. The
interface mirrors :class:`HttpTransport` so provider code is
transport-agnostic, but the methods raise
:class:`TransportNotImplementedError` until the hardware integration
is specced.

Expected shape once implemented
-------------------------------
- ``open``: open the device node (``/dev/quantum0``) and map BARs.
- ``close``: unmap BARs and close the file descriptor.
- ``request``: serialize the request into a command frame, write it
  via MMIO / DMA, poll for completion, and decode the response frame.
"""

from __future__ import annotations

from ..config import ConnectionConfig
from ..exceptions import TransportNotImplementedError
from .base import Transport, TransportRequest, TransportResponse


class PcieTransport(Transport):
    """Transport over a PCIe device node.

    Parameters
    ----------
    config:
        A :class:`ConnectionConfig` with ``transport_type == PCIE``.
        The ``pcie_device`` field carries the device node path.
    """

    def __init__(self, config: ConnectionConfig) -> None:
        self.config = config

    def open(self) -> None:
        """Open the PCIe device and map BARs.

        Raises
        ------
        TransportNotImplementedError
            Hardware integration not yet available.
        """
        raise TransportNotImplementedError(
            "PCIe transport is not yet implemented. "
            "Use an HTTP transport for now."
        )

    def close(self) -> None:
        """Unmap BARs and close the device handle.

        Raises
        ------
        TransportNotImplementedError
            Hardware integration not yet available.
        """
        raise TransportNotImplementedError(
            "PCIe transport is not yet implemented."
        )

    def request(self, req: TransportRequest) -> TransportResponse:
        """Send a command frame over PCIe and return the response.

        Raises
        ------
        TransportNotImplementedError
            Hardware integration not yet available.
        """
        raise TransportNotImplementedError(
            "PCIe transport is not yet implemented."
        )

    def __repr__(self) -> str:  # pragma: no cover - cosmetic
        dev = self.config.pcie_device or "<unspecified>"
        return f"PcieTransport(device={dev!r})"
