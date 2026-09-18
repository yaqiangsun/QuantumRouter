"""Example — basic usage of the QuantumRouter package (single file, all vendors).

Run with::

    python examples/basic_usage.py                          # 默认 lingyun
    python examples/basic_usage.py --backend wuyue
    python examples/basic_usage.py --backend tianyan

Before running, set the token for the vendor you use (in ``.env`` or the
environment)::

    set LINGYUN_TOKEN=...          # Windows
    export LINGYUN_TOKEN=...       # macOS / Linux
    set TianYan_TOKEN=...
    set WUYUE_TOKEN=...
    set LINGYUN_URL=...            # lingyun 模拟机需要指向运行中的服务端

This example talks to the chosen quantum-cloud platform over HTTP. It uses
``create_provider``, the single entry point that keeps the calling code
identical when switching vendors.
"""

from __future__ import annotations

import argparse
import os
import sys
import time
from pathlib import Path

# Allow running this example without installing the package:
# ``python examples/basic_usage.py``
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from qiskit import QuantumCircuit, transpile  # noqa: E402 - path adjusted above

import quantumrouter as qr  # noqa: E402
from dotenv import load_dotenv  # noqa: E402

# backend -> provider / 后端名 / env 里读 token 的键名 / run 参数
PROVIDERS: dict[str, dict[str, object]] = {
    "lingyun": {
        "provider": "lingyun",
        "backend": "lingyun_001",
        "token_env": "LINGYUN_TOKEN",
        "url_env": "LINGYUN_URL",
        "url_default": "http://127.0.0.1:8000",
        "run_kwargs": {"shots": 1024, "readout_calibration": True},
    },
    "tianyan": {
        "provider": "tianyan",
        "backend": "tianyan_sw",
        "token_env": "TianYan_TOKEN",
        "transpile": True,  # 真机前先用后端耦合表做 transpile
        "run_kwargs": {"shots": 1024, "readout_calibration": True},
    },
    "wuyue": {
        "provider": "wuyue",
        "backend": "WuYue-QPUSim-FullAmpSim",  # 模拟机
        "token_env": "WUYUE_TOKEN",
        "run_kwargs": {"shots": 1024, "calculate_type": 1, "timeout": 120},
    },
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Basic usage of QuantumRouter across vendors."
    )
    parser.add_argument(
        "--backend",
        choices=sorted(PROVIDERS),
        default="lingyun",
        help=f"要用的后端：{' / '.join(sorted(PROVIDERS))}（默认 lingyun）",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    load_dotenv(os.path.join(project_root, ".env"))
    cfg = PROVIDERS[args.backend]

    # ------------------------------------------------------------------ #
    # 1. 用统一入口 create_provider 建 provider（传输方式由 URL 推断）。
    # ------------------------------------------------------------------ #
    provider = qr.create_provider(
        backend=cfg["provider"],
        url=(os.environ.get(cfg["url_env"]) or cfg["url_default"]) if cfg.get("url_env") else None,
        token=os.environ.get(cfg["token_env"]) or None,
    )

    # ------------------------------------------------------------------ #
    # 2. 列出该用户可用的后端（会真的请求云端）。
    # ------------------------------------------------------------------ #
    try:
        backends = provider.backends(online=True)
    except qr.QuantumRouterError as exc:
        print(f"连接 {args.backend} 云端失败:\n  {exc}")
        print("检查 token / 网络 / 服务端是否在运行后重试。")
        return

    print(f"Available backends ({len(backends)}):")
    if not backends:
        print("No backends found. Check the URL / token.")
        return

    # ------------------------------------------------------------------ #
    # 3. 选一个后端并构造 7 比特线路（H + CZ + 测量）。
    # ------------------------------------------------------------------ #
    backend = provider.backend(cfg["backend"])
    print(f"Using backend: {backend.name}")

    qc_raw = QuantumCircuit(7, 2, name="demo_circuit")
    qc_raw.h(0)          # 叠加态
    qc_raw.cz(0, 6)      # CZ 纠缠门，Q0 控制 Q6 目标
    qc_raw.measure(0, 0)
    qc_raw.measure(6, 1)

    # tianyan 真机前先按后端耦合表 transpile。
    if cfg.get("transpile"):
        tqc = transpile(qc_raw, backend=backend)
        # tqc = transpile(qc_raw, backend=backend, layout_method="sabre")
        tqc.draw(idle_wires=False)
        print("[END] tqc, type(tqc): ", tqc, type(tqc))

    # ------------------------------------------------------------------ #
    # 4. 提交作业并取回测量计数。
    # ------------------------------------------------------------------ #
    job = backend.run(run_input=[qc_raw], **cfg["run_kwargs"])
    task_id = job.job_id()
    print("\n[INFO] backend.run job: ", job)
    print("task_id: ", task_id)

    res = job.result()
    print("[INFO] backend.run-----res: ", res)

    cnts = job.result().get_counts()
    print("[INFO] backend.run -----cnts: ", cnts)


if __name__ == "__main__":
    main()
