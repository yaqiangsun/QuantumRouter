"""Sampler V2 implementation for QuantumRouter backends.

QuantumRouter 的物理后端（凌云 / 天仪 / 五岳）和仿真后端都没有原生实现
Qiskit 的 ``BaseSamplerV2`` 接口，因此这里用 :class:`BackendSamplerV2` 做适配层，
把 ``backend.run()`` 的结果包装成标准的 ``PrimitiveResult[SamplerPubResult]``。

与父类相比只多一件事：把 QuantumRouter 特有的两个执行开关透传给后端。

* ``readout_calibration`` —— 是否做读出误差校正；
* ``auto_transpile``      —— 是否在后端侧自动转译。

这两个开关是**每个 QuantumRouter 后端 ``run()`` 都声明的形参**
（见 ``quantumrouter/providers/*/backend/base.py``），并非某一家专有。

这两个开关可以在三个地方配置，优先级由低到高：

1. 模块默认值 :data:`DEFAULT_RUN_OPTIONS`（都是 ``True``）；
2. 构造时 ``Sampler(backend, options={"run_options": {...}})``；
3. 调用 ``Sampler.run(..., readout_calibration=..., auto_transpile=...)``。

第 3 层传 ``None`` 表示「不表态」，让第 2/1 层决定。
"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Iterable
from typing import Any

import numpy as np
from qiskit.primitives import BackendSamplerV2

# ``_run_circuits`` 是 Qiskit 的私有工具函数，父类 ``BackendSamplerV2`` 自己也从
# ``backend_estimator_v2`` 导入它。这里复用同一个实现，避免再抄一份副本走样。
# 它同时是本模块的调试接缝：``quantumrouter.sampler.base._run_circuits`` 可以被
# 临时替换，用来观察后端返回的原始 counts。
from qiskit.primitives.backend_estimator_v2 import _run_circuits
from qiskit.primitives.backend_sampler_v2 import _analyze_circuit, _prepare_memory
from qiskit.primitives.containers import (
    PrimitiveResult,
    SamplerPubLike,
    SamplerPubResult,
)
from qiskit.primitives.containers.sampler_pub import SamplerPub
from qiskit.primitives.primitive_job import PrimitiveJob
from qiskit.providers import BackendV2

__all__ = ["Sampler", "DEFAULT_RUN_OPTIONS"]

DEFAULT_RUN_OPTIONS: dict[str, Any] = {
    "readout_calibration": True,
    "auto_transpile": True,
}
"""传给 ``backend.run()`` 的默认执行开关，会被更具体的配置覆盖。"""


class Sampler(BackendSamplerV2):
    """在 QuantumRouter 后端上执行线路采样。

    与父类 :class:`BackendSamplerV2` 的区别只有两处：

    1. 支持 ``readout_calibration`` / ``auto_transpile`` 两个后端开关，透传给
       ``backend.run()``，并支持构造函数默认值和 :meth:`run` 逐次覆盖；
    2. ``default_shots`` 是真正的构造参数。

    Args:
        backend: 目标量子后端（``BackendV2``）。
        default_shots: ``run()`` 未显式给 ``shots`` 时使用的默认采样次数。
            若 ``options`` 里也写了 ``default_shots``，以 ``options`` 为准。
        options: 传给父类的选项字典，支持 ``default_shots`` / ``seed_simulator`` /
            ``run_options`` 三个键。其中 ``run_options`` 会被原样透传给
            ``backend.run()``，用于设置 ``readout_calibration``、``auto_transpile``、
            ``meas_level`` 等后端私有选项。

    Examples:
        默认 4096 次采样，构造时关掉读出校正::

            sampler = Sampler(
                backend,
                default_shots=4096,
                options={"run_options": {"readout_calibration": False}},
            )
            result = sampler.run([(circuit, params)]).result()

        单次调用覆盖构造时的设置::

            sampler.run([(circuit, params)], auto_transpile=False)
    """

    def __init__(
        self,
        backend: BackendV2,
        default_shots: int = 1024,
        options: dict[str, Any] | None = None,
    ) -> None:
        """初始化 Sampler。

        Args:
            backend: 目标量子后端。
            default_shots: 默认采样次数，``run()`` 未指定 ``shots`` 时生效。
            options: 传给父类的选项字典，见类文档。
        """
        merged_options = dict(options or {})
        # 只在 options 没写的时候才用形参，保证「options 里显式写的更优先」，
        # 同时让 default_shots 形参真正生效（此前它被静默忽略，恒为 1024）。
        merged_options.setdefault("default_shots", default_shots)
        super().__init__(backend=backend, options=merged_options)

    def run(
        self,
        pubs: Iterable[SamplerPubLike],
        *,
        shots: int | None = None,
        readout_calibration: bool | None = None,
        auto_transpile: bool | None = None,
    ) -> PrimitiveJob[PrimitiveResult[SamplerPubResult]]:
        """提交一批 PUB 并返回作业句柄。

        Args:
            pubs: 待执行的 PUB 序列。单个 PUB 是
                ``(circuit, parameter_values)`` 及可选 ``shots``，
                注意必须包在列表里：``sampler.run([(circuit, values)])``。
            shots: 本次执行的采样次数；``None`` 表示沿用默认值。
            readout_calibration: 是否做读出误差校正；``None`` 表示不表态，
                由构造时的 ``run_options`` 或模块默认值决定。
            auto_transpile: 是否在后端侧自动转译；``None`` 同上。

        Returns:
            作业句柄，``.result()`` 可拿到 ``PrimitiveResult[SamplerPubResult]``。
        """
        if shots is None:
            shots = self._options.default_shots
        coerced_pubs = [SamplerPub.coerce(pub, shots) for pub in pubs]
        self._validate_pubs(coerced_pubs)
        job = PrimitiveJob(
            self._run,
            coerced_pubs,
            self._resolve_run_options(readout_calibration, auto_transpile),
        )
        job._submit()
        return job

    def _resolve_run_options(
        self,
        readout_calibration: bool | None,
        auto_transpile: bool | None,
    ) -> dict[str, Any]:
        """合并三层配置，得到最终透传给 ``backend.run()`` 的选项。"""
        run_options = dict(DEFAULT_RUN_OPTIONS)
        run_options.update(self._options.run_options or {})
        if readout_calibration is not None:
            run_options["readout_calibration"] = readout_calibration
        if auto_transpile is not None:
            run_options["auto_transpile"] = auto_transpile
        return run_options

    def _run(
        self,
        pubs: list[SamplerPub],
        run_options: dict[str, Any],
    ) -> PrimitiveResult[SamplerPubResult]:
        pub_dict = defaultdict(list)
        # consolidate pubs with the same number of shots
        for i, pub in enumerate(pubs):
            pub_dict[pub.shots].append(i)

        results = [None] * len(pubs)
        for shots, lst in pub_dict.items():
            # run pubs with the same number of shots at once
            pub_results = self._run_pubs(
                pubs=[pubs[i] for i in lst],
                shots=shots,
                run_options=run_options,
            )
            # reconstruct the result of pubs
            for i, pub_result in zip(lst, pub_results):
                results[i] = pub_result
        return PrimitiveResult(results, metadata={"version": 2})

    def _run_pubs(
        self,
        pubs: list[SamplerPub],
        shots: int,
        run_options: dict[str, Any],
    ) -> list[SamplerPubResult]:
        """Compute results for pubs that all require the same value of ``shots``."""
        # prepare circuits
        bound_circuits = [pub.parameter_values.bind_all(pub.circuit) for pub in pubs]
        flatten_circuits = []
        for circuits in bound_circuits:
            flatten_circuits.extend(np.ravel(circuits).tolist())

        # run circuits
        results, _ = _run_circuits(
            flatten_circuits,
            self._backend,
            clear_metadata=False,
            memory=True,
            shots=shots,
            seed_simulator=self._options.seed_simulator,
            **run_options,
        )
        result_memory = _prepare_memory(results)

        # pack memory to an ndarray of uint8
        meas_level = run_options.get("meas_level")
        results = []
        start = 0
        for pub, bound in zip(pubs, bound_circuits):
            meas_info, max_num_bytes = _analyze_circuit(pub.circuit)
            end = start + bound.size
            results.append(
                self._postprocess_pub(
                    result_memory[start:end],
                    shots,
                    bound.shape,
                    meas_info,
                    max_num_bytes,
                    pub.circuit.metadata,
                    meas_level,
                )
            )
            start = end

        return results
