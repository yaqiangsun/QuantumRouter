"""Qiskit ⇄ LQCloud helpers.

Two jobs live here:

1. :func:`qiskit_circuit_to_ir` — turn a **Qiskit** :class:`~qiskit.QuantumCircuit`
   into the instruction IR the LQCloud cloud executes.  The wire format is
   identical to what the upstream ``lqcloud`` SDK produces for its own
   ``QuantumCircuit`` (``tmp/lqcloud-0.5.0/lqcloud/backend/serialization.py``),
   so the QPU server behaves exactly the same — but the circuit is defined
   in Qiskit, never in ``lqcloud.QuantumCircuit``.

2. Result conversion helpers — translate the server's bitstring counts /
   per-shot memory into Qiskit's hex-key convention (bit ``j`` of the key
   integer = classical bit ``j``'s outcome).

The LQCloud server returns bitstrings where ``bitstring[i]`` is the
outcome of classical bit ``i`` (verified empirically: preparing ``|1⟩`` on
``q0`` and mapping ``q0→c0`` yields ``"10"``).  Qiskit keys an integer by
``k = sum(outcome_j << j)``, so the bitstring is reversed before parsing.
"""

from __future__ import annotations

from typing import Any, Optional, Sequence

from qiskit import QuantumCircuit
from qiskit.circuit import ParameterExpression
from qiskit.circuit.operation import Operation

# ---------------------------------------------------------------------- #
# Platform IR vocabulary
# ---------------------------------------------------------------------- #
#
# The gate names below are the LQCloud **circuit-IR vocabulary** — the
# instruction names the cloud's ``qpu_server`` accepts in ``run_circuit``
# payloads.  Like the upstream ``lqcloud`` SDK (``serialization.py`` /
# ``circuit/gates.py``) this is a *protocol* constant, tied to the server
# version rather than to any one machine: MQ02 / QZ02 / AGate-100 all
# share it.  It changes only when the platform ships a new IR version, at
# which point the SDK also bumps its own hardcoded table.
#
# Verified live on MQ02: ``h, x, rz, cz, s, sdg, t, id, y, z, reset,
# barrier, measure`` are all accepted.  The native two-qubit gate is
# ``cz``; single-qubit rotations are ``rz``.
NATIVE_SINGLE_QUBIT_GATES = frozenset(
    {
        "id",
        "h",
        "x",
        "y",
        "z",
        "s",
        "sdg",
        "t",
        "rz",
    }
)
NATIVE_TWO_QUBIT_GATES = frozenset({"cz"})

#: Control / measurement instructions every LQCloud circuit must use;
#: these are universal and never vary per machine.
_MEASURE_GATES = frozenset({"measure"})
_CONTROL_GATES = frozenset({"barrier"})
_RESET_GATE = "reset"

#: Full serializer vocabulary (the union we can emit on the wire).
SERIALIZABLE_GATES = (
    NATIVE_SINGLE_QUBIT_GATES | NATIVE_TWO_QUBIT_GATES | _MEASURE_GATES | _CONTROL_GATES | {_RESET_GATE}
)


