"""Example — basic usage of the QuantumRouter package.

Run with::

    python examples/basic_usage.py

Before running, set your LingYun token (optional for the
simulation server)::

    set LINGYUN_TOKEN=...          # Windows
    export LINGYUN_TOKEN=...       # macOS / Linux

This example talks to the LingYun quantum-cloud platform over HTTP.
It uses ``create_provider``, the single entry point that keeps the
calling code identical when switching vendors.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

# Allow running this example without installing the package:
# ``python examples/basic_usage.py``
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import quantumrouter  # noqa: E402 - path adjusted above


def main() -> None:
    # ------------------------------------------------------------------ #
    # Build a provider from a connection string.
    # The transport (HTTP here) is inferred from the URL scheme.
    # ------------------------------------------------------------------ #
    provider = quantumrouter.create_provider(
        backend="lingyun",
        url="http://xx.xxxx.xx:xxxx",          # simulation server
        token=os.environ.get("LINGYUN_TOKEN", ""),
    )

    # ------------------------------------------------------------------ #
    # List available backends for this user.
    # This reaches the server; if it's not running we report and exit.
    # ------------------------------------------------------------------ #
    try:
        backends = provider.backends(online=True)
    except quantumrouter.QuantumRouterError as exc:
        print(f"Could not reach the server:\n  {exc}")
        print("\nSet LINGYUN_URL to a running simulation server and retry.")
        return

    print(f"Available backends ({len(backends)}):")
    for b in backends:
        kind = "simulator" if b.is_simulator else "quantum"
        print(f"  - {b.name} ({kind})")

    if not backends:
        print("No backends found. Check the URL / token.")
        return

    # ------------------------------------------------------------------ #
    # Pick one backend and submit a job.
    # ------------------------------------------------------------------ #
    backend = backends[0]

    # Pull this backend's calibration / hardware configuration.
    print(f"\nFetching configuration for {backend.name!r}...")
    config = backend.fetch_configuration()
    print(f"  keys: {list(config.keys())[:5]}...")

    # Submit a single-circuit job.
    # ``circuits`` are vendor-specific serialized circuit strings
    # (LingYun uses QCIS).
    circuit_str = "QINIT 4\nH 0"
    print("\nSubmitting job...")
    task_ids = backend.submit_job([circuit_str], shots=1024)
    print(f"  task_ids: {task_ids}")

    # ------------------------------------------------------------------ #
    # Query results.
    # ------------------------------------------------------------------ #
    print("\nQuerying results...")
    results = backend.query_job(task_ids)
    print(f"  results: {results}")


if __name__ == "__main__":
    main()
