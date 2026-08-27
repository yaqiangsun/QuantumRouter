"""Abstract base class for all transports.

Transports are the lowest layer in the stack: they own the connection
(socket, device handle, ...) and exchange opaque request/response
blobs with the remote quantum service. Everything above them — API
client, provider, backend — speaks in terms of :class:`TransportRequest`
and :class:`TransportResponse`.

This separation means a new wire mechanism (gRPC, serial, ...) is just
a new ``Transport`` subclass; the business layers don't change.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field


@dataclass
class TransportRequest:
    """Vendor-agnostic request carried across a transport.

    Fields are deliberately broad so provider code can populate only
    what its service expects.
    """

    url: str
    method: str = "GET"
    json: dict | None = None
    params: dict | None = None
    headers: dict | None = None
    data: bytes | None = None
    timeout: float = 30.0


@dataclass
class TransportResponse:
    """Raw response from a transport, plus a parsed view if possible."""

    status_code: int
    raw: bytes
    json_data: dict | None = None
    headers: dict = field(default_factory=dict)

    def json(self) -> dict:
        """Return the parsed JSON body, raising if it's absent/invalid."""
        if self.json_data is None:
            raise ValueError("Response body is not valid JSON or is empty")
        return self.json_data


class Transport(ABC):
    """Interface for request/response transports.

    Implementations should be safe to re-open and re-close. ``request``
    may assume :meth:`open` has been called, but it's good practice to
    open lazily on first request as well.
    """

    @abstractmethod
    def open(self) -> None:
        """Establish the underlying connection."""

    @abstractmethod
    def close(self) -> None:
        """Release the underlying connection. Idempotent."""

    @abstractmethod
    def request(self, req: TransportRequest) -> TransportResponse:
        """Send a request and return the raw response."""

    # ------------------------------------------------------------------ #
    # Context manager support
    # ------------------------------------------------------------------ #
    def __enter__(self) -> "Transport":
        self.open()
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        self.close()
