from qiskit import QuantumCircuit
from qiskit import qasm3


def qiskit_to_qasm(circuit: QuantumCircuit) -> str:
    """
    将Qiskit QuantumCircuit 转为标准 OpenQASM 3 字符串

    Args:
        circuit: 已完成transpile的量子线路
    Returns:
        str: OpenQASM3 完整文本

    实现说明（★ 不要退回成裸的 qasm3.dumps）：

    1) 必须先重建到一条「带具名寄存器」的线路上再导出。
       transpile 之后的 ISA 线路，其比特是 Target 里的裸 ``Qubit`` 对象，
       不属于任何 ``QuantumRegister``。此时 ``qasm3.dumps`` 会导出 ``$7`` / ``$12``
       这种物理比特别名，**而且完全不声明 qubit 寄存器**，例如：

           OPENQASM 3.0;
           include "stdgates.inc";
           bit[2] meas;
           h $7;
           cx $7, $12;
           meas[0] = measure $7;

       服务端 ``QuantumCircuit.from_qasm_str`` 解析这种文本时，只能把它们建成
       隐式比特，``qargs[0]._index`` 为 ``None``；于是
       ``check_qc_topology`` 拿到 ``(None, None)`` 一律判「拓扑不合法」，
       把该条结果写成空值 —— 客户端查到的 ``resultStatus`` 永远为 ``[]``。
       重建进 ``QuantumCircuit(width, n_clbits)`` 之后，导出变成
       ``qubit[11] q;`` + ``q[7]`` / ``q[12]``，服务端就能正确读到 ``_index``。

    2) 顺带把宽度压到「刚好容纳被用到的最高物理比特」。
       不压缩的话，2 比特的算法线路会被撑到后端全宽（66），服务端就要去仿真
       66 比特；既慢又容易失败（失败时服务端会把所有 shot 静默填成 [0, 0]，
       表现为 QNN 目标函数恒为 0.5）。压缩只丢弃空转比特上的操作，
       被用到的物理比特编号原样保留，因此服务端的耦合器校验结果不变。
    """
    num_qubits = circuit.num_qubits
    num_clbits = circuit.num_clbits

    # 真正被使用到的物理比特（忽略 id 这类空操作）
    used = sorted(
        {
            circuit.find_bit(qubit).index
            for inst in circuit.data
            if inst.operation.name != "id"
            for qubit in inst.qubits
        }
    )
    if not used:
        used = list(range(num_qubits))

    allowed = set(used)
    narrow = QuantumCircuit(max(used) + 1, num_clbits)
    for inst in circuit.data:
        q_indices = [circuit.find_bit(q).index for q in inst.qubits]
        if not set(q_indices) <= allowed:
            continue
        c_indices = [circuit.find_bit(c).index for c in inst.clbits]
        narrow.append(
            inst.operation,
            [narrow.qubits[i] for i in q_indices],
            [narrow.clbits[i] for i in c_indices],
        )

    return qasm3.dumps(narrow, disable_constants=True)
