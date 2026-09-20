"""Quafu quantum-cloud provider.

Self-registers with :class:`ProviderRegistry` on import so that
``ProviderRegistry.get("quafu")`` resolves after
``import quantumrouter.providers.quafu``.

Uses only Quafu's remote request compute service: circuits are defined
with Qiskit, converted to OpenQASM 2, and submitted to the Quafu cloud
via :class:`QuafuApiClient`. The upstream ``pyquafu`` package (and its
bundled ``QuantumCircuit`` / local ``simulate``) is intentionally not
imported.

Endpoint paths and auth headers are defined in :mod:`config` so the
server can be swapped without touching client logic.
"""

from .client import QuafuApiClient
from .job import QuafuJob
from .provider import QuafuProvider

__all__ = ["QuafuApiClient", "QuafuJob", "QuafuProvider"]
