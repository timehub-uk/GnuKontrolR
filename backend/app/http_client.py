"""
Shared httpx client factory with container API request signing.
All outbound requests from the panel identify as GnuKontrolR-Browser.
Container API calls get HMAC-signed request/response pairs to prevent MITM.
"""
import hmac
import hashlib
import json
import os
import secrets
from typing import Optional

import httpx

PANEL_UA = "GnuKontrolR-Browser/1.0"
CONTAINER_API_TOKEN = os.environ.get("CONTAINER_API_TOKEN", "")


def _sign_data(key: str, *parts: bytes) -> str:
    mac = hmac.new(key.encode(), b"", hashlib.sha256)
    for p in parts:
        mac.update(p)
    return mac.hexdigest()


def sign_request(token: str, method: str, path: str, body: bytes = b"") -> tuple[str, str]:
    """Return (request_id, signature) for a unique signed request."""
    request_id = secrets.token_hex(16)
    sig = _sign_data(token, method.encode(), path.encode(), request_id.encode(), body)
    return request_id, sig


def verify_response_signature(token: str, request_id: str, body: bytes, sig: str) -> bool:
    """Verify the container's response signature matches."""
    expected = _sign_data(token, request_id.encode(), b"|", body)
    return hmac.compare_digest(sig, expected)


def panel_client(**kwargs) -> httpx.AsyncClient:
    """Return an AsyncClient with the panel User-Agent pre-set."""
    headers = dict(kwargs.pop("headers", {}))
    headers.setdefault("User-Agent", PANEL_UA)
    return _SignedClient(headers=headers, **kwargs)


class _SignedClient(httpx.AsyncClient):
    """AsyncClient that automatically signs container API requests and verifies
    response signatures to prevent replay and MITM attacks."""

    async def request(self, method: str, url: str, **kwargs) -> httpx.Response:
        is_container = "CONTAINER_API_TOKEN" in os.environ and CONTAINER_API_TOKEN
        rid = ""
        if is_container:
            body = kwargs.get("content") or b""
            if not body and "json" in kwargs:
                body = json.dumps(kwargs["json"]).encode()
            if isinstance(body, str):
                body = body.encode()
            rid, sig = sign_request(CONTAINER_API_TOKEN, method, url, body)
            headers = dict(kwargs.pop("headers", {}))
            headers["X-Request-Id"] = rid
            headers["X-Signature"] = sig
            kwargs["headers"] = headers

        response = await super().request(method, url, **kwargs)

        if is_container:
            resp_sig = response.headers.get("X-Response-Signature", "")
            if resp_sig:
                if not verify_response_signature(CONTAINER_API_TOKEN, rid, response.content, resp_sig):
                    raise httpx.HTTPStatusError(
                        "Response signature mismatch — possible MITM attack",
                        request=response.request,
                        response=response,
                    )
        return response
