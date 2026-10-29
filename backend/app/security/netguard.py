"""SSRF defences: URL validation, DNS resolution and IP classification.

Rules (enforced on the first request AND on every redirect hop):
* scheme must be http or https; no credentials in the URL; port must be allow-listed
* the hostname must resolve, and EVERY resolved address must be publicly routable
  (no loopback, private, link-local, CGNAT, multicast, reserved, unspecified,
  IPv4-mapped/6to4/Teredo wrappers of those, or cloud metadata addresses)
* the connection is then made to the vetted IP itself (see http_client), so a second
  DNS answer cannot swap in an internal address (DNS rebinding)
"""
from __future__ import annotations

import asyncio
import ipaddress
import socket
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from urllib.parse import urlsplit

IPAddress = ipaddress.IPv4Address | ipaddress.IPv6Address
Resolver = Callable[[str, int], Awaitable[list[str]]]

BLOCKED_HOSTNAMES = {
    "localhost",
    "localhost.localdomain",
    "metadata",
    "metadata.google.internal",
    "metadata.goog",
    "instance-data",
    "instance-data.ec2.internal",
}
BLOCKED_SUFFIXES = (".localhost", ".local", ".internal", ".intranet", ".lan", ".home.arpa", ".corp")

# Ranges ipaddress.is_global does not reject on every Python version, listed explicitly.
EXTRA_BLOCKED_NETS = [
    ipaddress.ip_network(n)
    for n in (
        "0.0.0.0/8",
        "100.64.0.0/10",  # CGNAT
        "169.254.0.0/16",  # link-local incl. 169.254.169.254 metadata
        "192.0.0.0/24",
        "192.0.2.0/24",
        "198.18.0.0/15",
        "198.51.100.0/24",
        "203.0.113.0/24",
        "224.0.0.0/4",
        "240.0.0.0/4",
        "fd00:ec2::254/128",  # AWS IPv6 metadata
        "fc00::/7",
        "fec0::/10",  # deprecated site-local
        "fe80::/10",
        "ff00::/8",
        "64:ff9b::/96",  # NAT64 can wrap private v4
        "64:ff9b:1::/48",
    )
]


class UnsafeURLError(ValueError):
    """Raised when a URL or destination fails the SSRF policy. `code` is machine-readable."""

    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code


@dataclass(frozen=True)
class VettedTarget:
    url: str
    scheme: str
    host: str  # IDNA-encoded hostname as it must appear in Host/SNI
    port: int
    ip: str


def _embedded_v4(addr: ipaddress.IPv6Address) -> ipaddress.IPv4Address | None:
    if addr.ipv4_mapped:
        return addr.ipv4_mapped
    if addr.sixtofour:
        return addr.sixtofour
    if addr.teredo:
        return addr.teredo[1]
    return None


def is_public_ip(raw: str | IPAddress) -> bool:
    try:
        addr = ipaddress.ip_address(raw) if isinstance(raw, str) else raw
    except ValueError:
        return False
    if isinstance(addr, ipaddress.IPv6Address):
        inner = _embedded_v4(addr)
        if inner is not None and not is_public_ip(inner):
            return False
    if any(addr.version == net.version and addr in net for net in EXTRA_BLOCKED_NETS):
        return False
    return bool(addr.is_global) and not (
        addr.is_private
        or addr.is_loopback
        or addr.is_link_local
        or addr.is_multicast
        or addr.is_reserved
        or addr.is_unspecified
    )


def parse_and_check_url(url: str, allowed_ports: list[int]) -> tuple[str, str, int]:
    """Static checks that need no DNS. Returns (scheme, idna_host, port)."""
    if not isinstance(url, str) or len(url) > 2048:
        raise UnsafeURLError("invalid_url", "URL is missing or too long.")
    if any(ch in url for ch in ("\r", "\n", "\t", "\x00", " ")):
        raise UnsafeURLError("invalid_url", "URL contains whitespace or control characters.")
    try:
        parts = urlsplit(url)
        port = parts.port
    except ValueError as exc:
        raise UnsafeURLError("invalid_url", f"URL could not be parsed: {exc}") from exc
    scheme = parts.scheme.lower()
    if scheme not in ("http", "https"):
        raise UnsafeURLError("scheme_not_allowed", "Only http and https links are supported.")
    if parts.username is not None or parts.password is not None:
        raise UnsafeURLError("credentials_in_url", "Links containing usernames or passwords are not allowed.")
    host = (parts.hostname or "").rstrip(".").lower()
    if not host:
        raise UnsafeURLError("invalid_url", "URL has no host.")
    try:
        host = host.encode("idna").decode("ascii")
    except UnicodeError as exc:
        raise UnsafeURLError("invalid_url", "Hostname is not a valid domain name.") from exc
    port = port or (443 if scheme == "https" else 80)
    if port not in allowed_ports:
        raise UnsafeURLError("port_not_allowed", f"Port {port} is not allowed.")
    if host in BLOCKED_HOSTNAMES or host.endswith(BLOCKED_SUFFIXES):
        raise UnsafeURLError("host_not_allowed", "That host is not reachable from this service.")
    # A literal IP must be public. Note getaddrinfo also turns "2130706433" / "0x7f.1" into
    # 127.0.0.1, which the resolution step below catches.
    try:
        literal = ipaddress.ip_address(host.strip("[]"))
    except ValueError:
        literal = None
    if literal is not None and not is_public_ip(literal):
        raise UnsafeURLError("private_address", "Links to private or local network addresses are not allowed.")
    return scheme, host, port


async def system_resolver(host: str, port: int) -> list[str]:
    loop = asyncio.get_running_loop()
    infos = await asyncio.wait_for(
        loop.getaddrinfo(host.strip("[]"), port, type=socket.SOCK_STREAM), timeout=5
    )
    return sorted({info[4][0] for info in infos})


async def vet_url(url: str, allowed_ports: list[int], resolver: Resolver = system_resolver) -> VettedTarget:
    scheme, host, port = parse_and_check_url(url, allowed_ports)
    try:
        addresses = await resolver(host, port)
    except (OSError, asyncio.TimeoutError) as exc:
        raise UnsafeURLError("dns_failure", "The link's domain could not be resolved.") from exc
    if not addresses:
        raise UnsafeURLError("dns_failure", "The link's domain could not be resolved.")
    for addr in addresses:
        if not is_public_ip(addr.split("%")[0]):
            raise UnsafeURLError("private_address", "The link resolves to a private or local network address.")
    return VettedTarget(url=url, scheme=scheme, host=host, port=port, ip=addresses[0])
