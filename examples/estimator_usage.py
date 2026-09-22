"""Example — evaluate expectation values with an Estimator on any vendor.

Run with::

    python examples/estimator_usage.py --backend local     # 本地 Qiskit 仿真，无需 token / URL / 服务端
    python examples/estimator_usage.py --backend lingyun
    python examples/estimator_usage.py --backend tianyan
    python examples/estimator_usage.py --backend wuyue
    python examples/estimator_usage.py --backend quafu
    python examples/estimator_usage.py --backend lqcloud

Before running, set the token for the vendor you use (in ``.env`` or the
environment)::

    set LINGYUN_TOKEN=...          # Windows
    export LINGYUN_TOKEN=...       # macOS / Linux
    set TianYan_TOKEN=...
    set WUYUE_TOKEN=...
    set QUANFU_TOKEN=...           # quafu 云端服务地址固定，无需 LINGYUN_URL
    set LQCLOUD_TOKEN=...          # lqcloud 真机 MQ02，云端地址固定
    set LINGYUN_URL=...            # lingyun 模拟机需要指向运行中的服务端

``--backend local`` 不需要上面任何一项：它在本地用 Qiskit 自带模拟器跑，完全不联网。

This example is the Estimator twin of :file:`basic_usage.py`: same provider
switching (``create_provider`` + a ``--backend`` switch), but instead of asking
the backend for measurement counts it asks for the **expectation value** of a
Paul Hamiltonian, i.e. ``⟨ψ(θ)|H|ψ(θ)⟩``.

Two things to note about how the Estimator is built here:

* QuantumRouter has no ``qr.Estimator`` wrapper — the package only ships a
  ``qr.Sampler``. We therefore wrap the QuantumRouter backend in Qiskit's
  generic :class:`qiskit.primitives.BackendEstimatorV2`, which turns any
  ``BackendV2`` into an Estimator. This is the same adapter the Sampler is
  built on.
* The circuit is **not** transpiled by hand. Each QuantumRouter backend carries
  its real coupling map in its ``Target`` and transpiles internally
  (``auto_transpile=True``, which is the default), so the logical ansatz and
  the observable — both written on logical qubits — are mapped consistently.
  We also leave ``readout_calibration`` at each backend's default (``True``):
  ``BackendEstimatorV2`` does not expose a per-call switch for it.

The Estimator returns one expectation value per parameter set, so this example
also shows **broadcasting** — a whole sweep of ``theta`` vectors in a single
job, which the plain ``backend.run()`` interface cannot express.
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

# Allow running this example without installing the package:
# ``python examples/estimator_usage.py``
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from qiskit.circuit.library import real_amplitudes  # noqa: E402 - path adjusted above
from qiskit.primitives import BackendEstimatorV2  # noqa: E402
from qiskit.quantum_info import SparsePauliOp  # noqa: E402

import quantumrouter as qr  # noqa: E402
from dotenv import load_dotenv  # noqa: E402

# backend -> provider / 后端名 / env 里读 token 的键名 / Estimator 精度
#
# ``precision`` 是 Estimator 的目标精度：它按 ``shots = ceil(1 / precision**2)``
# 换算采样次数。默认 0.015625（≈4096 shots）；lqcloud 是真实 QPU、按次计费，
# 给一个更粗的精度少花 shots。
PROVIDERS: dict[str, dict[str, object]] = {
    "local": {
        "provider": "local",
        "backend": "local_simulator",  # 本地 Qiskit 仿真，无需 token / URL / 服务端
        "token_env": "LOCAL_TOKEN",    # 本后端从不读取 token，这里只占位
        "precision": 0.015625,
    },
    "lingyun": {
        "provider": "lingyun",
        "backend": "lingyun_001",
        "token_env": "LINGYUN_TOKEN",
        "url_env": "LINGYUN_URL",
        "url_default": "http://127.0.0.1:8000",
        "precision": 0.015625,
    },
    "tianyan": {
        "provider": "tianyan",
        "backend": "tianyan_sw",
        "token_env": "TianYan_TOKEN",
        "precision": 0.015625,
    },
    "wuyue": {
        "provider": "wuyue",
        "backend": "WuYue-QPUSim-FullAmpSim",  # 模拟机
        "token_env": "WUYUE_TOKEN",
        "precision": 0.015625,
    },
    "quafu": {
        "provider": "quafu",
        "backend": "ScQ-Sim10",  # 模拟机（10 比特）
        "token_env": "QUANFU_TOKEN",
        "precision": 0.015625,
    },
    "lqcloud": {
        "provider": "lqcloud",
        "backend": "MQ02",  # 真机（24 比特链式拓扑），QPU 队列按次收费
        "token_env": "LQCLOUD_TOKEN",
        "precision": 0.05,  # 更粗的精度 -> 更少 shots，试跑更便宜
    },
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Estimator usage of QuantumRouter across vendors."
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
    # 3. 选一个后端。
    # ------------------------------------------------------------------ #
    backend = provider.backend(cfg["backend"])
    print(f"Using backend: {backend.name}")

    # ------------------------------------------------------------------ #
    # 4. 定义参数化电路和哈密顿量。
    #
    #    用函数式 real_amplitudes（类 RealAmplitudes 在 Qiskit 2.1 已弃用）。
    #    电路与可观测量都写在**逻辑比特**上，不手动 transpile：后端 Target
    #    带真机耦合表，run() 里的 auto_transpile 会自动映射好。
    # ------------------------------------------------------------------ #
    ansatz = real_amplitudes(num_qubits=2, reps=2)
    observable = SparsePauliOp.from_list([
        ("II", 1), ("IZ", 2), ("XI", 3),
    ])
    # 一组 θ 就是一次期望值计算；这里给多组，演示 Estimator 的广播：
    # 一个 job 拿回整条扫描曲线的 evs。
    thetas = [
        [0, 1, 1, 2, 3, 5],
        [1, 0, 2, 1, 4, 2],
    ]

    # ------------------------------------------------------------------ #
    # 5. 用 Qiskit 原生 BackendEstimatorV2 包住 QuantumRouter 后端并运行。
    # ------------------------------------------------------------------ #
    estimator = BackendEstimatorV2(
        backend=backend,
        options={"default_precision": cfg["precision"]},
    )
    job = estimator.run([(ansatz, observable, thetas)])
    print("\n[INFO] estimator.run job: ", job)
    print("job_id: ", job.job_id())

    pub_result = job.result()[0]

    # ------------------------------------------------------------------ #
    # 6. 提取结果：evs 是每个 θ 对应的 ⟨ψ(θ)|H|ψ(θ)⟩，stds 是标准误差。
    # ------------------------------------------------------------------ #
    print("\nExpectation values:", pub_result.data.evs)
    print("Standard errors:   ", pub_result.data.stds)
    print("Metadata:          ", pub_result.metadata)


if __name__ == "__main__":
    main()
