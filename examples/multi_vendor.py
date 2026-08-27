"""Example — switching cloud vendors without changing calling code.

Run with::

    python examples/multi_vendor.py

This is the key design goal of QuantumRouter: switch from LingYun
(a local simulation server) to IBM Quantum (the real IBM Quantum
Platform) by changing **one parameter** in ``create_provider``.
Everything below — listing backends, submitting jobs, querying
results — stays identical.

Environment
-----------
LingYun::

    LINGYUN_TOKEN=...                # optional for the simulation server
    LINGYUN_URL=http://xx.xx.xx.xx:xxxx

IBM Quantum::

    IBM_QUANTUM_TOKEN=...            # required
    IBM_INSTANCE=ibmquantum/open/... # optional; account default otherwise

The IBM provider uses the official ``qiskit-ibm-provider`` SDK,
which owns its HTTPS transport. Install it with::

    pip install qiskit-ibm-provider
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

# Allow running this example without installing the package:
# ``python examples/multi_vendor.py``
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import quantumrouter  # noqa: E402 - path adjusted above
from quantumrouter.exceptions import ProviderNotFoundError  # noqa: E402


def workflow(provider: quantumrouter.Provider) -> None:
    """Vendor-agnostic workflow: list, submit, query.

    The same code runs against any registered provider. Circuit
    format is vendor-specific (LingYun uses QCIS, IBM uses
    OpenQASM) — the caller supplies the right string.
    """
    try:
        backends = provider.backends(online=True)
    except quantumrouter.QuantumRouterError as exc:
        # Network / auth failures are expected when running this
        # example offline against a simulation server.
        print(f"[{provider.__class__.__name__}] backends request failed: {exc}")
        return

    print(f"[{provider.__class__.__name__}] backends: "
          f"{[b.name for b in backends]}")

    if not backends:
        return

    backend = backends[0]
    task_ids = backend.submit_job(["QINIT 4\nH 0"], shots=512)
    print(f"[{provider.__class__.__name__}] task_ids: {task_ids}")

    results = backend.query_job(task_ids)
    print(f"[{provider.__class__.__name__}] results: {results}")


def main() -> None:
    # ------------------------------------------------------------------ #
    # LingYun — local simulation server.
    # ------------------------------------------------------------------ #
    try:
        lingyun = quantumrouter.create_provider(
            backend="lingyun",
            url=os.environ.get("LINGYUN_URL", "http://xx.xx.xx.xx:xxxx"),
            token=os.environ.get("LINGYUN_TOKEN", ""),
        )
        workflow(lingyun)
    except Exception as exc:  # noqa: BLE001 - demo: tolerate offline
        print(f"[LingYun] demo skipped (needs a reachable server): {exc}")

    print()

    # ------------------------------------------------------------------ #
    # IBM Quantum — IBM Quantum Platform via the qiskit-ibm-provider SDK.
    # Same ``create_provider`` call, same ``workflow`` — only the
    # backend name, URL, and token change.
    # ------------------------------------------------------------------ #
    try:
        ibm = quantumrouter.create_provider(
            backend="ibm",
            url="https://quantum-computing.ibm.com",  # informational; SDK owns transport
            token=os.environ.get("IBM_QUANTUM_TOKEN", ""),
            instance=os.environ.get("IBM_INSTANCE"),  # passed via ConnectionConfig.extra
        )
        workflow(ibm)
    except ProviderNotFoundError:
        print("[IBM Quantum] not implemented yet. "
              "Add quantumrouter/providers/ibm/ to enable.")
    except quantumrouter.QuantumRouterError as exc:
        print(f"[IBM Quantum] demo skipped: {exc}")

    print()
    print("Registered providers:", list(quantumrouter.ProviderRegistry.all().keys()))


if __name__ == "__main__":
    main()
