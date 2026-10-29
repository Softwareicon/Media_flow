"""Optional accounts. Every app install starts as an anonymous principal; registering upgrades it in place."""
from __future__ import annotations

from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, Depends, Request, Response
from sqlalchemy import delete, select
from sqlalchemy.exc import IntegrityError

from ..models import Download, MediaAnalysis, OAuthConnection, Session, User
from ..schemas import AccountOut, AccountSettingsUpdate, Credentials, SessionOut
from ..security import ratelimit
from ..security.crypto import hash_password, new_token, token_digest, verify_password
from .deps import DbDep, SettingsDep, UserDep, current_session, err

router = APIRouter(tags=["auth & account"])


async def _issue(db, user: User, ttl_days: int) -> SessionOut:
    token = new_token()
    exp = datetime.now(UTC) + timedelta(days=ttl_days)
    db.add(Session(user_id=user.id, token_hash=token_digest(token), expires_at=exp))
    await db.commit()
    return SessionOut(token=token, user_id=user.id, is_anonymous=user.is_anonymous, email=user.email, expires_at=exp)


@router.post("/auth/anonymous", response_model=SessionOut, status_code=201)
async def anonymous(request: Request, db: DbDep, settings: SettingsDep) -> SessionOut:
    """Create an anonymous principal for this install. No personal data is collected."""
    ratelimit.enforce(request, "auth", None, settings.rate_limit_auth_per_minute)
    user = User(is_anonymous=True)
    db.add(user)
    await db.flush()
    return await _issue(db, user, settings.session_ttl_days)


@router.post("/auth/register", response_model=SessionOut, status_code=201)
async def register(body: Credentials, request: Request, user: UserDep, db: DbDep, settings: SettingsDep) -> SessionOut:
    """Attach email + password to the current anonymous principal (keeps its history and connections)."""
    ratelimit.enforce(request, "auth", user.id, settings.rate_limit_auth_per_minute)
    if not user.is_anonymous:
        raise err(409, "already_registered", "This account already has an email address.")
    user.email = body.email.lower()
    user.password_hash = hash_password(body.password)
    user.is_anonymous = False
    try:
        await db.flush()
    except IntegrityError:
        await db.rollback()
        raise err(409, "email_taken", "An account with this email already exists. Sign in instead.") from None
    await db.execute(delete(Session).where(Session.user_id == user.id))  # rotate sessions on privilege change
    return await _issue(db, user, settings.session_ttl_days)


@router.post("/auth/login", response_model=SessionOut)
async def login(body: Credentials, request: Request, db: DbDep, settings: SettingsDep) -> SessionOut:
    ratelimit.enforce(request, "login", body.email.lower(), settings.rate_limit_auth_per_minute)
    user = (await db.execute(select(User).where(User.email == body.email.lower()))).scalar_one_or_none()
    if not verify_password(user.password_hash if user else None, body.password) or not user:
        raise err(401, "invalid_credentials", "Email or password is incorrect.")
    return await _issue(db, user, settings.session_ttl_days)


@router.post("/auth/logout", status_code=204)
async def logout(db: DbDep, found=Depends(current_session)) -> Response:
    await db.delete(found[1])
    await db.commit()
    return Response(status_code=204)


@router.get("/account", response_model=AccountOut)
async def account(user: UserDep, db: DbDep) -> AccountOut:
    conns = (await db.execute(select(OAuthConnection.platform).where(OAuthConnection.user_id == user.id))).scalars().all()
    return AccountOut(user_id=user.id, email=user.email, is_anonymous=user.is_anonymous,
                      keep_server_history=user.keep_server_history, connections=sorted(conns),
                      created_at=user.created_at)


@router.patch("/account/settings", response_model=AccountOut)
async def update_settings(body: AccountSettingsUpdate, user: UserDep, db: DbDep) -> AccountOut:
    user.keep_server_history = body.keep_server_history
    if not body.keep_server_history:
        await db.execute(delete(Download).where(Download.user_id == user.id,
                                                Download.status.in_(("completed", "failed", "cancelled"))))
    await db.commit()
    return await account(user, db)


@router.delete("/account/history", status_code=204)
async def delete_history(user: UserDep, db: DbDep) -> Response:
    """Delete every download record and cached analysis for this account."""
    await db.execute(delete(Download).where(Download.user_id == user.id))
    await db.execute(delete(MediaAnalysis).where(MediaAnalysis.user_id == user.id))
    await db.commit()
    return Response(status_code=204)


@router.delete("/account", status_code=204)
async def delete_account(user: UserDep, db: DbDep) -> Response:
    """Permanently delete the account and all server-side data (sessions, connections, history)."""
    for model in (Download, MediaAnalysis, OAuthConnection, Session):
        await db.execute(delete(model).where(model.user_id == user.id))
    await db.delete(user)
    await db.commit()
    return Response(status_code=204)
