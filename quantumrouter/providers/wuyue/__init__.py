"""WuYue quantum-cloud provider.

Self-registers with :class:`ProviderRegistry` on import so that
``ProviderRegistry.get("WuYue")`` resolves after
``import quantumrouter.providers.WuYue``.

Endpoint paths and auth headers are defined in :mod:`config` so that
the 172.29.220.35 simulation server and qc.zdxlz.com cloud can be
swapped without touching client logic.
"""

from .client import WuYueApiClient
from .provider import WuYueProvider
from .job import WuYueJob

__all__ = ["WuYueApiClient", "WuYueProvider", "WuYueJob"]
