"""Exception hierarchy for QuantumRouter.

All exceptions raised by the package derive from :class:`QuantumRouterError`,
so callers can catch the full set with a single ``except``.
"""


class QuantumRouterError(Exception):
    """Base exception for the QuantumRouter package."""


class TransportError(QuantumRouterError):
    """Raised when a transport cannot send/receive a request."""


class TransportNotImplementedError(TransportError):
    """Raised when a transport path is defined but not yet implemented."""


class ConnectionError(TransportError):  # noqa: A001 - intentional name
    """Raised when a transport cannot be opened."""


class TimeoutError(TransportError):  # noqa: A001 - intentional name
    """Raised when a transport request exceeds its deadline."""


class ProtocolError(QuantumRouterError):
    """Raised when a response violates the expected protocol."""


class ProviderError(QuantumRouterError):
    """Raised when a cloud provider rejects the request."""


class ProviderNotFoundError(ProviderError):
    """Raised when an unknown provider name is looked up."""

    def __init__(self, name: str) -> None:
        self.name = name
        super().__init__(f"Provider '{name}' not found")


class BackendNotFoundError(ProviderError):
    """Raised when an unknown backend name is looked up."""

    def __init__(self, name: str) -> None:
        self.name = name
        super().__init__(f"Backend '{name}' not found")
