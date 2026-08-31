"""LingYun API client.

Bridges :class:`TransportRequest` / :class:`TransportResponse` to the
endpoints declared in :mod:`config`. Each method returns a parsed
payload (``data``) and raises :class:`ProviderError` (or a subclass)
when the cloud rejects the request.

The client is vendor-specific but transport-agnostic: it doesn't know
whether bytes flow over HTTP or PCIe, only that :meth:`request` sends
and receives.
"""

from __future__ import annotations

from datetime import datetime

from ...exceptions import ProviderError
from ...transport.base import TransportRequest
from . import config as endpoints


def _request_time() -> str:
    """Format the current time for LingYun's ``requestTime`` header."""
    return (
        datetime.now()
        .strftime("%m/%d/%Y, %I:%M:%S %p")
        .replace("/0", "/")
        .lstrip()
        .replace(" 0", " ")
    )


class LingYunApiClient:
    """Transport-backed client for the LingYun REST surface.

    Parameters
    ----------
    transport:
        An open :class:`Transport` used for all requests.
    token:
        Auth token, sent as both ``basicToken`` and ``Authorization``
        (LingYun sends both). May be empty for simulation-server
        access.
    """

    BACKENDS = endpoints.BACKENDS
    COMPUTER_CONFIG = endpoints.COMPUTER_CONFIG
    MACHINE_CONFIG = endpoints.MACHINE_CONFIG
    SUBMIT = endpoints.SUBMIT
    QUERY_RESULT = endpoints.QUERY_RESULT

    def __init__(self, transport, token: str = "") -> None:
        self.transport = transport
        self.token = token

    # ------------------------------------------------------------------ #
    # Internals
    # ------------------------------------------------------------------ #
    def request(self, req: TransportRequest) -> dict:
        """Send a request, validate the envelope, and return ``data``."""
        resp = self.transport.request(req)
        data = resp.json()
        return self._check(data)

    def _headers(self, api_code: str) -> dict:
        return {
            "Accept": "application/json, text/plain, */*",
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:137.0) "
                "Gecko/20100101 Firefox/137.0"
            ),
            "apiCode": api_code,
            "requestTime": _request_time(),
            "basicToken": self.token,
            "Authorization": f"Bearer {self.token}" if self.token else "",
        }

    @staticmethod
    def _check(data: dict, *, ok_code: int | tuple[int, int] = 0) -> dict:
        """Raise ProviderError if the response code is unexpected.

        Returns the ``data`` payload on success.
        """
        if not isinstance(data, dict):
            raise ProviderError(f"LingYun returned non-dict: {data!r}")
        code = data.get("code")
        if isinstance(ok_code, tuple):
            ok = code in ok_code
        else:
            ok = code == ok_code
        if not ok:
            raise ProviderError(
                f"LingYun request failed: code={code}, "
                f"msg={data.get('msg') or data.get('message')}"
            )
        return data.get("data", {})

    # ------------------------------------------------------------------ #
    # Endpoints
    # ------------------------------------------------------------------ #
    def get_backends(self) -> list[dict]:
        """List available quantum backends for the current user."""
        req = TransportRequest(
            url=self.BACKENDS,
            method="GET",
            params={"a": str(int(_now_ms())), "apiCode": "byUser"},
            headers=self._headers("byUser"),
        )
        data = self.request(req)
        if isinstance(data, str):
            import json
            data = json.loads(data) if data else []
        return data or []

    def get_quantum_computer_config(self, computer_id: str) -> dict:
        """Fetch the configuration overview of a quantum computer."""
        req = TransportRequest(
            url=self.COMPUTER_CONFIG,
            method="GET",
            params={
                "a": str(int(_now_ms())),
                "type": "overview",
                "quantumComputerId": computer_id,
                "label": "qubits,couplers,coupler_map,disabled_qubits,disabled_couplers",
            },
            headers=self._headers("config"),
        )
        return self.request(req)

    def get_quantum_machine_config(self, computer_code: str) -> dict:
        """Download the physical machine calibration data."""
        req = TransportRequest(
            url=f"{self.MACHINE_CONFIG}/{computer_code}",
            method="GET",
            headers=self._headers("download_config"),
        )
        data = self.request(req)
        if isinstance(data, str):
            import json
            data = json.loads(data) if data else {}
        return data or {}

    def submit_job(
        self,
        circuits: list[str],
        machine: str,
        *,
        shots: int = 1000,
        language: str = "openqasm3",
    ) -> list:
        """Submit a job and return the assigned task IDs."""
        body = {
            "circuit": circuits,
            "language": language,
            "name": "",
            "lab_id": "",
            "lab_name": "",
            "shots": shots,
            "computerCode": machine,
            "is_verify": True,
        }
        req = TransportRequest(
            url=self.SUBMIT,
            method="POST",
            json=body,
            headers=self._headers("submit"),
        )
        return self.request(req)

    def query_job(self, task_ids: list[str]) -> dict:
        """Fetch results for previously submitted task IDs."""
        req = TransportRequest(
            url=self.QUERY_RESULT,
            method="POST",
            json={"query_ids": task_ids},
            headers=self._headers("config"),
        )
        # query result uses code=0 (not 200) as success
        resp = self.transport.request(req)
        data = resp.json()
        # print("[client.py] data: ", data)
        code = data.get("code")
        if code != 0:
            raise ProviderError(
                f"LingYun query_job failed: code={code}, msg={data.get('msg')}"
            )
        return data.get('data').get('experimentResultModelList')


def _now_ms() -> float:
    """Return current timestamp in milliseconds.

    Kept as a function (not ``time.time`` inline) so it's easy to
    override during testing.
    """
    from time import time
    return time() * 1000
