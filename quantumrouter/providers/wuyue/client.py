"""WuYue API client — plain-``requests`` bridge to the WuYue cloud.

Implements the Ecloud AK/SK request signing exactly as the upstream
``wuyue.plugin.runner.Runner`` -> ``wuyue.plugin.ecloud`` stack does
(see ``tmp/WuYueSDK-master/wuyue/plugin/ecloud/``): every request has
``AccessKey`` / ``SignatureMethod=HmacSHA256`` / ``SignatureVersion=V2.0``
/ ``Timestamp`` / ``SignatureNonce`` folded into its (canonical, sorted)
query string, and the resulting signature travels as the trailing
``Signature`` query parameter.

No ``wuyue`` package import: the cloud is reached with ``requests`` and
the wire formats are transcribed from the SDK below.

Circuit text arrives already converted from Qiskit by
:mod:`quantumrouter.providers.wuyue.backend.base`; this client only does
submit / query / list.  Every method raises
:class:`~quantumrouter.exceptions.ProviderError` when the cloud rejects a
request (HTTP error, ``code != 1``, or a malformed payload).

Wire notes (verified against the live cloud, 2026-09):
* Submit: signed POST to ``/api/openapi/wyqcloud/external/task/sdk/submit``
  with a JSON body ``{deviceId, name, inData=<qasm>, examNum, quanNum,
  wait, calculatType, ...}``; returns ``{"code": 1, "data": {"taskId", ...}}``.
* Query: signed GET ``.../sdk/info?taskId=<id>``; returns
  ``{"code": 1, "data": {"taskStatus", "outCounts", "outData", ...}}``
  where ``taskStatus == 5`` is success (6 = failure) and ``outCounts`` is a
  JSON string of ``{bitstring: count}`` with ``bitstring[i]`` = outcome of
  classical bit ``i`` (so qiskit keys convert by ``sum(1 << i)``).
* Engine list: signed GET to
  ``/api/openapi/wyqcloud/task/engine/list``; returns
  ``{"code": 1, "body": [{deviceId, bits, engName, status, ...}]}``.
"""

from __future__ import annotations

import datetime
import hashlib
import hmac
import json
import uuid
from typing import Any, Optional
from urllib.parse import quote, unquote_plus

import requests

from ...exceptions import ProviderError
from . import config as endpoints

#: SDK identity header, transcribed from ``ecloud/request.py``.
_PRODUCT = "WYQCLOUD"
_VERSION = "v1"
_SDK_VERSION = "1.0.6"
_CORE_VERSION = "1.0.5"

_ACCESS_KEY = "AccessKey"
_SIG_METHOD = "SignatureMethod"
_SIG_METHOD_VAL = "HmacSHA256"
_SIG_VERSION = "SignatureVersion"
_SIG_VERSION_VAL = "V2.0"
_TIMESTAMP = "Timestamp"
_NONCE = "SignatureNonce"
_SIGNATURE = "Signature"
_SK_PREFIX = "BC_SIGNATURE&"


def _percent_encode(text: str) -> str:
    """Encode like the SDK's ``percent_encode`` (RFC 3986 minus reserved)."""
    return (
        quote(str(text), safe="")
        .replace("+", "%20")
        .replace("*", "%2A")
        .replace("%7E", "~")
    )


def _hmac_sha256_hex(data: str, key: str) -> str:
    return hmac.new(key.encode("utf-8"), data.encode("utf-8"), hashlib.sha256).hexdigest()


