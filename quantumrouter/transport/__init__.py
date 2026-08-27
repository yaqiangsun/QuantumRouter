"""Transport layer for QuantumRouter.

A *transport* knows how to turn a :class:`TransportRequest` into a
:class:`TransportResponse` using exactly one wire mechanism (HTTP,
PCIe, ...). The layer is vendor-agnostic — provider-specific paths,
auth headers, and response shapes live under
``quantumrouter/providers/<vendor>/``.
"""

from .base import Transport, TransportRequest, TransportResponse
from .factory import create_transport
from .http import HttpTransport
from .pcie import PcieTransport

__all__ = [
    "Transport",
    "TransportRequest",
    "TransportResponse",
    "create_transport",
    "HttpTransport",
    "PcieTransport",
]
