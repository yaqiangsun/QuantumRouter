"""TianYan quantum-cloud provider.

Self-registers with :class:`ProviderRegistry` on import so that
``ProviderRegistry.get("TianYan")`` resolves after
``import quantumrouter.providers.TianYan``.

Endpoint paths and auth headers are defined in :mod:`config` so that
the 172.29.220.35 simulation server and qc.zdxlz.com cloud can be
swapped without touching client logic.
"""

from .client import TianYanApiClient
from .provider import TianYanProvider

__all__ = ["TianYanApiClient", "TianYanProvider"]
