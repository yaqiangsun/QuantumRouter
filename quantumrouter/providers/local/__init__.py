"""Local Qiskit simulator provider (本地仿真).

Self-registers with :class:`ProviderRegistry` on import so that
``ProviderRegistry.get("local")`` resolves after
``import quantumrouter.providers.local``.

Unlike the cloud vendors this provider makes **no network request at all**:
its backend wraps Qiskit's core ``BasicSimulator``, so circuits run in-process
on the local machine. ``create_provider("local", ...)`` needs no URL, token,
or running server.
"""

from .provider import LocalProvider

__all__ = ["LocalProvider"]
