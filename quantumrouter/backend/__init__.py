"""Generic quantum backend interface.

A *backend* is one quantum computer or simulator exposed by a
provider. This module defines the vendor-agnostic contract;
``quantumrouter/providers/<vendor>/backend.py`` supplies the concrete
subclass that wires the contract onto that vendor's API.

Keeping the contract here means the provider layer can hand back
``Backend`` objects to user code without leaking vendor-specific
types.
"""

from .base import Backend
from .configuration import BackendConfiguration

__all__ = ["Backend", "BackendConfiguration"]
