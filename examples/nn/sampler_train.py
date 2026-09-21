"""Example — train a quantum neural network on a QuantumRouter backend.

Run with::

    python examples/nn/sampler_train.py --backend local     # 本地 Qiskit 仿真，无需 token / URL
    python examples/nn/sampler_train.py --backend lingyun
    python examples/nn/sampler_train.py --backend quafu
    python examples/nn/sampler_train.py --backend lqcloud
    # 跨服务推理测试：在 lingyun 训练，把权重搬到 tianyan 上再推理一遍
    python examples/nn/sampler_train.py --backend lingyun --infer-backend tianyan

``--backend local`` runs the whole training loop on Qiskit's built-in local
simulator — no URL, no token, no running server; combine it with
``--infer-backend tianyan`` etc. to exercise cross-vendor inference locally.

This example needs a running QuantumRouter simulation server (LingYun).
Point ``LINGYUN_URL`` at it (defaults to ``http://127.0.0.1:8000``)::

    set LINGYUN_URL=http://127.0.0.1:8000        # Windows
    export LINGYUN_URL=http://127.0.0.1:8000     # macOS / Linux

For Quafu (``--backend quafu``) set ``QUANFU_TOKEN`` in ``.env``; its
cloud service address is fixed, so no URL is needed.

For LQCloud (``--backend lqcloud``) set ``LQCLOUD_TOKEN`` in ``.env``;
its cloud address is fixed, and the backend is the real 24-qubit MQ02
(QPU queue charges per job — reduce ``MAX_ITER``/shots to keep a test
run cheap).

It trains a 2-qubit ``SamplerQNN`` to separate a toy linearly-separable
dataset, using :class:`quantumrouter.Sampler` as the Qiskit primitives
backend. That is the whole point of the example: the circuits run on the
**QuantumRouter backend**, not on a local statevector simulator, so the
same training code works against a real device by changing only the
provider URL.

With ``--infer-backend`` it also shows the reverse direction — a model is
only a vector of parameters, so the trained weights can be shipped to a
*second* provider and run pure inference there. This proves the weights
are portable across clouds: train on one service, infer on another.

Requires ``qiskit-machine-learning``::

    pip install qiskit-machine-learning
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

# Allow running this example without installing the package:
# ``python examples/nn/sampler_train.py``
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import numpy as np  # noqa: E402 - path adjusted above
from qiskit.circuit.library import real_amplitudes  # noqa: E402
from qiskit_machine_learning.algorithms.classifiers import (  # noqa: E402
    NeuralNetworkClassifier,
)
from qiskit_machine_learning.circuit.library import qnn_circuit  # noqa: E402
from qiskit_machine_learning.neural_networks import SamplerQNN  # noqa: E402
from qiskit_machine_learning.optimizers import COBYLA  # noqa: E402
from qiskit_machine_learning.utils import algorithm_globals  # noqa: E402

import quantumrouter as qr  # noqa: E402
from dotenv import load_dotenv  # noqa: E402

SEED = 42
NUM_INPUTS = 2
NUM_SAMPLES = 8
MAX_ITER = 30

# backend -> (provider_id, backend_id, env 里读 token 的键名)
PROVIDERS: dict[str, dict[str, str | None]] = {
    "local": {
        "provider": "local",
        "backend": "local_simulator",  # 本地 Qiskit 仿真，无需 token / URL / 服务端
        "token_env": "LOCAL_TOKEN",    # 占位：本后端从不读 token / URL
        "url_env": "LOCAL_URL",
        "url_default": None,
    },
    "lingyun": {
        "provider": "lingyun",
        "backend": "lingyun_001",
        "token_env": "LINGYUN_TOKEN",
        "url_env": "LINGYUN_URL",
        "url_default": "http://127.0.0.1:8000",
    },
    "tianyan": {
        "provider": "tianyan",
        "backend": "tianyan_sw",
        "token_env": "TianYan_TOKEN",
        "url_env": None,
        "url_default": None,
    },
    "wuyue": {
        "provider": "wuyue",
        "backend": "WuYue-QPUSim-FullAmpSim",  # 模拟机
        "token_env": "WUYUE_TOKEN",
        "url_env": None,
        "url_default": None,
    },
    "quafu": {
        "provider": "quafu",
        "backend": "ScQ-Sim10",  # 模拟机（10 比特）
        "token_env": "QUANFU_TOKEN",
        "url_env": None,
        "url_default": None,
    },
    "lqcloud": {
        "provider": "lqcloud",
        "backend": "MQ02",
        "token_env": "LQCLOUD_TOKEN",
        "url_env": None,
        "url_default": None,
    },
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Train a QNN on a QuantumRouter backend.")
    parser.add_argument(
        "--backend",
        choices=sorted(PROVIDERS),
        default="lingyun",
        help=f"训练要用的后端指令：{' / '.join(sorted(PROVIDERS))}（默认 lingyun）",
    )
    parser.add_argument(
        "--infer-backend",
        choices=sorted(PROVIDERS),
        default=None,
        help=f"可选：训练完成后，把训练好的权重搬到这个后端上做纯推理测试"
             f"（跨服务验证模型可移植，例如 --backend lingyun --infer-backend tianyan）",
    )
    return parser.parse_args()


def parity(bitstring: int) -> int:
    """把测量结果映射成它的奇偶性 —— QNN 要学的二分类标签。"""
    return f"{bitstring:b}".count("1") % 2


def build_dataset() -> tuple[np.ndarray, np.ndarray]:
    """造一个小型线性可分二分类数据集，点在 [-1, 1]^2 内均匀分布。"""
    X = 2 * algorithm_globals.random.random([NUM_SAMPLES, NUM_INPUTS]) - 1
    y01 = 1 * (np.sum(X, axis=1) >= 0)  # 反对角线两侧分别标 0 / 1
    return X, y01


def connect_backend(name: str) -> tuple[qr.Sampler, object]:
    """按 PROVIDERS 表里的键连上一个后端，并包成 quantumrouter.Sampler。

    训练和跨服务推理都走这里：唯一的区别只是传进来的名字不同。
    """
    config = PROVIDERS[name]
    url = (os.environ.get(config["url_env"]) or config["url_default"]) if config["url_env"] else None
    provider = qr.create_provider(
        backend=config["provider"],
        url=url,
        token=os.environ.get(config["token_env"]) or None,
    )
    backend = provider.backend(config["backend"])
    return qr.Sampler(backend), backend


def main() -> None:
    args = parse_args()
    project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    load_dotenv(os.path.join(project_root, ".env"))

    algorithm_globals.random_seed = SEED
    X, y01 = build_dataset()

    # ------------------------------------------------------------------ #
    # 1. 选后端，并把 QuantumRouter 后端包成 Qiskit 的 Sampler。
    #
    #    用 quantumrouter.Sampler —— 不要用 qiskit.primitives 里的
    #    StatevectorSampler 之类顶替，那样线路会在本地状态向量模拟器上跑，
    #    请求根本到不了服务端。
    #
    #    用 --backend 指令切换供应商：lingyun / tianyan / wuyue / quafu / lqcloud。
    # ------------------------------------------------------------------ #
    sampler, backend = connect_backend(args.backend)

    # ------------------------------------------------------------------ #
    # 2. 构建 QNN 线路。
    #
    #    不需要自己 transpile，也不用指定物理比特：后端 Target 带着真机
    #    耦合表，Sampler 默认 auto_transpile=True，会自动把逻辑比特映射到
    #    真实存在的耦合器上。
    # ------------------------------------------------------------------ #
    circuit, input_params, weight_params = qnn_circuit(
        ansatz=real_amplitudes(NUM_INPUTS, reps=1)
    )
    # circuit.measure_all()

    # ------------------------------------------------------------------ #
    # 3. 组装 SamplerQNN 和分类器。
    #
    #    必须传「逻辑线路」：SamplerQNN 一旦发现 circuit.layout 不为 None，
    #    就会按 layout 去反解 counts，结果会解错。
    # ------------------------------------------------------------------ #
    sampler_qnn = SamplerQNN(
        circuit=circuit,
        input_params=input_params,
        weight_params=weight_params,
        interpret=parity,
        output_shape=2,  # 奇偶映射的两种可能结果
        sampler=sampler,
    )
    classifier = NeuralNetworkClassifier(
        neural_network=sampler_qnn,
        optimizer=COBYLA(maxiter=MAX_ITER),
        callback=lambda _weights, value: print(f"  目标函数: {value:.6f}"),
    )

    # ------------------------------------------------------------------ #
    # 4. 训练并评估。
    # ------------------------------------------------------------------ #
    print(f"在 {backend.name} 上训练 {NUM_SAMPLES} 个样本，最多 {MAX_ITER} 次迭代 ...")
    classifier.fit(X, y01)

    accuracy = classifier.score(X, y01)
    print(f"\n训练集分类准确率 = {accuracy:.4f}")
    print(f"训练后的权重: {np.round(classifier.weights, 6)}")

    # ------------------------------------------------------------------ #
    # 5. 跨服务推理测试（--infer-backend）。
    #
    #    模型本质上就是一组权重。线路定义、参数布局都和具体云无关，只有
    #    真正采样那一刻才接触后端 —— 所以训练好的权重可以原样搬到另一个
    #    服务上，只用它做纯推理（不训练）。这是 QuantumRouter 想证明的场景：
    #    一套权重，随处推理；比如 lingyun 训练，tianyan 推理。
    # ------------------------------------------------------------------ #
    if args.infer_backend is not None:
        print(
            f"\n把训练好的权重搬到 {args.infer_backend} 上做纯推理测试 ..."
        )
        infer_sampler, infer_backend = connect_backend(args.infer_backend)
        infer_qnn = SamplerQNN(
            circuit=circuit.copy(),  # 逻辑线路，后端侧会按各自 Target 自动映射
            input_params=input_params,
            weight_params=weight_params,
            interpret=parity,
            output_shape=2,
            sampler=infer_sampler,
        )
        infer_probs = infer_qnn.forward(X, classifier.weights)
        infer_pred = np.argmax(infer_probs, axis=1)
        infer_accuracy = float(np.mean(infer_pred == y01))
        print(f"  {backend.name} 训练的权重拖到 {infer_backend.name} 上推理")
        print(f"  训练后端准确率 = {accuracy:.4f} | 推理后端准确率 = {infer_accuracy:.4f}")


if __name__ == "__main__":
    main()
