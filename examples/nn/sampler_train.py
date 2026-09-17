"""Example — train a quantum neural network on a QuantumRouter backend.

Run with::

    python examples/nn/sampler_train.py

This example needs a running QuantumRouter simulation server (LingYun).
Point ``LINGYUN_URL`` at it (defaults to ``http://127.0.0.1:8000``)::

    set LINGYUN_URL=http://127.0.0.1:8000        # Windows
    export LINGYUN_URL=http://127.0.0.1:8000     # macOS / Linux

It trains a 2-qubit ``SamplerQNN`` to separate a toy linearly-separable
dataset, using :class:`quantumrouter.Sampler` as the Qiskit primitives
backend. That is the whole point of the example: the circuits run on the
**QuantumRouter backend**, not on a local statevector simulator, so the
same training code works against a real device by changing only the
provider URL.

Requires ``qiskit-machine-learning``::

    pip install qiskit-machine-learning
"""

from __future__ import annotations

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

SEED = 42
NUM_INPUTS = 2
NUM_SAMPLES = 20
MAX_ITER = 30


def parity(bitstring: int) -> int:
    """把测量结果映射成它的奇偶性 —— QNN 要学的二分类标签。"""
    return f"{bitstring:b}".count("1") % 2


def build_dataset() -> tuple[np.ndarray, np.ndarray]:
    """造一个小型线性可分二分类数据集，点在 [-1, 1]^2 内均匀分布。"""
    X = 2 * algorithm_globals.random.random([NUM_SAMPLES, NUM_INPUTS]) - 1
    y01 = 1 * (np.sum(X, axis=1) >= 0)  # 反对角线两侧分别标 0 / 1
    return X, y01


def main() -> None:
    algorithm_globals.random_seed = SEED
    X, y01 = build_dataset()

    # ------------------------------------------------------------------ #
    # 1. 选后端，并把 QuantumRouter 后端包成 Qiskit 的 Sampler。
    #
    #    用 quantumrouter.Sampler —— 不要用 qiskit.primitives 里的
    #    StatevectorSampler 之类顶替，那样线路会在本地状态向量模拟器上跑，
    #    请求根本到不了服务端。
    # ------------------------------------------------------------------ #
    provider = qr.create_provider(
        backend="lingyun",
        url=os.environ.get("LINGYUN_URL", "http://127.0.0.1:8000"),
        token=os.environ.get("LINGYUN_TOKEN") or None,
    )
    backend = provider.backend("lingyun_001")
    sampler = qr.Sampler(backend)

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


if __name__ == "__main__":
    main()
