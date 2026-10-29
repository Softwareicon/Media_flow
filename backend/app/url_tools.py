"""URL extraction and normalization for user-pasted links."""
from __future__ import annotations

import re
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from .security.netguard import UnsafeURLError

_URL_IN_TEXT = re.compile(r"https?://[^\s<>\"'`]+", re.IGNORECASE)
TRACKING_PARAMS = {
    "fbclid", "gclid", "igsh", "igshid", "si", "feature", "mibextid", "ref_src", "ref_url",
    "t_ref", "_r", "_t", "share_id", "utm_source", "utm_medium", "utm_campaign",
    "utm_term", "utm_content", "utm_id", "is_from_webapp", "sender_device", "rdt",
}
# keep params that identify content on some platforms
KEEP_ALWAYS = {"v", "list", "id", "story_fbid", "h", "img_index"}


def extract_url(text: str) -> str:
    """Pull the first link out of pasted text ('Look at this! https://...')."""
    text = (text or "").strip()
    m = _URL_IN_TEXT.search(text)
    if m:
        return m.group(0).rstrip(").,;!?]}'\"")
    if re.fullmatch(r"(www\.)?[a-z0-9-]+(\.[a-z0-9-]+)+(/\S*)?", text, re.IGNORECASE):
        return "https://" + text
    raise UnsafeURLError("invalid_url", "That doesn't look like a link. Paste a full http(s):// URL.")


def normalize_url(raw: str) -> str:
    url = extract_url(raw)
    parts = urlsplit(url)
    scheme = parts.scheme.lower()
    if scheme not in ("http", "https"):
        raise UnsafeURLError("scheme_not_allowed", "Only http and https links are supported.")
    host = (parts.hostname or "").lower().rstrip(".")
    if not host:
        raise UnsafeURLError("invalid_url", "URL has no host.")
    netloc = host
    if parts.port and parts.port not in (80, 443):
        netloc = f"{host}:{parts.port}"
    if parts.username or parts.password:
        raise UnsafeURLError("credentials_in_url", "Links containing usernames or passwords are not allowed.")
    query = [(k, v) for k, v in parse_qsl(parts.query, keep_blank_values=True)
             if k in KEEP_ALWAYS or (k.lower() not in TRACKING_PARAMS and not k.lower().startswith("utm_"))]
    return urlunsplit((scheme, netloc, parts.path or "/", urlencode(query, doseq=True), ""))
