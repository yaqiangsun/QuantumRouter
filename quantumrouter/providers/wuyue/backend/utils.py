"""OpenQASM 2 helpers for the WuYue provider.

WuYue's server consumes standard OpenQASM 2 text in its ``inData`` field
(the same format upstream ``wuyue.plugin.runner.convert_qasm`` emits from
a Qiskit circuit via ``qiskit.qasm2.dumps``).  Qiskit's
:func:`qiskit.qasm2.dumps` already produces exactly this shape for both
register-based and transpiled bare-qubit circuits, so no reassembly is
required here (contrast LingYun's ``qiskit_to_qasm``).
"""

from __future__ import annotations

import re

from qiskit import QuantumCircuit, qasm2


def qiskit_to_qasm2(circuit: QuantumCircuit) -> tuple[str, int]:
    """Export a qiskit circuit to OpenQASM 2 and its declared qubit width.

    Returns
    -------
    ``(qasm_text, width)`` where ``width`` is the ``qreg q[N]`` width the
    WuYue submit payload uses for its ``quanNum`` field.
    """
    qasm = qasm2.dumps(circuit)
    width = 0
    match = re.search(r"qreg\s+q\[(\d+)\];", qasm)
    if match:
        width = int(match.group(1))
    return qasm, width
