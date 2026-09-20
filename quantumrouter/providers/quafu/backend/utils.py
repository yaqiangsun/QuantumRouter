"""OpenQASM 2 helpers for the Quafu provider.

Quafu's server consumes OpenQASM 2 text in its ``qtasm`` field (the
same format upstream pyquafu emits from ``QuantumCircuit.to_openqasm()``:
``OPENQASM 2.0;`` + ``qreg q[N];`` + ``creg ...;`` + ``measure q[i] -> c[j];``).
Qiskit's :func:`qiskit.qasm2.dumps` already produces exactly this shape
for both register-based and transpiled bare-qubit circuits, so no
reassembly is required here (contrast LingYun's ``qiskit_to_qasm``).
"""

from __future__ import annotations

import re

from qiskit import QuantumCircuit, qasm2


def qiskit_to_qasm2(circuit: QuantumCircuit) -> tuple[str, int]:
    """Export a qiskit circuit to OpenQASM 2 and its declared qubit width.

    Returns
    -------
    ``(qasm_text, width)`` where ``width`` is the ``qreg q[N]`` width the
    Quafu submit payload uses for its ``qubits`` field.
    """
    qasm = qasm2.dumps(circuit)
    width = 0
    match = re.search(r"qreg\s+q\[(\d+)\];", qasm)
    if match:
        width = int(match.group(1))
    return qasm, width
