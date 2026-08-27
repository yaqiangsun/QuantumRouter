"""IBM Quantum provider (IBM Quantum Platform).

Self-registers with :class:`quantumrouter.provider.ProviderRegistry`
so that ``ProviderRegistry.get("ibm")`` resolves after
``import quantumrouter.providers.ibm``.

This integration uses the official ``qiskit-ibm-provider`` SDK,
which manages its own HTTP transport to IBM Quantum. As a result,
the transport-aware ``ConnectionConfig`` is used only for
``open()``/``close()`` lifecycle and instance resolution — the SDK
owns the wire layer.

Circuits are accepted as OpenQASM strings (the IBM Runtime native
serialized form).
"""

from .backend import IBMBackend, IBMSimulatorBackend
from .client import IBMApiClient
from .provider import IBMProvider

__all__ = [
    "IBMApiClient",
    "IBMBackend",
    "IBMSimulatorBackend",
    "IBMProvider",
]
