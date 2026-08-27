"""Backend configuration data.

A :class:`BackendConfiguration` carries everything a provider learns
about a backend at listing time — its name, status, whether it's a
simulator, plus vendor-specific fields under ``data``. The class also
knows how to build itself from a raw provider API response, so
provider code can stay thin.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from ..exceptions import QuantumRouterError
from ..types import BackendStatus


@dataclass
class BackendConfiguration:
    """Vendor-agnostic description of one quantum backend.

    Parameters
    ----------
    backend_name:
        The machine identifier the provider uses in its API
        (e.g. ``lingyun_sw_176_001``).
    simulator:
        True if the backend is a simulator rather than a real chip.
    status:
        Current lifecycle state, as far as listing can tell.
    data:
        The raw dict the provider returned. Concrete providers reach
        into this for vendor-specific fields they need later.
    """

    backend_name: str
    simulator: bool
    status: BackendStatus = BackendStatus.UNKNOWN
    data: dict = field(default_factory=dict)

    @classmethod
    def from_api(
        cls,
        data: dict,
        api_client: Any = None,  # accepted for symmetry, unused by default
    ) -> "BackendConfiguration":
        """Build a config from a provider's raw API response.

        The default implementation expects a small envelope::

            {
                "code": "lingyun_sw_176_001",
                "simulator": True,
                "status": "running" | "online" | ...
            }

        Providers with a different shape can override this method or
        pass a pre-built config directly.
        """
        try:
            backend_name = data["code"]
        except KeyError as exc:
            raise QuantumRouterError(
                f"Backend API response missing 'code': {data!r}"
            ) from exc

        simulator = bool(data.get("simulator", False))
        raw_status = data.get("status", "unknown")
        try:
            status = BackendStatus(raw_status)
        except ValueError:
            status = BackendStatus.UNKNOWN

        return cls(
            backend_name=backend_name,
            simulator=simulator,
            status=status,
            data=data,
        )
