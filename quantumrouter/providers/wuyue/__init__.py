"""WuYue provider package.

Uses only the WuYue **remote request compute service** (list engines /
submit / poll circuit tasks) — the upstream ``wuyue`` SDK and its bundled
``QuantumCircuit`` / simulator / gradient stack are deliberately not used.
Circuits are defined and transpiled with Qiskit exactly like every other
QuantumRouter vendor, then serialized to OpenQASM 2 by
:mod:`quantumrouter.providers.wuyue.backend.utils` before submission.

Importing this package self-registers :class:`WuYueProvider` with the
:class:`quantumrouter.provider.registry.ProviderRegistry` under the id
``"wuyue"``.
"""

from .provider import WuYueProvider

__all__ = ["WuYueProvider"]
