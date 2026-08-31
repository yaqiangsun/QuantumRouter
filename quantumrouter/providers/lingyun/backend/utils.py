from qiskit import QuantumCircuit
from qiskit import qasm3

def qiskit_to_qasm(circuit: QuantumCircuit) -> str:
    """
    将Qiskit QuantumCircuit 转为标准 OpenQASM 3 字符串
    Args:
        circuit: 已完成transpile的量子线路
    Returns:
        str: OpenQASM3 完整文本
    """
    qasm_text = qasm3.dumps(
        circuit,
        disable_constants=True
    )
    return qasm_text
