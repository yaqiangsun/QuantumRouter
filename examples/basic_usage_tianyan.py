"""Example — basic usage of the QuantumRouter package.

Run with::

    python examples/basic_usage.py

Before running, set your TianYan token (optional for the
simulation server)::

    set TianYan_TOKEN=...          # Windows
    export TianYan_TOKEN=...       # macOS / Linux

This example talks to the TianYan quantum-cloud platform over HTTP.
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
        backend="TianYan",
        token=os.environ.get("TianYan_TOKEN", "xxxxxxxxxx"),
    )

    # ------------------------------------------------------------------ #
    # List available backends for this user.
    # ------------------------------------------------------------------ #
    try:
        backends = provider.backends(online=True)
    except quantumrouter.QuantumRouterError as exc:
        print(f"Could not reach the server:\n  {exc}")
        print("\nSet TianYan_URL to a running simulation server and retry.")
        return

    print(f"Available backends ({len(backends)}):")

    if not backends:
        print("No backends found. Check the URL / token.")
        return
    # ------------------------------------------------------------------ #
    # Pick one backend and submit a job.
    # ------------------------------------------------------------------ #
        
    # backend = backends[0]
    backend = provider.backend("tianyan_sw")

    # 仿真机测不了
    # print(f"\nFetching configuration...")
    # config = backend.fetch_configuration()
    # print(f"  keys: {list(config.keys())[:5]}...")

    # from qiskit import QuantumCircuit
    # qc_raw = QuantumCircuit(7, 2, name="demo_circuit")
    # qc_raw.x(0)
    # qc_raw.x(0)
    # qc_raw.cz(0, 6)
    # qc_raw.measure(0, 0)
    # qc_raw.measure(6, 1)

    from qiskit import QuantumCircuit, QuantumRegister, ClassicalRegister
    # 线路1
    qc_raw = QuantumCircuit(7, 2, name="demo_circuit")
    qc_raw.h(0)
    qc_raw.cz(0, 6)
    qc_raw.measure(0, 0)
    qc_raw.measure(6, 1)

    # from cqlib_adapter.qiskit_ext import X2PGate, X2MGate
    # # 线路2
    # qs = QuantumRegister(2)
    # cs = ClassicalRegister(2)
    # qc_raw = QuantumCircuit(qs, cs)
    # qc_raw.x(qs[1])           # Pauli-X 门
    # qc_raw.h(qs[0])           # Hadamard 门（将自动分解为物理门）
    # qc_raw.cx(qs[0], qs[1])   # CNOT 门
    # qc_raw.append(X2PGate(), [qs[0]])  # 添加 X2P 门
    # qc_raw.append(X2MGate(), [qs[1]])  # 添加 X2M 门
    # qc_raw.barrier(qs)
    # qc_raw.measure(qs, cs)    #测量操作

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
    # FIXME:要从qcis字符串改为openqasm3
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
