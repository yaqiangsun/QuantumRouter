"""Provider layer for QuantumRouter.

A *provider* is the entry point for one quantum-cloud vendor
(LingYun, IBM Quantum, ...). It lists backends and hands them out,
delegating the actual request/response to a transport-backed client.

This package is **vendor-agnostic**: it holds the abstract
:class:`Provider`, the :class:`ProviderRegistry`, and the
:func:`create_provider` factory. Concrete vendors live under
``quantumrouter/providers/<vendor>/`` and self-register on import.
"""

from .base import Provider
from .registry import (
    ProviderRegistry,
    create_provider,
    get_provider,
    register_provider,
)

__all__ = [
    "Provider",
    "ProviderRegistry",
    "create_provider",
    "register_provider",
    "get_provider",
]
