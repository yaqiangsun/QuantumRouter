"""Example — basic usage of the QuantumRouter package for WuYue mobile quantum cloud.
Run with::
    python examples/basic_usage_wuyue.py
Before running, set WuYue env variables:
    set WUYUE_TOKEN=xxx        # Windows
    export WUYUE_TOKEN=xxx      # macOS / Linux
This example talks to WuYue quantum-cloud platform over HTTP via internal WuyueClient.
It uses ``create_provider``, single entry point, same calling code as TianYan after switching backend name.
"""
from __future__ import annotations
import os
import sys
import time
from pathlib import Path
from qiskit import QuantumCircuit
# Auto add project root path for local run without install
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import quantumrouter  # noqa: E402


def main() -> None:
    # ------------------------------------------------------------------ #
    # 1. Create WuYue provider via unified create_provider entry
    # ------------------------------------------------------------------ #
    provider = quantumrouter.create_provider(
            backend="wuyue",
            token=os.environ.get("WUYUE_TOKEN", "xxxxxxxxx+xxxxxxxxxxx"),
        )

    # ------------------------------------------------------------------ #
    # 2. List all online available backends
    # ------------------------------------------------------------------ #
    try:
        backends = provider.backends(online=True)
    except quantumrouter.QuantumRouterError as exc:
        print(f"Connect WuYue cloud failed:\n  {exc}")
        print("Check AK/SK validity & network access to WuYue endpoint.")
        return

    print(f"Available WuYue backends count: {len(backends)}")
    if not backends:
        print("No usable devices found, verify your cloud account permission.")
        return

    # ------------------------------------------------------------------ #
    # 3. Select target simulator device & construct Qiskit circuit
    # ------------------------------------------------------------------ #
    backend = provider.backend("WuYue-QPUSim-FullAmpSim") # 模拟机
    # backend = provider.backend("WuYue-QPU-002-V6") # 真机

    
    # 线路一：有7个比特
    qc_raw = QuantumCircuit(7, 2, name="wuyue_demo_circuit")
    qc_raw.h(0)
    qc_raw.cz(0, 6)
    qc_raw.measure(0, 0)
    qc_raw.measure(6, 1)

    # 线路二：有2个比特
    # qc_raw = QuantumCircuit(2, 2)
    # qc_raw.h(0)    # 叠加
    # qc_raw.cx(0,1) # 纠缠
    # qc_raw.measure(0, 0)
    # qc_raw.measure(1, 1)

    # ------------------------------------------------------------------ #
    # 4. Submit circuit object via backend.run (auto convert QASM inside Runner)
    # ------------------------------------------------------------------ #
    job = backend.run(
        run_input=[qc_raw],
        shots=1024,
        calculate_type=1,
        timeout=120
    )
    print("[INFO] basic.py backend.run job, type: ", type(job), ", value: ", job)

    task_id = job.job_id()
    print(f"\n[INFO] WuYue backend.run launched job: {job}")
    print(f"task_id: {task_id}")

    time.sleep(5)

    res = job.result()
    print(f"\n[INFO] Job full result object: {res}")

    cnts = job.result().get_counts()
    # cnts = res.get_counts()
    print(f"[INFO] Measurement counts: {cnts}")


if __name__ == "__main__":
    main()
