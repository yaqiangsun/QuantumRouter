"""Backend configuration data.
A :class:`BackendConfiguration` carries everything a provider learns
about a backend at listing time — its name, status, whether it's a
simulator, plus vendor-specific fields under ``data``. The class also
knows how to build itself from a raw provider API response, so
provider code can stay thin.
"""
from __future__ import annotations
from dataclasses import dataclass, field
from typing import Any, Optional, List
from ..exceptions import QuantumRouterError
from ..types import BackendStatus, BackendType

@dataclass
class BackendConfiguration:
    """Vendor-agnostic description of one quantum backend.
    Parameters
    ----------
    backend_name:
        The machine identifier the provider uses in its API
        (e.g. ``lingyun_sw_176_001``).
    n_qubits:
        Max physical qubit count of hardware
    simulator:
        True if the backend is a simulator rather than a real chip.
    coupling_map:
        Hardware qubit coupling topology list
    basis_gates:
        Native hardware base gate list for transpile
    status:
        Current lifecycle state, as far as listing can tell.
    data:
        The raw dict the provider returned. Concrete providers reach
        into this for vendor-specific fields they need later.
    """
    def __init__(
        self,
        backend_name: str,
        n_qubits: int,
        simulator: bool,
        coupling_map: Optional[List[List[int]]] = None,
        basis_gates: Optional[List[str]] = None,
        status: BackendStatus = None,
        data: Optional[dict] = None,
    ):
        """Initializes the BackendConfiguration instance."""
        self.backend_name = backend_name
        self.simulator = simulator
        self.status = status
        self.data = data
        self.n_qubits = n_qubits
        self.coupling_map = coupling_map
        self.basis_gates = basis_gates

    @classmethod
    def from_api(
        cls,
        data: dict,
        api_client: Any = None,  # accepted for symmetry, unused by default
    ) -> "BackendConfiguration":
        """Base universal parser for general platforms(LingYun/WuYue).
        TianYan will override this logic inside its provider.
        """
        # print("[INFO] configuration.py data.keys(): ", data.keys())
        
        try:
            n_qubits = data['bitWidth']
        except KeyError as exc:
            raise QuantumRouterError(
                f"Backend API response missing 'bitWidth': {data!r}"
            ) from exc
        
        try:
            backend_name = data["code"]
        except KeyError as exc:
            raise QuantumRouterError(
                f"Backend API response missing 'code': {data!r}"
            ) from exc
        if data['labels'] == '1':
            backend_type = BackendType.quantum_computer
        else:
            backend_type = BackendType.simulator
        simulator = backend_type == BackendType.simulator
        raw_status = data.get("status", "unknown")
        try:
            status = BackendStatus(raw_status)
        except ValueError:
            status = BackendStatus.UNKNOWN
        return cls(
            backend_name=backend_name,
            simulator=simulator,
            status=status,
            data=data,
            n_qubits=n_qubits,
            coupling_map=None,
            basis_gates=None
        )

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "BackendConfiguration":
        """Normalized dict construction util for vendor custom parser."""
        return cls(**data)