def resolve_native_gates(declared_gates: Optional[Sequence[str]]) -> list[str]:
    """Resolve a backend's declared native gate list against the IR vocabulary.

    The ``/api/v1/qpus`` payload carries a ``native_gates`` field that is
    currently ``None`` on every backend; when a deployment starts
    populating it (or a machine advertises a narrower set), the Target and
    serializer should follow it *inside* the protocol vocabulary rather
    than assume the default full set.

    Returns the intersection of ``declared_gates`` (lowercased) with the
    serializable vocabulary, or the full vocabulary when nothing was
    declared.  A declared gate that is not in the vocabulary is dropped and
    surfaced with a warning — it would mean the platform's IR version is
    newer than this provider knows about, and should be loud instead of
    silently submitting an instruction the server would reject.
    """
    if not declared_gates:
        return sorted(SERIALIZABLE_GATES)
    known = set()
    unknown: list[str] = []
    for name in declared_gates:
        if not isinstance(name, str):
            continue
        key = name.strip().lower()
        if key in SERIALIZABLE_GATES:
            known.add(key)
        else:
            unknown.append(key)
    if unknown:
        import warnings

        warnings.warn(
            "LQCloud backend declares native gate(s) outside this provider's "
            f"IR vocabulary and they were ignored: {sorted(unknown)}. "
            "This usually means the cloud deployed a newer IR version than "
            f"this provider knows (vocabulary: {sorted(SERIALIZABLE_GATES)}).",
            stacklevel=2,
        )
    # Nothing from the declared list survived -> stay conservative with the
    # full vocabulary rather than submitting a circuit with no gates.
    return sorted(known) if known else sorted(SERIALIZABLE_GATES)


class LQCloudCircuitError(ValueError):
    """Raised when a Qiskit circuit cannot be shipped to the LQCloud cloud."""



# ---------------------------------------------------------------------- #
# Qiskit circuit -> LQCloud IR
# ---------------------------------------------------------------------- #
def _gate_params(gate: Operation) -> list[Any]:
    """Return JSON-safe numeric gate parameters.

    Parameters arriving as Qiskit :class:`ParameterExpression` objects are
    bound to floats; the LQCloud wire format only accepts numbers.
    """
    params: list[Any] = []
    for param in getattr(gate, "params", []) or []:
        if isinstance(param, ParameterExpression):
            params.append(float(param))
        elif isinstance(param, complex):
            # ``rz`` etc. may carry a complex phase in edge cases
            params.append([param.real, param.imag])
        else:
            params.append(param)
    return params


def qiskit_circuit_to_ir(
    circuit: QuantumCircuit,
    *,
    coupling_map: Optional[Sequence[Sequence[int]]] = None,
    shot_override: Optional[int] = None,
) -> dict[str, Any]:
    """Convert a *Qiskit* circuit to the LQCloud ``circuit`` payload section.

    Parameters
    ----------
    circuit:
        A Qiskit circuit, already transpiled to the backend's native gate
        set (``h`` / ``rz`` / ``cz`` / ``measure`` / ...).  If it still
        carries composite gates (``cx``, ``ry``, ``u``, ...) those are
        raised as :class:`LQCloudCircuitError` — transpile first.
    coupling_map:
        Optional topology (list of ``[q0, q1]`` adjacent pairs, undirected).
        When given, every two-qubit gate is checked for adjacency so we
        fail fast client-side instead of paying a queue slot.
    shot_override:
        When set, win over ``circuit.metadata`` for the payload's ``shots``
        (the caller passes the per-run shots explicitly).

    Returns
    -------
    The ``circuit`` dict placed under ``command.circuit`` on the wire:
    ``{"n_qubits", "n_clbits", "instructions", "shots", "result_format"}``.
    """
    if not isinstance(circuit, QuantumCircuit):
        raise LQCloudCircuitError(
            "LQCloud backend.run() expects Qiskit QuantumCircuit objects."
        )

    # Unbound symbolic parameters can't travel over the JSON wire.
    unbound = [p.name for p in circuit.parameters]
    if unbound:
        raise LQCloudCircuitError(
            "Circuit contains unbound parameter(s): "
            f"{unbound}. Bind them with qc.assign_parameters(...) before "
            "submitting to the LQCloud cloud."
        )

    instructions: list[dict[str, Any]] = []
    for item in circuit.data:
        gate, qargs, cargs = item.operation, item.qubits, item.clbits
        name = getattr(gate, "name", "").lower()
        qubits = [circuit.find_bit(q).index for q in qargs]
        clbits = [circuit.find_bit(c).index for c in cargs]

        if name in _CONTROL_GATES:
            instructions.append({"name": name, "qubits": qubits, "clbits": [], "params": []})
            continue
        if name in _MEASURE_GATES:
            instructions.append({"name": "measure", "qubits": qubits, "clbits": clbits, "params": []})
            continue
        if name == "reset":
            instructions.append({"name": "reset", "qubits": qubits, "clbits": [], "params": []})
            continue
        if name in NATIVE_SINGLE_QUBIT_GATES:
            instructions.append(
                {"name": name, "qubits": qubits, "clbits": [], "params": _gate_params(gate)}
            )
            continue
        if name in NATIVE_TWO_QUBIT_GATES:
            _check_adjacent(name, qubits, coupling_map)
            instructions.append(
                {"name": name, "qubits": qubits, "clbits": [], "params": _gate_params(gate)}
            )
            continue

        raise LQCloudCircuitError(
            f"Gate {gate.name!r} is not supported by the LQCloud cloud "
            f"(supported: {sorted(NATIVE_SINGLE_QUBIT_GATES | NATIVE_TWO_QUBIT_GATES | _MEASURE_GATES | _CONTROL_GATES)}). "
            "Transpile the circuit to the backend first, e.g. "
            "transpile(qc, backend=backend) or keep auto_transpile=True."
        )

    n_qubits = circuit.num_qubits
    # The server derives memory bitstrings from clbit indices, so the
    # declared width must cover the highest measured clbit (not just
    # ``circuit.num_clbits``, which can be 0 for bare-qubit circuits).
    n_clbits = max(
        (max(inst["clbits"]) + 1 for inst in instructions if inst["name"] == "measure" and inst["clbits"]),
        default=circuit.num_clbits or 0,
    )

    payload: dict[str, Any] = {
        "n_qubits": n_qubits,
        "n_clbits": n_clbits,
        "instructions": instructions,
        "shots": shot_override if shot_override is not None else 1024,
        "result_format": "memory",
    }
    return payload


