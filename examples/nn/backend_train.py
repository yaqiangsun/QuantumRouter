"""Example — train a quantum neural network with ``backend.run()`` directly
(no Qiskit Sampler primitive, no qiskit-machine-learning neural-network classes).

Run with::

    python examples/nn/backend_train.py --backend lingyun

This is the ``backend``-only twin of :file:`sampler_train.py`: same problem,
same circuit, same dataset, same optimizer — but instead of wrapping the
backend in :class:`quantumrouter.Sampler` and letting ``SamplerQNN`` /
``NeuralNetworkClassifier`` drive the circuit executions, it submits every
circuit straight through ``backend.run()`` and turns the returned counts into
probabilities by hand. That is the whole point: if you prefer the bare-metal
route (or want to see how the primitive wrapper works under the hood), this is
the thing to copy.

To keep the two trainings running along the *same* objective, it also
replicates the two default choices ``NeuralNetworkClassifier`` makes:
the ``squared_error`` (L2) multiclass objective and the random initial point
drawn from ``algorithm_globals`` (seeded with ``SEED``). Only the shot noise
of the backend stays different.

Requires ``qiskit-machine-learning`` (for the ansatz, the dataset RNG and the
COBYLA optimizer only)::

    pip install qiskit-machine-learning

Needs a running QuantumRouter simulation server (LingYun). Point
``LINGYUN_URL`` at it (defaults to ``http://127.0.0.1:8000``)::

    set LINGYUN_URL=http://127.0.0.1:8000        # Windows
    export LINGYUN_URL=http://127.0.0.1:8000     # macOS / Linux

Note on cost: each objective evaluation runs one job of ``SHOTS`` ×
``NUM_SAMPLES`` shots (the whole batch is submitted as a single job, exactly
like the Sampler batches same-``shots`` pubs). ``COBYLA(maxiter=MAX_ITER)``
therefore means at most ``MAX_ITER`` jobs against the backend. Lower ``SHOTS``
or ``MAX_ITER`` if you are just trying the example out.
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

# Allow running this example without installing the package:
# ``python examples/nn/backend_train.py``
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import numpy as np  # noqa: E402 - path adjusted above
from qiskit.circuit.library import real_amplitudes  # noqa: E402
from qiskit_machine_learning.circuit.library import qnn_circuit  # noqa: E402
from qiskit_machine_learning.optimizers import COBYLA  # noqa: E402
from qiskit_machine_learning.utils import algorithm_globals  # noqa: E402

import quantumrouter as qr  # noqa: E402
from dotenv import load_dotenv  # noqa: E402

SEED = 42
NUM_INPUTS = 2
NUM_SAMPLES = 8
MAX_ITER = 30
SHOTS = 1024  # 每轮 objective 求值对每个样本采这么多次（可调小加快实验）

# backend -> (provider_id, backend_id, env 里读 token 的键名)
PROVIDERS: dict[str, dict[str, str | None]] = {
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
        "url_default": None
    },
    "wuyue": {
        "provider": "wuyue",
        "backend": "WuYue-QPUSim-FullAmpSim",  # 模拟机
        "token_env": "WUYUE_TOKEN",
        "url_env": None,
        "url_default": None
    },
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Train a QNN on a QuantumRouter backend.")
    parser.add_argument(
        "--backend",
        choices=sorted(PROVIDERS),
        default="lingyun",
        help=f"要用的后端指令：{' / '.join(sorted(PROVIDERS))}（默认 lingyun）",
    )
    return parser.parse_args()


def parity(bitstring: int) -> int:
    """把测量结果映射成它的奇偶性 —— QNN 要学的二分类标签。"""
    return f"{bitstring:b}".count("1") % 2


def bitstring_to_int(key: str) -> int:
    """把 counts 的键解析成整数，供 :func:`parity` 使用。

    ``backend.run()`` 返回的 Qiskit ``Result.get_counts()`` 通常给出裸二进制串
    （如 ``"01"``）；个别厂商也可能给 ``"0x.."`` 十六进制键，这里都兼容。
    """
    key = key.lower()
    if key.startswith("0x"):
        return int(key, 16)
    if key.startswith("0b"):
        return int(key, 2)
    return int(key, 2)


def build_dataset() -> tuple[np.ndarray, np.ndarray]:
    """造一个小型线性可分二分类数据集，点在 [-1, 1]^2 内均匀分布。"""
    X = 2 * algorithm_globals.random.random([NUM_SAMPLES, NUM_INPUTS]) - 1
    y01 = 1 * (np.sum(X, axis=1) >= 0)  # 反对角线两侧分别标 0 / 1
    return X, y01


def predict_probs(
    circuit,
    input_params,
    weight_params,
    X: np.ndarray,
    weights: np.ndarray,
    backend,
    shots: int,
) -> np.ndarray:
    """QNN 前向：把整批样本 X 绑定上当前权重，一批提交到后端，返回 (N, 2) 概率矩阵。

    返回值形状和 ``SamplerQNN.forward`` 一致：第 i 行是 [[P(标签=0), P(标签=1)]],
    这样后续目标函数、预测的写法都能和 ``sampler_train.py`` 对齐。

    ``sampler_train.py`` 里这件事是 ``SamplerQNN(sampler=...)`` 做的；这里
    直接复刻它做的事：绑定参数 -> ``backend.run()`` -> ``get_counts()`` ->
    用 :func:`parity` 把每条测量结果折算成标签，再归一化成概率。
    """
    bound_circuits = [
        circuit.assign_parameters(
            dict(zip(input_params, x)) | dict(zip(weight_params, weights))
        )
        for x in X
    ]
    job = backend.run(bound_circuits, shots=shots)  # 一批线路 = 一个任务
    counts_list = job.result().get_counts()
    if isinstance(counts_list, dict):  # 只有一个线路时 Qiskit 返回单份 counts
        counts_list = [counts_list]

    p1 = np.empty(len(bound_circuits))
    for i, counts in enumerate(counts_list):
        total = sum(counts.values())
        ones = sum(cnt for key, cnt in counts.items() if parity(bitstring_to_int(key)))
        p1[i] = ones / total
    return np.column_stack([1.0 - p1, p1])


def squared_error_loss(y01: np.ndarray, probs: np.ndarray) -> float:
    """二阶（L2）多分类目标 —— :class:`NeuralNetworkClassifier` 的默认损失。

    逐行等价于 qiskit-machine-learning 的 ``MultiClassObjectiveFunction`` +
    ``L2Loss``（classifier 没传 ``loss`` 参数时用的就是这套）：:

        loss = (1/N) * Σ_out Σ_sample  probs[sample, out] * (out - y_sample)²

    注意这是概率的**线性**损失，不是交叉熵。要跟 ``sampler_train.py`` 训出
    同样的轨迹，目标函数必须和它一模一样 —— 这是关键之一。
    """
    num_samples = y01.shape[0]
    val = 0.0
    for out in (0, 1):
        val += probs[:, out] @ (np.full(num_samples, out) - y01) ** 2
    return float(val / num_samples)


def main() -> None:
    args = parse_args()
    project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    load_dotenv(os.path.join(project_root, ".env"))

    algorithm_globals.random_seed = SEED
    X, y01 = build_dataset()

    # ------------------------------------------------------------------ #
    # 1. 选后端 —— 和 sampler_train.py 一样，但这里不再包 quantumrouter.Sampler，
    #    拿到后端后直接用它。
    #
    #    用 --backend 指令切换供应商：lingyun / tianyan / wuyue。
    # ------------------------------------------------------------------ #
    config = PROVIDERS[args.backend]
    provider = qr.create_provider(
        backend=config["provider"],
        url=(os.environ.get(config["url_env"]) or config["url_default"]) if config["url_env"] else None,
        token=os.environ.get(config["token_env"]) or None,
    )
    backend = provider.backend(config["backend"])
    print(f"Using backend: {backend.name}（不经过 Sampler，直接 backend.run）")

    # ------------------------------------------------------------------ #
    # 2. 构建 QNN 线路（和 sampler_train.py 完全一致）。
    #
    #    SamplerQNN 会自己处理测量；这一版要手动跑后端，所以自己加上测量。
    #    同样不需要自己 transpile：backend.run(auto_transpile=True) 会按后端
    #    Target 的耦合表自动映射到真实物理比特。
    # ------------------------------------------------------------------ #
    circuit, input_params, weight_params = qnn_circuit(
        ansatz=real_amplitudes(NUM_INPUTS, reps=1)
    )
    circuit.measure_all()

    # ------------------------------------------------------------------ #
    # 3. 定义 objective：一批样本过一遍后端，算 classifier 默认的 L2 损失。
    # ------------------------------------------------------------------ #
    evals = 0

    def objective(weights: np.ndarray) -> float:
        nonlocal evals
        probs = predict_probs(circuit, input_params, weight_params, X, weights, backend, SHOTS)
        loss = squared_error_loss(y01, probs)
        evals += 1
        print(f"  目标函数: {loss:.6f} (第 {evals} 次求值)")
        return loss

    # ------------------------------------------------------------------ #
    # 4. 训练并评估。
    # ------------------------------------------------------------------ #
    print(f"在 {backend.name} 上训练 {NUM_SAMPLES} 个样本，最多 {MAX_ITER} 次迭代 ...")
    # NeuralNetworkClassifier 不传 initial_point 时用的初值是
    # algorithm_globals.random.random(num_weights) —— 也固定 SEED=42，
    # 而且是在 build_dataset() 之后第一个抽的，这里照它抽，两条路径的初值一致。
    initial_point = algorithm_globals.random.random(len(weight_params))
    optimize_result = COBYLA(maxiter=MAX_ITER).minimize(objective, initial_point)
    final_weights = np.asarray(optimize_result.x)

    probs = predict_probs(circuit, input_params, weight_params, X, final_weights, backend, SHOTS)
    pred = np.argmax(probs, axis=1)  # 和 classifier.predict 的 argmax 一致
    accuracy = float(np.mean(pred == y01))
    print(f"\n训练集分类准确率 = {accuracy:.4f}")
    print(f"训练后的权重: {np.round(final_weights, 6)}")


if __name__ == "__main__":
    main()
