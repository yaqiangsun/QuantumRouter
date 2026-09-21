# -*- coding: utf-8 -*-
# Copyright (c) 2026 yaqiang.sun.
# This source code is licensed under the license found in the LICENSE file
# in the root directory of this source tree.
#########################################################################
# Author: yaqiangsun
# Created Time: 2026/08/25 12:23:21
########################################################################

"""QuantumRouter — Unified interface for quantum cloud providers.

One API, any backend. The package exposes the vendor-agnostic
contract; concrete vendors live under ``quantumrouter/providers/<vendor>/``
and self-register on import.

Switching cloud vendors is a one-parameter change — the calling code
stays identical.

Example
-------
>>> import quantumrouter
>>> provider = quantumrouter.create_provider(
...     backend="xxx",                       # change this to switch vendors
...     url="http://xx.xx.xx.xx:xx",
...     token="...",                             # optional for the simulation server
... )
>>> backends = provider.backends(online=True)
>>> b = backends[0]
>>> b.submit_job(["H 0"])
['task_1']
>>> b.query_job(["task_1"])
[{'task': 'task_1'}]

Switching to another vendor::

    provider = quantumrouter.create_provider(backend="ibm", url="https://...")

Working with a PCIe-attached card instead of a cloud service::

    provider = quantumrouter.create_provider(
        backend="xxx", url="pcie:///dev/quantum0",
    )

Sampling circuits through Qiskit's primitives interface::

    sampler = quantumrouter.Sampler(b, default_shots=4096)
    result = sampler.run([(circuit, params)]).result()
    counts = result[0].data.meas.get_counts()
"""

from __future__ import annotations

__version__ = "0.0.7"

# --- Version ------------------------------------------------------------
# (defined above for hatchling dynamic-version discovery)

# --- Errors -------------------------------------------------------------
from .exceptions import (
    BackendNotFoundError,
    ConnectionError,
    ProtocolError,
    ProviderError,
    ProviderNotFoundError,
    QuantumRouterError,
    TimeoutError,
    TransportError,
    TransportNotImplementedError,
)

# --- Core types ---------------------------------------------------------
from .types import (
    ApiResponse,
    BackendStatus,
    JobStatus,
    TransportType,
)

# --- Connection / transport --------------------------------------------
from .config import ConnectionConfig
from .transport import (
    HttpTransport,
    PcieTransport,
    Transport,
    TransportRequest,
    TransportResponse,
    create_transport,
)

# --- Backend / provider -------------------------------------------------
from .backend import Backend, BackendConfiguration
from .provider import (
    Provider,
    ProviderRegistry,
    create_provider,
    get_provider,
    register_provider,
)

# Import the providers package (but NOT any vendor subpackage) so
# that ``quantrouter.providers.lingyun`` triggers the lazy
# ``__getattr__`` in providers/__init__.py. Each vendor subpackage
# pulls in heavy, vendor-specific third-party deps (qiskit,
# numpy, ...). Importing them eagerly would force every user to
# install every vendor's deps even if they only use one.
#
# Providers self-register with :class:`ProviderRegistry` once
# their package is explicitly imported by the user, e.g.::
#
#     import quantumrouter.providers.lingyun as _lingyun  # self-register
#     # or, equivalently, attribute access triggers lazy import:
#     quantumrouter.providers.lingyun
from . import providers  # noqa: F401 - exposes lazy __getattr__ on attribute access

# --- Primitives ---------------------------------------------------------
# ``Sampler`` adapts a QuantumRouter backend to Qiskit's ``BaseSamplerV2``
# interface so user code — including libraries such as
# ``qiskit-machine-learning`` — can treat a backend like any other Qiskit
# backend.
#
# This import is eager, unlike the vendor subpackages above. The vendor
# laziness exists to avoid forcing *optional, vendor-specific* deps
# (``cqlib-adapter``, ``wuyue``, ...) on users who don't need them. The
# primitives adapter has no such deps: it needs only ``qiskit`` and
# ``numpy``, and ``qiskit`` is already imported eagerly by
# :mod:`quantumrouter.backend` (and pulls in ``qiskit.primitives``
# itself). Laziness would buy nothing here.
from .sampler import Sampler

__all__ = [
    "__version__",
    # Errors
    "QuantumRouterError",
    "TransportError",
    "TransportNotImplementedError",
    "ConnectionError",
    "TimeoutError",
    "ProtocolError",
    "ProviderError",
    "ProviderNotFoundError",
    "BackendNotFoundError",
    # Core types
    "TransportType",
    "BackendStatus",
    "JobStatus",
    "ApiResponse",
    # Connection / transport
    "ConnectionConfig",
    "Transport",
    "TransportRequest",
    "TransportResponse",
    "HttpTransport",
    "PcieTransport",
    "create_transport",
    # Backend / provider
    "Backend",
    "BackendConfiguration",
    "Provider",
    "ProviderRegistry",
    "create_provider",
    "register_provider",
    "get_provider",
    # Primitives
    "Sampler",
]