def _check_adjacent(
    gate_name: str,
    qubits: list[int],
    coupling_map: Optional[Sequence[Sequence[int]]],
) -> None:
    """Fail fast if a two-qubit gate sits on non-adjacent qubits."""
    if len(qubits) != 2 or not coupling_map:
        return
    q0, q1 = qubits
    if q0 == q1:
        return
    edge = {q0, q1}
    if any(edge == {int(a), int(b)} for a, b in coupling_map):
        return
    raise LQCloudCircuitError(
        f"Two-qubit gate {gate_name!r} on qubits {qubits} is not an "
        "adjacent pair of the backend coupling map. Transpile the circuit "
        "to the backend topology first (auto_transpile=True) or use an "
        "adjacent pair — the LQCloud server rejects non-adjacent "
        "two-qubit gates."
    )


# ---------------------------------------------------------------------- #
# Server bitstrings -> qiskit hex keys
# ---------------------------------------------------------------------- #
def bitstring_to_qiskit_key(bitstring: str) -> int:
    """Map an LQCloud bitstring to a Qiskit count/memory integer.

    LQCloud: ``bitstring[i]`` = outcome of classical bit ``i``.  Qiskit:
    integer ``k`` with bit ``j`` = classical bit ``j``'s outcome, i.e.
    ``k = sum(outcome_j << j)`` — the bitstring is parsed reversed.
    """
    return int(str(bitstring)[::-1], 2)


def ir_counts_to_qiskit(counts: dict) -> dict[str, int]:
    """Convert the server's ``{bitstring: count}`` dict to qiskit hex counts."""
    out: dict[str, int] = {}
    for bitstring, count in counts.items():
        key = hex(bitstring_to_qiskit_key(bitstring))
        out[key] = out.get(key, 0) + int(count)
    return out


def ir_memory_to_qiskit(memory: Sequence[str]) -> list[str]:
    """Convert the server's per-shot bitstring list to qiskit hex memory."""
    return [hex(bitstring_to_qiskit_key(s)) for s in memory]
