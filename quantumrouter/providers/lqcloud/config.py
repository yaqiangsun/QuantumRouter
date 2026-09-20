"""Endpoint paths and server defaults for the LQCloud quantum service.

Mirrors the wire surface of the upstream ``lqcloud`` SDK (see
``tmp/lqcloud-0.5.0/``) so the same cloud can be reached **without**
importing the SDK or its own ``QuantumCircuit``: circuit definition
stays in Qiskit, and only the remote request compute service is used.

All paths are relative to :data:`DEFAULT_URL`; the API is
token-authenticated via the ``X-API-Key`` header (and a redundant
``Authorization: Bearer`` for older gateways).
"""

from __future__ import annotations

# Official LQCloud base URL (also the SDK's ``DEFAULT_URL``).
DEFAULT_URL = "https://cloud.logicalqubit.com"

# Backend discovery — GET returns the backend list (name, qubits,
# topology, supported_measurement_types, ...).
QPUS = "/api/v1/qpus"

# Circuit submission — POST ``{command, qpu_name}`` returns
# ``{task_id, status, queue_position, ...}``.
# Polling uses the per-task endpoint ``GET /api/v1/tasks/async/{task_id}``.
TASKS_ASYNC = "/api/v1/tasks/async"
