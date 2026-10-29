"""OAuth 2.0 authorization-code flows for platforms that release a user's OWN media.

The backend is the confidential client: app secrets never reach the phone. Tokens are
Fernet-encrypted at rest and can be revoked by the user (DELETE /connections/{platform}).

Endpoint URLs and scopes below follow each platform's public docs as of Oct 2026 and must be
re-checked during each platform's app review (see docs/STATUS.md, live integration checklist).
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from urllib.parse import urlencode

from .config import Settings
from .security.http_client import SafeHttpClient, UpstreamError


@dataclass(frozen=True)
class Provider:
    key: str
    authorize_url: str
    token_url: str
    scope: str
    token_hosts: tuple[str, ...]
    scope_sep: str = " "

    def client(self, s: Settings) -> tuple[str | None, str | None]:
        cid = getattr(s, f"{self.key}_client_id", None) or getattr(s, f"{self.key}_app_id", None)
        sec = getattr(s, f"{self.key}_client_secret", None) or getattr(s, f"{self.key}_app_secret", None)
        return cid, sec.get_secret_value() if sec else None


def providers(s: Settings) -> dict[str, Provider]:
    v = s.facebook_graph_version
    return {
        "vimeo": Provider("vimeo", "https://api.vimeo.com/oauth/authorize", "https://api.vimeo.com/oauth/access_token",
                          "public private video_files", ("api.vimeo.com",)),
        "instagram": Provider("instagram", "https://www.instagram.com/oauth/authorize",
                              "https://api.instagram.com/oauth/access_token", "instagram_business_basic",
                              ("api.instagram.com", "graph.instagram.com"), ","),
        "facebook": Provider("facebook", f"https://www.facebook.com/{v}/dialog/oauth",
                             f"https://graph.facebook.com/{v}/oauth/access_token",
                             "public_profile,pages_show_list,pages_read_engagement", ("graph.facebook.com",), ","),
        "pinterest": Provider("pinterest", "https://www.pinterest.com/oauth/", "https://api.pinterest.com/v5/oauth/token",
                              "pins:read,boards:read,user_accounts:read", ("api.pinterest.com",), ","),
    }


def redirect_uri(s: Settings, platform: str) -> str:
    return f"{s.public_base_url.rstrip('/')}/api/v1/connections/{platform}/callback"


def authorize_url(s: Settings, p: Provider, state: str) -> str:
    cid, _ = p.client(s)
    q = {"client_id": cid, "redirect_uri": redirect_uri(s, p.key), "response_type": "code", "scope": p.scope,
         "state": state}
    return f"{p.authorize_url}?{urlencode(q)}"


@dataclass
class TokenSet:
    access_token: str
    refresh_token: str | None
    expires_at: datetime | None
    scope: str | None
    account_id: str | None
    username: str | None


def _expiry(seconds) -> datetime | None:
    try:
        return datetime.now(UTC) + timedelta(seconds=int(seconds)) if seconds else None
    except (TypeError, ValueError):
        return None


async def exchange_code(s: Settings, p: Provider, code: str, http: SafeHttpClient) -> TokenSet:
    cid, secret = p.client(s)
    if not cid or not secret:
        raise UpstreamError("not_configured", f"{p.key} is not configured on this server.")
    ru = redirect_uri(s, p.key)
    form = {"grant_type": "authorization_code", "code": code, "redirect_uri": ru}

    if p.key in ("vimeo", "pinterest"):  # client authenticates with HTTP Basic
        resp = await http.request("POST", p.token_url, data=form, auth=(cid, secret), allowed_hosts=p.token_hosts,
                                  headers={"Accept": "application/json"}, follow_redirects=False)
    elif p.key == "instagram":
        resp = await http.request("POST", p.token_url, data={**form, "client_id": cid, "client_secret": secret},
                                  allowed_hosts=p.token_hosts, follow_redirects=False)
    else:  # facebook: GET with query parameters
        q = urlencode({"client_id": cid, "client_secret": secret, "redirect_uri": ru, "code": code})
        resp = await http.request("GET", f"{p.token_url}?{q}", allowed_hosts=p.token_hosts, follow_redirects=False)
    if resp.status != 200:
        raise UpstreamError("oauth_exchange_failed", f"{p.key} rejected the authorization (HTTP {resp.status}).")
    body = resp.json()
    token = body.get("access_token")
    if not token:
        raise UpstreamError("oauth_exchange_failed", f"{p.key} returned no access token.")
    ts = TokenSet(token, body.get("refresh_token"), _expiry(body.get("expires_in")), body.get("scope"),
                  None, None)
    if p.key == "vimeo":
        user = body.get("user") or {}
        ts.account_id, ts.username = (user.get("uri") or "").rsplit("/", 1)[-1] or None, user.get("name")
    elif p.key == "instagram":
        ts.account_id = str(body.get("user_id") or "") or None
        # swap the 1-hour token for a 60-day long-lived token
        q = urlencode({"grant_type": "ig_exchange_token", "client_secret": secret, "access_token": token})
        ll = await http.request("GET", f"https://graph.instagram.com/access_token?{q}",
                                allowed_hosts=("graph.instagram.com",))
        if ll.status == 200:
            lb = ll.json()
            ts.access_token, ts.expires_at = lb.get("access_token", token), _expiry(lb.get("expires_in"))
    return ts
