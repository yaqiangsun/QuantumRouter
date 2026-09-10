"""Cloud-vendor implementations for QuantumRouter.

This package is a **pure vendor directory**: each subpackage implements
one quantum-cloud vendor (LingYun, IBM Quantum, ...) and self-registers
it with :class:`quantumrouter.provider.ProviderRegistry`.

The vendor-agnostic ``Provider`` abstract base, the registry, and the
:func:`create_provider` factory live in :mod:`quantumrouter.provider` —
sibling to :mod:`quantumrouter.backend` and :mod:`quantumrouter.transport`.

Vendor subpackages are imported **lazily**. Each one pulls in heavy,
vendor-specific third-party deps (``qiskit``, ``numpy`` ...)
at import time. Loading them eagerly here would force a user who only
wants LingYun to also install IBM's, TianYan's, and Wuyue's deps.

A provider self-registers once its subpackage is imported, which users
can do any of three ways::

    import quantumrouter.providers.lingyun as _lingyun  # explicit
    quantumrouter.providers.lingyun                      # attribute
    # or via the helper:
    import quantumrouter
    quantumrouter.create_provider("lingyun", url=...)    # lazy-imports

Accessing ``quantumrouter.providers.<vendor>`` triggers
:func:`importlib.import_module` on first use, so the import (and the
self-register side effect) happens at most once per vendor.
"""

from __future__ import annotations

import importlib

# Subpackages known to live under this package. ``__getattr__`` uses
# this set to decide whether an unknown attribute is a lazy vendor
# import or a genuine ``AttributeError``. Add new vendor ids here.
_VENDOR_PACKAGES = {"ibm", "lingyun", "tianyan", "wuyue"}


def __getattr__(name: str):
    """Lazily import a vendor subpackage on first attribute access.

    Also self-registers the vendor with :class:`ProviderRegistry`
    (via the side effect of the subpackage's own ``__init__``).
    """
    if name in _VENDOR_PACKAGES:
        return importlib.import_module(f".{name}", __name__)
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


def __dir__() -> list[str]:
    """Expose vendor ids so ``dir(...)`` and autocompletion work."""
    return sorted(_VENDOR_PACKAGES)
