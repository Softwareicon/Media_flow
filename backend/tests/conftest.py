"""Test harness.

ALL upstream traffic in this suite is MOCKED: `FakeWeb` stands in for the internet, with
canned responses shaped like each platform's documented API. Passing tests prove our
request/parse/security logic, NOT that a live platform integration works — see
docs/STATUS.md "Live integration checklist" for that.
"""
from __future__ import annotations

import json
import os
from urllib.parse import unquote
from collections.abc import Callable

import httpx
import pytest
from cryptography.fernet import Fernet
from fastapi.testclient import TestClient

from app.config import get_settings
from app.security import ratelimit
from app.security.http_client import SafeHttpClient

PUBLIC_IP = "93.184.216.34"

BASE_ENV = {
    "ENVIRONMENT": "test",
    "AUTO_CREATE_TABLES": "true",
    "TOKEN_ENCRYPTION_KEY": Fernet.generate_key().decode(),
    "PUBLIC_BASE_URL": "https://api.mediaflow.test",
    "RATE_LIMIT_PER_MINUTE": "1000",
    "RATE_LIMIT_AUTH_PER_MINUTE": "1000",
}


class FakeWeb:
    """Routes requests by Host header + path to handlers. Records what was requested."""

    def __init__(self) -> None:
        self.dns: dict[str, list[str]] = {}
        self.routes: dict[tuple[str, str], Callable[[httpx.Request], httpx.Response]] = {}
        self.seen: list[httpx.Request] = []

    # --- registration helpers
    def host(self, name: str, ip: str = PUBLIC_IP) -> None:
        self.dns[name] = [ip]

    def on(self, host: str, path: str, handler: Callable[[httpx.Request], httpx.Response] | httpx.Response) -> None:
        self.host(host) if host not in self.dns else None
        if isinstance(handler, httpx.Response):  # rebuild per request: a Response body can be read only once
            status, headers, body = handler.status_code, dict(handler.headers), handler.read()
            handler = lambda _r: httpx.Response(status, headers=headers, content=body)  # noqa: E731
        self.routes[(host, unquote(path.split("?")[0]))] = handler

    def json(self, host: str, path: str, payload, status: int = 200) -> None:
        self.on(host, path, httpx.Response(status, content=json.dumps(payload).encode(),
                                           headers={"content-type": "application/json"}))

    def file(self, host: str, path: str, body: bytes, content_type: str, total: int | None = None) -> None:
        def handler(req: httpx.Request) -> httpx.Response:
            rng = req.headers.get("range")
            size = total or len(body)
            if rng:
                end = int(rng.split("-")[1])
                return httpx.Response(206, content=body[: end + 1], headers={
                    "content-type": content_type, "content-range": f"bytes 0-{min(end, size - 1)}/{size}"})
            return httpx.Response(200, content=body, headers={"content-type": content_type,
                                                              "content-length": str(size)})
        self.on(host, path, handler)

    # --- plumbing
    async def resolve(self, host: str, port: int) -> list[str]:
        if host in self.dns:
            return self.dns[host]
        raise OSError("NXDOMAIN")

    def handle(self, req: httpx.Request) -> httpx.Response:
        self.seen.append(req)
        host = req.headers.get("host", "").split(":")[0]
        handler = self.routes.get((host, req.url.path))
        if handler is None:
            return httpx.Response(404, content=b"not found", headers={"content-type": "text/plain"})
        return handler(req)

    def client(self) -> SafeHttpClient:
        return SafeHttpClient(allowed_ports=[80, 443], timeout=5, max_redirects=3, resolver=self.resolve,
                              transport=httpx.MockTransport(self.handle))


@pytest.fixture
def web() -> FakeWeb:
    return FakeWeb()


@pytest.fixture
def make_client(tmp_path, monkeypatch, web):
    """Factory: make_client(**extra_env) -> TestClient with a fresh SQLite DB and the FakeWeb."""
    clients: list[TestClient] = []

    def factory(**extra: str) -> TestClient:
        for k, v in {**BASE_ENV, "DATABASE_URL": f"sqlite+aiosqlite:///{tmp_path}/t{len(clients)}.db", **extra}.items():
            monkeypatch.setenv(k, v)
        get_settings.cache_clear()
        ratelimit.backend.reset()
        from app.main import create_app
        app = create_app(get_settings(), http=web.client(), run_background=False)
        c = TestClient(app)
        c.__enter__()
        clients.append(c)
        return c

    yield factory
    for c in clients:
        c.__exit__(None, None, None)
    get_settings.cache_clear()
    for k in os.environ.copy():
        if k.endswith(("_CLIENT_ID", "_CLIENT_SECRET", "_APP_ID", "_APP_SECRET", "_BEARER_TOKEN")):
            monkeypatch.delenv(k, raising=False)


@pytest.fixture
def client(make_client) -> TestClient:
    return make_client()


def auth(c: TestClient) -> dict[str, str]:
    r = c.post("/api/v1/auth/anonymous")
    assert r.status_code == 201, r.text
    return {"Authorization": f"Bearer {r.json()['token']}"}


MP4_HEAD = b"\x00\x00\x00\x20ftypisom\x00\x00\x02\x00isomiso2avc1mp41" + b"\x00" * 32
JPEG_HEAD = b"\xff\xd8\xff\xe0\x00\x10JFIF\x00" + b"\x00" * 50
PNG_HEAD = b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR" + b"\x00" * 50