def _sha256_hex(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _sign_aksk_path(
    method: str,
    path: str,
    query_params: dict[str, str] | None,
    access_key: str,
    secret_key: str,
) -> str:
    """Fold auth params + signature into ``path`` (SDK ``_sign_aksk``).

    Returns the full signed path ``/uri?AccessKey=...&...&Signature=...``
    that gets appended to the endpoint.
    """
    query = dict(query_params or {})
    query[_ACCESS_KEY] = access_key
    query[_SIG_METHOD] = _SIG_METHOD_VAL
    query[_SIG_VERSION] = _SIG_VERSION_VAL
    query[_TIMESTAMP] = datetime.datetime.now().strftime("%Y-%m-%dT%H:%M:%SZ")
    query[_NONCE] = uuid.uuid4().hex

    canonical = "&".join(
        f"{_percent_encode(k)}={_percent_encode(query[k])}" for k in sorted(query)
    )
    hashed = _sha256_hex(canonical)
    # unquote_plus then percent_encode keeps the path identical for the
    # server, exactly like ``_sign_aksk``.
    servlet_path = unquote_plus(path or "")
    string_to_sign = (
        method.upper() + "\n" + _percent_encode(servlet_path) + "\n" + hashed
    )
    sig = _hmac_sha256_hex(string_to_sign, _SK_PREFIX + secret_key)
    return f"{servlet_path}?{canonical}&{_SIGNATURE}={_percent_encode(sig)}"


def _sdk_headers(action: str) -> dict[str, str]:
    """Headers the SDK always sends (``ecloud/request._append_default_headers``)."""
    return {
        "x-openapi-sdk": (
            f"action:{action};product:{_PRODUCT};version:{_VERSION};"
            f"sdkversion:{_SDK_VERSION};language:Python;coreversion:{_CORE_VERSION}"
        ),
        "User-Agent": "OpenAPI/2.0/Python",
        "Content-Type": "application/json",
    }


class WuYueApiClient:
    """Standardized high-level client for the WuYue quantum cloud.

    Parameters
    ----------
    access_key:
        Mobile-cloud Ecloud ``AccessKey`` ID (first half of
        ``WUYUE_TOKEN``, the ``access+secret`` pair).
    secret_key:
        Mobile-cloud Ecloud ``AccessKey`` secret (second half).
    endpoint:
        Cloud platform base URL; ``None`` uses the official endpoint.
    """

    def __init__(
        self,
        access_key: str,
        secret_key: str,
        endpoint: Optional[str] = None,
    ) -> None:
        if not access_key or not secret_key:
            raise ProviderError(
                "WuYue API credentials are required; set WUYUE_TOKEN in .env "
                "to 'accessKey+secretKey'."
            )
        self.access_key = access_key
        self.secret_key = secret_key
        self.endpoint = (endpoint or endpoints.DEFAULT_ENDPOINT).rstrip("/")

    # ------------------------------------------------------------------ #
    # Transport helpers
    # ------------------------------------------------------------------ #
    def _request(
        self,
        method: str,
        path: str,
        *,
        action: str,
        query: dict[str, str] | None = None,
        body: dict[str, Any] | None = None,
        timeout: float = 60.0,
    ) -> dict[str, Any]:
        """Sign and send one request; return the parsed JSON body."""
        signed_path = _sign_aksk_path(
            method, path, query, self.access_key, self.secret_key
        )
        url = self.endpoint + signed_path
        try:
            resp = requests.request(
                method,
                url,
                headers=_sdk_headers(action),
                data=json.dumps(body) if body is not None else None,
                timeout=timeout,
                verify=False,
            )
            resp.raise_for_status()
        except requests.RequestException as exc:
            raise ProviderError(
                f"Failed to communicate with WuYue cloud ({url}): {exc}"
            ) from exc

        data = _decode_json(resp, url)
        if not isinstance(data, dict):
            raise ProviderError(
                f"WuYue returned non-object JSON from {url}: {data!r}"
            )
        if data.get("code") != 1:
            raise ProviderError(
                f"WuYue request failed: code={data.get('code')} "
                f"msg={data.get('msg')!r} errorCode={data.get('errorCode')!r}"
            )
        return data

    # ------------------------------------------------------------------ #
    # Endpoints
    # ------------------------------------------------------------------ #
    def get_backends(self) -> list[dict]:
        """Return the user's cloud engines, normalized for the provider.

        Each result is ``{"code", "name", "simulator", "n_qubits",
        "description", "labels", "status", "queue_tasks"}`` matching the
        :meth:`WuYueProvider._parse_wuyue_config` reader.
        """
        data = self._request(
            "GET",
            endpoints.ENGINE_LIST_URI,
            action="listEngine",
            timeout=60.0,
        )
        raw_engines = data.get("body") or data.get("data") or []
        if not isinstance(raw_engines, list):
            raise ProviderError(
                f"WuYue engine list returned malformed payload: "
                f"{type(raw_engines).__name__}"
            )

        normalized: list[dict] = []
        for engine in raw_engines:
            if not isinstance(engine, dict):
                continue
            # Only online engines are schedulable (status=1 online, 0 down).
            if engine.get("status") not in (None, 1):
                continue
            dev_code = engine.get("deviceId") or ""
            sim = "sim" in dev_code.lower()
            normalized.append(
                {
                    "code": dev_code,
                    "name": dev_code,
                    "simulator": sim,
                    "n_qubits": int(engine.get("bits") or 0),
                    "description": (
                        f"{engine.get('engName') or dev_code}, "
                        f"pending queue tasks: {engine.get('engQueueTaskNum') or 0}"
                    ),
                    "labels": "0" if sim else "1",
                    "status": int(engine.get("status") or 0),
                    "queue_tasks": int(engine.get("engQueueTaskNum") or 0),
                }
            )
        return normalized

    def submit_job(
        self,
        qasm: str,
        *,
        device_id: str,
        qubits: int,
        shots: int = 1024,
        **task_args: Any,
    ) -> str:
        """Submit one OpenQASM 2 circuit; return the assigned task id."""
        # QuantumRouter-internal run() knobs must not leak into the wire body.
        for internal in ("timeout", "readout_calibration", "auto_transpile"):
            task_args.pop(internal, None)
        body: dict[str, Any] = {
            "name": task_args.pop("name", f"qr_task_{uuid.uuid4().hex[:12]}"),
            "deviceId": device_id,
            "inData": qasm,
            "examNum": shots,
            "quanNum": qubits,
            "calculatType": task_args.pop("calculate_type", 1),
            "wait": True,
        }
        # Forward vendor task knobs verbatim (e.g. isAmend, qubitMapping,
        # gateDecomposition, noiseType, ...); callers use the SDK's
        # snake_case names for the mapped ones above.
        body.update(task_args)

        data = self._request(
            "POST",
            endpoints.SUBMIT_URI,
            action="submitTask",
            body=body,
            timeout=120.0,
        )
        inner = data.get("data") or {}
        task_id = inner.get("taskId") or inner.get("task_id")
        if not task_id:
            raise ProviderError(
                f"WuYue submission did not return a task id: {data!r}"
            )
        return str(task_id)

    def query_job(self, task_ids: list[str]) -> list[dict]:
        """Batch-query remote task status / counts for the given task ids."""
        results: list[dict] = []
        for task_id in task_ids:
            data = self._request(
                "GET",
                endpoints.QUERY_URI,
                action="queryTaskInfo",
                query={"taskId": task_id},
                timeout=60.0,
            )
            inner = data.get("data") or {}
            results.append(
                {
                    "task_id": task_id,
                    "task_status": inner.get("taskStatus"),
                    "out_counts": inner.get("outCounts"),
                    "out_data": inner.get("outData"),
                    "out_probs": inner.get("outProbs"),
                    "out_amps": inner.get("outAmps"),
                    "success": inner.get("taskStatus") == 5,
                    "error": inner.get("msg") or inner.get("outData"),
                    "raw": inner,
                }
            )
        return results


def _decode_json(resp: requests.Response, url: str) -> Any:
    """Parse a JSON body, tolerating the server's GBK-encoded Chinese fields.

    The server returns ``application/json`` without an explicit charset and
    encodes non-ASCII (``engName``, ``clientName``, ...) in GBK.  ``resp.json()``
    would guess UTF-8 and mangle those fields; try UTF-8 first then GBK so the
    parsed dict keeps correct values.  Functional fields (``deviceId``, ints)
    are ASCII either way.
    """
    raw = resp.content
    text = None
    for encoding in ("utf-8", "gbk"):
        try:
            text = raw.decode(encoding)
            break
        except UnicodeDecodeError:
            continue
    if text is None:
        text = raw.decode("utf-8", errors="replace")
    try:
        return json.loads(text)
    except json.JSONDecodeError as exc:
        raise ProviderError(
            f"WuYue returned non-JSON response from {url}: "
            f"{raw[:200]!r}"
        ) from exc


__all__ = ["WuYueApiClient", "_sign_aksk_path", "_percent_encode"]
