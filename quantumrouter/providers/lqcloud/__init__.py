"""LQCloud provider package.

Uses only the LQCloud **remote request compute service** (submit / poll
circuit tasks) — the upstream ``lqcloud`` SDK and its bundled
``QuantumCircuit`` are deliberately not used.  Circuits are defined with
Qiskit exactly like every other QuantumRouter vendor, then serialized to
the LQCloud instruction IR by :mod:`quantumrouter.providers.lqcloud.backend.utils`
before submission.

Importing this package self-registers :class:`LQCloudProvider` with the
:class:`quantumrouter.provider.registry.ProviderRegistry` under the id
``"lqcloud"``.
"""

from .provider import LQCloudProvider

__all__ = ["LQCloudProvider"]
