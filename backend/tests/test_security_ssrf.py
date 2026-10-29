"""SSRF, redirect and URL-safety tests."""
from __future__ import annotations

import httpx
import pytest

from app.security.netguard import UnsafeURLError, is_public_ip, parse_and_check_url, system_resolver, vet_url

from .conftest import MP4_HEAD

PORTS = [80, 443]


@pytest.mark.parametrize("ip", [
    "127.0.0.1", "127.255.255.254", "10.0.0.1", "172.16.5.4", "192.168.1.1", "169.254.169.254", "100.64.0.1",
    "0.0.0.0", "224.0.0.1", "255.255.255.255", "::1", "::", "fe80::1", "fc00::1", "fd00:ec2::254",
    "::ffff:127.0.0.1", "::ffff:10.0.0.1", "2002:0a00:0001::1", "64:ff9b::a00:1", "198.18.0.1", "fec0::1",
])
def test_non_public_ips_rejected(ip):
    assert not is_public_ip(ip)


@pytest.mark.parametrize("ip", ["93.184.216.34", "8.8.8.8", "2606:4700:4700::1111", "1.1.1.1"])
def test_public_ips_allowed(ip):
    assert is_public_ip(ip)


@pytest.mark.parametrize("url,code", [
    ("ftp://example.com/a.mp4", "scheme_not_allowed"),
    ("file:///etc/passwd", "scheme_not_allowed"),
    ("javascript:alert(1)", "scheme_not_allowed"),
    ("gopher://example.com/", "scheme_not_allowed"),
    ("http://user:pass@example.com/", "credentials_in_url"),
    ("http://example.com:22/", "port_not_allowed"),
    ("http://example.com:6379/", "port_not_allowed"),
    ("http://localhost/", "host_not_allowed"),
    ("http://foo.localhost/", "host_not_allowed"),
    ("http://metadata.google.internal/computeMetadata/v1/", "host_not_allowed"),
    ("http://db.internal/", "host_not_allowed"),
    ("http://127.0.0.1/", "private_address"),
    ("http://[::1]/", "private_address"),
    ("http://169.254.169.254/latest/meta-data/", "private_address"),
    ("http://[::ffff:169.254.169.254]/", "private_address"),
    ("http://10.1.2.3/x.mp4", "private_address"),
    ("http://exa mple.com/", "invalid_url"),
    ("http://example.com/\r\nHost: evil", "invalid_url"),
])
def test_static_url_checks(url, code):
    with pytest.raises(UnsafeURLError) as e:
        parse_and_check_url(url, PORTS)
    assert e.value.code == code


@pytest.mark.parametrize("url", ["http://2130706433/", "http://0x7f000001/", "http://0177.0.0.1/", "http://127.1/"])
async def test_numeric_encodings_of_loopback_blocked_after_resolution(url):
    # getaddrinfo turns these into 127.0.0.1 — no network needed for numeric hosts
    with pytest.raises(UnsafeURLError) as e:
        await vet_url(url, PORTS, system_resolver)
    assert e.value.code == "private_address"


async def test_hostname_resolving_to_private_ip_blocked(web):
    web.host("evil.example", "10.0.0.5")
    with pytest.raises(UnsafeURLError) as e:
        await vet_url("https://evil.example/a.mp4", PORTS, web.resolve)
    assert e.value.code == "private_address"


async def test_any_private_answer_in_multi_record_dns_blocks(web):
    web.dns["mixed.example"] = ["93.184.216.34", "127.0.0.1"]
    with pytest.raises(UnsafeURLError):
        await vet_url("https://mixed.example/", PORTS, web.resolve)


async def test_connection_pinned_to_vetted_ip(web):
    web.file("cdn.example", "/v.mp4", MP4_HEAD, "video/mp4")
    http = web.client()
    resp = await http.probe("https://cdn.example/v.mp4")
    assert resp.status == 206
    req = web.seen[-1]
    assert req.url.host == "93.184.216.34"  # TCP goes to the IP we checked…
    assert req.headers["host"] == "cdn.example"  # …while Host/SNI keep the name
    assert req.extensions.get("sni_hostname") == "cdn.example"
    await http.aclose()


