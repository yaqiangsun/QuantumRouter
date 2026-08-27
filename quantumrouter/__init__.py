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
"""

from __future__ import annotations

__version__ = "0.0.1"

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

# Import all vendor packages so they self-register.
from .providers import lingyun as _lingyun  # noqa: F401 - self-register side effect

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
]
