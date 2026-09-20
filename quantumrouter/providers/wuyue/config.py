"""Endpoint paths and server defaults for the WuYue quantum service.

Mirrors the wire surface of the upstream ``wuyue`` SDK (see
``tmp/WuYueSDK-master/``) so the same cloud can be reached **without**
importing the SDK or any of its heavy deps (cirq / pennylane / torch /
pycryptodome ...): circuit definition stays in Qiskit, and only the
remote request compute service is used.

Auth is the Ecloud AK/SK signature scheme (``AccessKey`` /
``SignatureMethod=HmacSHA256`` / ``SignatureVersion=V2.0`` /
``Timestamp`` / ``SignatureNonce``) applied to the query string; see
:mod:`quantumrouter.providers.wuyue.client`.

All paths are relative to :data:`DEFAULT_ENDPOINT` (the SDK's
``DEFAULT_ENDPOINT`` in ``wuyue.plugin.ecloud.utils``).
"""

from __future__ import annotations

# Official WuYue Ecloud base URL (same as the SDK's DEFAULT_ENDPOINT).
DEFAULT_ENDPOINT = "https://ecloud.10086.cn"

# Backend discovery — signed GET returns ``{"code": 1, "body": [...]}``
# with one dict per engine (deviceId, bits, engName, status, ...).
# (Not part of the public SDK's WuyueClient; used by QuantumRouter's
# vendor client to list the user's usable engines.)
ENGINE_LIST_URI = "/api/openapi/wyqcloud/task/engine/list"

# Circuit submission — signed POST with a JSON task body returns
# ``{"code": 1, "data": {"taskId": ..., ...}}``.
SUBMIT_URI = "/api/openapi/wyqcloud/external/task/sdk/submit"

# Task status query — signed GET with ``taskId`` query param returns
# ``{"code": 1, "data": {"taskStatus": ..., "outCounts": ..., ...}}``.
QUERY_URI = "/api/openapi/wyqcloud/external/task/sdk/info"