async def test_redirect_to_internal_address_blocked(web):
    web.on("site.example", "/go", httpx.Response(302, headers={"location": "http://169.254.169.254/latest/"}))
    http = web.client()
    with pytest.raises(UnsafeURLError) as e:
        await http.request("GET", "https://site.example/go")
    assert e.value.code in ("private_address", "unsafe_redirect")
    await http.aclose()


async def test_redirect_to_host_resolving_private_blocked(web):
    web.host("internal-looking.example", "192.168.0.10")
    web.on("site.example", "/go", httpx.Response(301, headers={"location": "https://internal-looking.example/x"}))
    http = web.client()
    with pytest.raises(UnsafeURLError) as e:
        await http.request("GET", "https://site.example/go")
    assert e.value.code == "private_address"
    await http.aclose()


async def test_https_to_http_downgrade_blocked(web):
    web.on("site.example", "/go", httpx.Response(302, headers={"location": "http://site.example/plain"}))
    http = web.client()
    with pytest.raises(UnsafeURLError) as e:
        await http.request("GET", "https://site.example/go")
    assert e.value.code == "unsafe_redirect"
    await http.aclose()


async def test_redirect_loop_stops(web):
    web.on("loop.example", "/a", httpx.Response(302, headers={"location": "/b"}))
    web.on("loop.example", "/b", httpx.Response(302, headers={"location": "/a"}))
    http = web.client()
    with pytest.raises(UnsafeURLError) as e:
        await http.request("GET", "https://loop.example/a")
    assert e.value.code == "too_many_redirects"
    await http.aclose()


async def test_redirect_outside_allowlist_blocked(web):
    web.on("api.vimeo.com", "/x", httpx.Response(302, headers={"location": "https://attacker.example/steal"}))
    web.host("attacker.example")
    http = web.client()
    with pytest.raises(UnsafeURLError) as e:
        await http.request("GET", "https://api.vimeo.com/x", allowed_hosts=("api.vimeo.com",))
    assert e.value.code == "host_not_allowed"
    await http.aclose()


async def test_credentials_not_forwarded_across_hosts(web):
    web.on("a.example", "/start", httpx.Response(302, headers={"location": "https://b.example/next"}))
    web.on("b.example", "/next", httpx.Response(200, content=b"ok"))
    http = web.client()
    await http.request("GET", "https://a.example/start", headers={"Authorization": "Bearer secret"})
    first, second = web.seen[-2], web.seen[-1]
    assert first.headers.get("authorization") == "Bearer secret"
    assert "authorization" not in second.headers
    await http.aclose()


async def test_body_capped_at_max_bytes(web):
    web.on("big.example", "/huge", httpx.Response(200, content=b"x" * 50_000))
    http = web.client()
    resp = await http.request("GET", "https://big.example/huge", max_bytes=1000)
    assert len(resp.body) == 1000 and resp.truncated
    await http.aclose()


def test_api_rejects_unsafe_urls(client):
    from .conftest import auth
    h = auth(client)
    for url in ("http://127.0.0.1/a.mp4", "file:///etc/passwd", "http://169.254.169.254/", "http://localhost:8000/x"):
        r = client.post("/api/v1/media/analyze", json={"url": url}, headers=h)
        assert r.status_code == 422, (url, r.text)
        assert r.json()["code"] in ("private_address", "scheme_not_allowed", "host_not_allowed", "port_not_allowed",
                                    "invalid_url")


async def test_ipv6_literal_host_header_bracketed(web):
    web.dns["2606:4700:4700::1111"] = ["2606:4700:4700::1111"]
    web.routes[("[2606:4700:4700::1111]", "/a")] = lambda r: httpx.Response(200, content=b"ok")
    http = web.client()
    await http.request("GET", "https://[2606:4700:4700::1111]/a")
    assert web.seen[-1].headers["host"] == "[2606:4700:4700::1111]"
    await http.aclose()
