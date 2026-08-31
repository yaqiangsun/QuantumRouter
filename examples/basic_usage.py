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
import time

def main() -> None:
    # ------------------------------------------------------------------ #
    # Build a provider from a connection string.
    # The transport (HTTP here) is inferred from the URL scheme.
    # ------------------------------------------------------------------ #
    provider = quantumrouter.create_provider(
        backend="lingyun",
        url="http://xx.xx.xx.xx:8000",          # simulation server
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

    if not backends:
        print("No backends found. Check the URL / token.")
        return

    # ------------------------------------------------------------------ #
    # Pick one backend and submit a job.
    # ------------------------------------------------------------------ #
    backend = backends[0]

    # Pull this backend's calibration / hardware configuration.
    print(f"\nFetching configuration...")
    config = backend.fetch_configuration()
    print(f"  keys: {list(config.keys())[:5]}...")

    # from qiskit import QuantumCircuit
    # qc_raw = QuantumCircuit(7, 2, name="demo_circuit")
    # qc_raw.x(0)
    # qc_raw.x(0)
    # qc_raw.cz(0, 6)
    # qc_raw.measure(0, 0)
    # qc_raw.measure(6, 1)

    from qiskit import QuantumCircuit, QuantumRegister, ClassicalRegister
    qc_raw = QuantumCircuit(7, 2, name="demo_circuit")
    
    # 替换两个x(0)为H门，制造叠加态
    qc_raw.h(0)
    
    # CZ 纠缠门，Q0控制 Q6目标
    qc_raw.cz(0, 6)
    
    # 分别：测量 Q0、Q6 到经典位 0、1
    qc_raw.measure(0, 0)
    qc_raw.measure(6, 1)

    job = backend.run(
        run_input=[qc_raw],
        shots=1024,
        readout_calibration=True
    )
    task_id = job.job_id()
    print("\n[INFO] backend.run job: ", job)
    print("task_id: ", task_id)

    print("sleep for a while")
    time.sleep(5)

    res = job.result()
    print("[INFO] backend.run-----res: ", res)

    cnts = job.result().get_counts()
    print("[INFO] backend.run -----cnts: ", cnts)

    #---------------- segment ------------------
    # TODO:要从qcis字符串改为openqasm3
    # qcis字符串
    # circuit_str = "X Q1\nH Q0\nCX Q0 Q1\nRX Q0 1.5707963267948966\nRX Q1 -1.5707963267948966\nB Q0 Q1\nM Q0\nM Q1"
    # circuit_str = 
    # print("\nSubmitting job...")
    # task_ids = backend.submit_job([circuit_str], shots=1024, language="openqasm3")
    # print(f"  task_ids: {task_ids}")

    # time.sleep(3)

    # print("\nQuerying results...task_ids", task_ids)
    # results = backend.query_job(task_ids)
    # print(f"  results: {results}")


if __name__ == "__main__":
    main()
