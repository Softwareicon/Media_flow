"""The only way backend code makes outbound HTTP requests.

* Every hop is vetted by netguard (scheme, port, public IPs only).
* The TCP connection goes to the vetted IP; Host header and TLS SNI/cert check use the
  hostname, so DNS cannot be re-pointed between the check and the connect.
* Redirects are followed manually, re-vetted, never downgraded https -> http, and can be
  pinned to an allow-list of hosts (platform adapters always pin to their API hosts).
* Response bodies are streamed and cut off at `max_bytes`. Nothing is written to disk.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any
from urllib.parse import urljoin, urlsplit, urlunsplit

import httpx

from .netguard import Resolver, UnsafeURLError, VettedTarget, system_resolver, vet_url

REDIRECT_CODES = {301, 302, 303, 307, 308}
DEFAULT_UA = "MediaFlowPro/1.0 (+https://mediaflow.example/bot)"


class UpstreamError(Exception):
    def __init__(self, code: str, message: str, status: int | None = None):
        super().__init__(message)
        self.code = code
        self.status = status


@dataclass
class SafeResponse:
    status: int
    url: str  # final logical URL (hostname, not IP)
    headers: httpx.Headers
    body: bytes = b""
    truncated: bool = False
    redirects: list[str] = field(default_factory=list)

    def json(self) -> Any:
        try:
            return json.loads(self.body.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise UpstreamError("bad_upstream_response", "Upstream returned invalid JSON.") from exc

    @property
    def content_type(self) -> str:
        return self.headers.get("content-type", "").split(";")[0].strip().lower()

    @property
    def content_length(self) -> int | None:
        cr = self.headers.get("content-range")  # bytes 0-31/123456
        if cr and "/" in cr:
            total = cr.rsplit("/", 1)[1].strip()
            if total.isdigit():
                return int(total)
        cl = self.headers.get("content-length")
        return int(cl) if cl and cl.isdigit() else None


def host_matches(host: str, allowed: tuple[str, ...]) -> bool:
    host = host.lower().rstrip(".")
    return any(host == a or host.endswith("." + a) for a in allowed)


def _ip_url(target: VettedTarget) -> str:
    parts = urlsplit(target.url)
    ip = f"[{target.ip}]" if ":" in target.ip else target.ip
    default = 443 if target.scheme == "https" else 80
    netloc = ip if target.port == default else f"{ip}:{target.port}"
    return urlunsplit((target.scheme, netloc, parts.path or "/", parts.query, ""))


class SafeHttpClient:
    def __init__(
        self,
        *,
        allowed_ports: list[int],
        timeout: float = 10.0,
        max_redirects: int = 3,
        resolver: Resolver = system_resolver,
        transport: httpx.AsyncBaseTransport | None = None,
    ):
        self.allowed_ports = allowed_ports
        self.max_redirects = max_redirects
        self.resolver = resolver
        self._client = httpx.AsyncClient(
            timeout=httpx.Timeout(timeout, connect=min(timeout, 5.0)),
            follow_redirects=False,
            trust_env=False,  # never route through an env-configured proxy that skips our checks
            transport=transport,
            headers={"User-Agent": DEFAULT_UA},
        )

    async def aclose(self) -> None:
        await self._client.aclose()

    async def request(
        self,
        method: str,
        url: str,
        *,
        headers: dict[str, str] | None = None,
        data: dict[str, str] | None = None,
        auth: tuple[str, str] | None = None,
        max_bytes: int = 1024 * 1024,
        allowed_hosts: tuple[str, ...] | None = None,
        blocked_hosts: tuple[str, ...] | None = None,
        follow_redirects: bool = True,
    ) -> SafeResponse:
        current = url
        redirects: list[str] = []
        for _hop in range(self.max_redirects + 1):
            target = await vet_url(current, self.allowed_ports, self.resolver)
            if allowed_hosts is not None and not host_matches(target.host, allowed_hosts):
                raise UnsafeURLError("host_not_allowed", f"Requests to {target.host} are not allowed here.")
            if blocked_hosts and host_matches(target.host, blocked_hosts):  # checked on EVERY hop, incl. redirects
                raise UnsafeURLError("host_blocked", f"Requests to {target.host} are blocked.")
            if _hop == 0:
                first_host = target.host
            host_hdr = f"[{target.host}]" if ":" in target.host else target.host  # IPv6 literals need brackets
            req_headers = {"Host": host_hdr if target.port in (80, 443) else f"{host_hdr}:{target.port}"}
            for k, v in (headers or {}).items():
                # never forward credentials to a different host after a redirect
                if target.host != first_host and k.lower() in ("authorization", "cookie", "proxy-authorization"):
                    continue
                req_headers[k] = v
            extensions = {"sni_hostname": target.host} if target.scheme == "https" else {}
            request = self._client.build_request(
                method, _ip_url(target), headers=req_headers, data=data, extensions=extensions,
            )
            try:
                # credentials only ever go to the first hop, never to a redirect target
                resp = await self._client.send(request, stream=True, auth=auth if _hop == 0 else None)
            except httpx.TimeoutException as exc:
                raise UpstreamError("upstream_timeout", "The remote server took too long to respond.") from exc
            except httpx.HTTPError as exc:
                raise UpstreamError("upstream_unreachable", "The remote server could not be reached.") from exc
            try:
                if follow_redirects and resp.status_code in REDIRECT_CODES and "location" in resp.headers:
                    nxt = urljoin(current, resp.headers["location"])
                    if target.scheme == "https" and urlsplit(nxt).scheme.lower() == "http":
                        raise UnsafeURLError("unsafe_redirect", "The link redirects from https to plain http.")
                    redirects.append(nxt)
                    current = nxt
                    if resp.status_code == 303:
                        method, data = "GET", None
                    continue
                body = bytearray()
                truncated = False
                if method.upper() != "HEAD":
                    async for chunk in resp.aiter_bytes():
                        room = max_bytes - len(body)
                        if len(chunk) > room:
                            body.extend(chunk[:room])
                            truncated = True
                            break
                        body.extend(chunk)
                return SafeResponse(resp.status_code, current, resp.headers, bytes(body), truncated, redirects)
            finally:
                await resp.aclose()
        raise UnsafeURLError("too_many_redirects", "The link redirects too many times.")

    async def get_json(self, url: str, *, allowed_hosts: tuple[str, ...], headers: dict[str, str] | None = None,
                       max_bytes: int = 2 * 1024 * 1024) -> Any:
        resp = await self.request("GET", url, headers={"Accept": "application/json", **(headers or {})},
                                  allowed_hosts=allowed_hosts, max_bytes=max_bytes)
        if resp.status in (401, 403):
            raise UpstreamError("upstream_forbidden", "The platform refused access to this item.", resp.status)
        if resp.status == 404:
            raise UpstreamError("not_found", "The platform says this item does not exist or is private.", 404)
        if resp.status == 429:
            raise UpstreamError("upstream_rate_limited", "The platform is rate-limiting requests. Try again later.", 429)
        if resp.status >= 400:
            raise UpstreamError("upstream_error", f"The platform returned HTTP {resp.status}.", resp.status)
        if resp.truncated:
            raise UpstreamError("bad_upstream_response", "Platform response was larger than expected.")
        return resp.json()

    async def probe(self, url: str, *, allowed_hosts: tuple[str, ...] | None = None, sniff_bytes: int = 64,
                    headers: dict[str, str] | None = None,
                    blocked_hosts: tuple[str, ...] | None = None) -> SafeResponse:
        """Fetch only the first bytes of a resource: gives real MIME, magic bytes and total size."""
        return await self.request(
            "GET", url, headers={"Range": f"bytes=0-{sniff_bytes - 1}", **(headers or {})},
            max_bytes=sniff_bytes, allowed_hosts=allowed_hosts, blocked_hosts=blocked_hosts,
        )
