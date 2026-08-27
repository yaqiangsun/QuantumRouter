"""Cross-cutting types and enums for QuantumRouter.

These types are vendor-agnostic. Anything specific to a cloud provider
lives under ``quantumrouter/providers/<vendor>/``.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class TransportType(str, Enum):
    """Underlying wire mechanism used to reach a quantum service."""

    HTTP = "http"
    PCIE = "pcie"

    @classmethod
    def from_url(cls, url: str) -> "TransportType":
        """Infer a transport type from a connection-string scheme."""
        lowered = url.lower()
        if lowered.startswith(("http://", "https://")):
            return cls.HTTP
        if lowered.startswith("pcie://"):
            return cls.PCIE
        raise ValueError(
            f"Cannot infer transport from url: {url!r}. "
            "Expected 'http://', 'https://', or 'pcie://'."
        )


class BackendStatus(str, Enum):
    """Lifecycle state of a quantum backend, as reported by its provider."""

    UNKNOWN = "unknown"
    OFFLINE = "offline"
    ONLINE = "online"
    RUNNING = "running"
    CALIBRATING = "calibrating"


class JobStatus(str, Enum):
    """Lifecycle state of a submitted quantum job."""

    UNKNOWN = "unknown"
    PENDING = "pending"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    CANCELLED = "cancelled"


@dataclass(frozen=True)
class ApiResponse:
    """Parsed envelope common to most quantum-cloud REST responses.

    Providers whose responses don't fit this shape can return their own
    dataclass from their transport layer; ``ApiResponse`` is a default.
    """

    code: int
    msg: str
    data: object
