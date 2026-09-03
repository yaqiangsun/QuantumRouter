"""Cloud-vendor implementations for QuantumRouter.

This package is a **pure vendor directory**: each subpackage implements
one quantum-cloud vendor (LingYun, IBM Quantum, ...) and self-registers
it with :class:`quantumrouter.provider.ProviderRegistry`.

The vendor-agnostic ``Provider`` abstract base, the registry, and the
:func:`create_provider` factory live in :mod:`quantumrouter.provider` —
sibling to :mod:`quantumrouter.backend` and :mod:`quantumrouter.transport`.

Importing this package imports all registered vendors so that
``ProviderRegistry.all()`` is populated without user action.
"""

from . import ibm as _ibm  # noqa: F401 - self-register side effect
from . import lingyun as _lingyun  # noqa: F401 - self-register side effect
from . import tianyan as _tianyan