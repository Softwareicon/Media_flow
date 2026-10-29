"""Connect / disconnect a user's own platform account (OAuth authorization-code flow).

Three steps, so a token can only ever be attached to the account that STARTED the flow:

1. `POST /connections/{p}/start` (authenticated) → `authorize_url` + a secret `verifier` that only the
   starting app holds (the server keeps just its SHA-256).
2. The provider redirects the browser to `GET /connections/{p}/callback`. The server exchanges the
   code and parks the token, encrypted, next to a one-time `handoff` code, then deep-links back to
   the app with that handoff. Nothing is attached to any account yet.
3. `POST /connections/{p}/complete {handoff, verifier}` (authenticated) — must come from the same user
   that started the flow AND present the verifier. Only then is the connection stored.

This blocks "login CSRF" style attacks: if an attacker sends their own authorize_url to a victim, the
victim's approval lands on the victim's device (attacker never sees the handoff), and the victim's app
can't complete it (wrong user, no verifier).
"""
from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from urllib.parse import urlencode

from fastapi import APIRouter, Request, Response
from fastapi.responses import RedirectResponse
from pydantic import BaseModel, Field
from sqlalchemy import delete, select

from ..models import OAuthConnection, OAuthState
from ..oauth import authorize_url, exchange_code, providers
from ..security import ratelimit
from ..security.crypto import constant_eq, get_cipher, new_token, token_digest
from ..security.http_client import UpstreamError
from ..security.netguard import UnsafeURLError
from .deps import DbDep, HttpDep, SettingsDep, UserDep, err

router = APIRouter(tags=["connections"])
FLOW_TTL = timedelta(minutes=10)


class CompleteBody(BaseModel):
    handoff: str = Field(min_length=20, max_length=128)
    verifier: str = Field(min_length=20, max_length=128)


def _aware(dt: datetime) -> datetime:
    return dt if dt.tzinfo else dt.replace(tzinfo=UTC)


def _app_redirect(settings, platform: str, status: str, handoff: str | None = None) -> RedirectResponse:
    q = {"platform": platform, "status": status, **({"handoff": handoff} if handoff else {})}
    return RedirectResponse(f"{settings.app_redirect_scheme}://connections?{urlencode(q)}", status_code=302)


@router.get("/connections")
async def list_connections(user: UserDep, db: DbDep, settings: SettingsDep) -> list[dict]:
    rows = (await db.execute(select(OAuthConnection).where(OAuthConnection.user_id == user.id))).scalars().all()
    by = {r.platform: r for r in rows}
    out = []
    for key, p in providers(settings).items():
        cid, sec = p.client(settings)
        r = by.get(key)
        out.append({"platform": key, "configured": bool(cid and sec and get_cipher().available),
                    "connected": r is not None, "username": r.external_username if r else None,
                    "expires_at": r.expires_at if r else None})
    return out


@router.post("/connections/{platform}/start")
async def start(platform: str, request: Request, user: UserDep, db: DbDep, settings: SettingsDep) -> dict:
    ratelimit.enforce(request, "oauth", user.id, settings.rate_limit_auth_per_minute)
    p = providers(settings).get(platform)
    if not p:
        raise err(404, "unknown_platform", "That platform has no account connection.")
    cid, sec = p.client(settings)
    if not (cid and sec) or not get_cipher().available:
        raise err(503, "not_configured", f"{platform.title()} connections aren't set up on this server.")
    state, verifier = new_token(), new_token()
    db.add(OAuthState(state_hash=token_digest(state), user_id=user.id, platform=platform,
                      code_verifier=token_digest(verifier), expires_at=datetime.now(UTC) + FLOW_TTL))
    await db.commit()
    return {"authorize_url": authorize_url(settings, p, state), "verifier": verifier,
            "return_url": f"{settings.app_redirect_scheme}://connections"}


@router.get("/connections/{platform}/callback", include_in_schema=False)
async def callback(platform: str, db: DbDep, http: HttpDep, settings: SettingsDep, code: str | None = None,
                   state: str | None = None, error: str | None = None):
    p = providers(settings).get(platform)
    if not p or not state:
        return _app_redirect(settings, platform, "error")
    st = await db.get(OAuthState, token_digest(state[:128]))
    if not st or st.platform != platform or st.handoff_hash is not None or _aware(st.expires_at) <= datetime.now(UTC):
        if st:  # wrong platform / replay / expired: burn the state
            await db.delete(st)
            await db.commit()
        return _app_redirect(settings, platform, "expired")
    if error or not code:
        await db.delete(st)
        await db.commit()
        return _app_redirect(settings, platform, "denied")
    try:
        ts = await exchange_code(settings, p, code[:2048], http)
    except (UpstreamError, UnsafeURLError, KeyError):
        await db.delete(st)
        await db.commit()
        return _app_redirect(settings, platform, "error")
    handoff = new_token()
    st.handoff_hash = token_digest(handoff)
    st.token_payload_enc = get_cipher().encrypt(json.dumps({
        "access_token": ts.access_token, "refresh_token": ts.refresh_token,
        "expires_at": ts.expires_at.isoformat() if ts.expires_at else None, "scope": ts.scope,
        "account_id": ts.account_id, "username": ts.username}))
    st.expires_at = datetime.now(UTC) + timedelta(minutes=5)  # short window to complete
    await db.commit()
    return _app_redirect(settings, platform, "pending", handoff)


@router.post("/connections/{platform}/complete")
async def complete(platform: str, body: CompleteBody, request: Request, user: UserDep, db: DbDep,
                   settings: SettingsDep) -> dict:
    ratelimit.enforce(request, "oauth", user.id, settings.rate_limit_auth_per_minute)
    st = (await db.execute(select(OAuthState).where(OAuthState.handoff_hash == token_digest(body.handoff)))
          ).scalar_one_or_none()
    ok = bool(st and st.platform == platform and st.user_id == user.id and st.code_verifier
              and constant_eq(st.code_verifier, token_digest(body.verifier)) and st.token_payload_enc
              and _aware(st.expires_at) > datetime.now(UTC))
    if st:
        await db.delete(st)  # single use, whether or not it succeeds
        await db.commit()
    if not ok:
        raise err(403, "connection_not_verified", "This connection couldn't be verified. Start it again from the app.")
    data = json.loads(get_cipher().decrypt(st.token_payload_enc) or "{}")  # type: ignore[union-attr]
    if not data.get("access_token"):
        raise err(403, "connection_not_verified", "This connection couldn't be verified. Start it again from the app.")
    cipher = get_cipher()
    await db.execute(delete(OAuthConnection).where(OAuthConnection.user_id == user.id,
                                                   OAuthConnection.platform == platform))
    db.add(OAuthConnection(
        user_id=user.id, platform=platform, access_token_enc=cipher.encrypt(data["access_token"]),
        refresh_token_enc=cipher.encrypt(data["refresh_token"]) if data.get("refresh_token") else None,
        expires_at=datetime.fromisoformat(data["expires_at"]) if data.get("expires_at") else None,
        scope=data.get("scope"), external_account_id=data.get("account_id"), external_username=data.get("username")))
    await db.commit()
    return {"platform": platform, "connected": True, "username": data.get("username")}


@router.delete("/connections/{platform}", status_code=204)
async def disconnect(platform: str, user: UserDep, db: DbDep) -> Response:
    await db.execute(delete(OAuthConnection).where(OAuthConnection.user_id == user.id,
                                                   OAuthConnection.platform == platform))
    await db.commit()
    return Response(status_code=204)
