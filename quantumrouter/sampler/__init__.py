"""Qiskit primitives adapters.

QuantumRouter backends implement the vendor-agnostic
:class:`~quantumrouter.backend.Backend` contract and speak each vendor's
own wire protocol, so they cannot inherit from Qiskit's primitives
directly. This package adapts a backend to Qiskit's ``BaseSamplerV2``
interface, so user code — including libraries such as
``qiskit-machine-learning`` — can treat a QuantumRouter backend like any
other Qiskit backend.

The adapter is re-exported at the package root, so both of these work::

    import quantumrouter
    sampler = quantumrouter.Sampler(backend)

    from quantumrouter.sampler import Sampler

Example
-------
>>> import quantumrouter
>>> backend = quantumrouter.create_provider(
...     backend="lingyun", url="http://127.0.0.1:8000"
... ).backend("lingyun_001")
>>> sampler = quantumrouter.Sampler(backend, default_shots=4096)
>>> result = sampler.run([(circuit, params)]).result()
"""

from .base import Sampler

__all__ = ["Sampler"]
