"""Example — PCIe transport (direct-to-hardware).

Run with::

    python examples/pcie_transport.py

This example shows how the **same** ``create_provider`` entry point
selects a PCIe transport instead of an HTTP one — the only change
is the URL scheme (``pcie://`` instead of ``http://``).

The PCIe transport is currently a placeholder that raises
``TransportNotImplementedError``. Once the hardware integration is
finished (mapping BARs, building command frames in
``transport/pcie.py``), this example runs as-is — no API changes.

To run against the HTTP simulation server first, set::

    LINGYUN_URL=http://xx.xxxx.xx:xxxx
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

# Allow running this example without installing the package:
# ``python examples/pcie_transport.py``
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import quantumrouter  # noqa: E402 - path adjusted above
from quantumrouter.exceptions import TransportNotImplementedError  # noqa: E402


def main() -> None:
    # ``pcie:///dev/quantum0`` selects the PCIe transport via
    # ConnectionConfig.from_url(), and create_provider forwards the
    # resulting ConnectionConfig to the LingYunProvider.
    pcie_url = os.environ.get("LINGYUN_PCIE_URL", "pcie:///dev/quantum0")

    print(f"Transport URL: {pcie_url}")
    cfg = quantumrouter.ConnectionConfig.from_url(pcie_url)
    print(f"Inferred transport type: {cfg.transport_type.value}")
    print()

    try:
        provider = quantumrouter.create_provider(
            backend="lingyun",
            url=pcie_url,
        )
    except TransportNotImplementedError as exc:
        print(f"PCIe transport is not yet implemented:\n  {exc}")
        print("\nFalling back to HTTP for this demo...")
        provider = quantumrouter.create_provider(
            backend="lingyun",
            url=os.environ.get("LINGYUN_URL", "http://xx.xxxx.xx:xxxx"),
        )

    try:
        backends = provider.backends(online=True)
    except quantumrouter.QuantumRouterError as exc:
        print(f"Could not reach the server:\n  {exc}")
        return

    print(f"Backends ({len(backends)}):")
    for b in backends:
        print(f"  - {b.name} ({'simulator' if b.is_simulator else 'quantum'})")


if __name__ == "__main__":
    main()
