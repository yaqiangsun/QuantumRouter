"""LingYun quantum-cloud provider (凌云).

Self-registers with :class:`ProviderRegistry` on import so that
``ProviderRegistry.get("lingyun")`` resolves after
``import quantumrouter.providers.lingyun``.

Endpoint paths and auth headers are defined in :mod:`config` so that
the xx.xx.xx.xx simulation server and qc.zdxlz.com cloud can be
swapped without touching client logic.
"""

from .client import LingYunApiClient
from .provider import LingYunProvider

__all__ = ["LingYunApiClient", "LingYunProvider"]
