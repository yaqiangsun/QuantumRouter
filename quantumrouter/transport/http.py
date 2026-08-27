"""HTTP transport.

Adapts the generic :class:`TransportRequest`/`:class:`TransportResponse`
contract onto ``requests.Session``. This is the transport used by the
default LingYun provider, and by any future provider whose service is
an HTTP endpoint.
"""

from __future__ import annotations

import json as _json

import requests

from ..exceptions import ConnectionError, TimeoutError, TransportError
from .base import Transport, TransportRequest, TransportResponse


class HttpTransport(Transport):
    """Transport over HTTP(S) using a ``requests.Session``.

    Parameters
    ----------
    base_url:
        The base URL (scheme + host + optional port) the session
        targets. Request URLs that already include a scheme are sent
        verbatim; relative URLs are joined to ``base_url``.
    timeout:
        Default request deadline in seconds. Overridden by
        ``TransportRequest.timeout`` when set.
    session:
        Optional pre-built ``requests.Session`` (e.g. with custom auth
        or retry adapters). One is created if not supplied.
    """

    def __init__(
        self,
        base_url: str,
        timeout: float = 30.0,
        session: requests.Session | None = None,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self.session = session or requests.Session()
        self._opened = session is not None  # external session = already open

    def open(self) -> None:
        """Mark the transport as open.

        ``requests.Session`` doesn't require explicit opening, but
        honoring the lifecycle keeps the interface uniform with PCIe
        and lets callers use ``with`` blocks reliably.
        """
        self._opened = True

    def close(self) -> None:
        """Close the underlying session if we own it."""
        if self.session is not None:
            self.session.close()
        self._opened = False

    def request(self, req: TransportRequest) -> TransportResponse:
        """Send ``req`` over the session and return the raw response."""
        if not self._opened:
            self.open()

        url = self._resolve_url(req.url)

        try:
            response = self.session.request(
                method=req.method,
                url=url,
                json=req.json,
                params=req.params,
                headers=req.headers,
                data=req.data,
                timeout=req.timeout or self.timeout,
            )
        except requests.exceptions.Timeout as exc:
            raise TimeoutError(
                f"Timeout after {req.timeout or self.timeout}s: {req.method} {url}"
            ) from exc
        except requests.exceptions.ConnectionError as exc:
            raise ConnectionError(
                f"Failed to connect to {url}: {exc}"
            ) from exc
        except requests.exceptions.RequestException as exc:
            raise TransportError(f"Transport request failed: {exc}") from exc

        return self._parse(response)

    # ------------------------------------------------------------------ #
    # Internals
    # ------------------------------------------------------------------ #
    def _resolve_url(self, url: str) -> str:
        """Join a relative URL to base_url, or pass an absolute one through."""
        if url.startswith(("http://", "https://")):
            return url
        if not url.startswith("/"):
            url = "/" + url
        return f"{self.base_url}{url}"

    @staticmethod
    def _parse(response: requests.Response) -> TransportResponse:
        """Convert a requests.Response into our TransportResponse."""
        raw = response.content or b""
        json_data: dict | None = None
        if raw:
            try:
                parsed = _json.loads(raw)
                if isinstance(parsed, dict):
                    json_data = parsed
            except (ValueError, _json.JSONDecodeError):
                json_data = None
        return TransportResponse(
            status_code=response.status_code,
            raw=raw,
            json_data=json_data,
            headers=dict(response.headers),
        )
