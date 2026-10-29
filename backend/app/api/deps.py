from __future__ import annotations

from datetime import UTC, datetime
from typing import Annotated

from fastapi import Depends, Header, HTTPException, Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..config import Settings, get_settings
from ..db import get_session
from ..models import Session as DbSession
from ..models import User
from ..security.crypto import token_digest
from ..security.http_client import SafeHttpClient

SettingsDep = Annotated[Settings, Depends(get_settings)]
DbDep = Annotated[AsyncSession, Depends(get_session)]


def get_http(request: Request) -> SafeHttpClient:
    return request.app.state.http


HttpDep = Annotated[SafeHttpClient, Depends(get_http)]


def err(status: int, code: str, message: str) -> HTTPException:
    return HTTPException(status_code=status, detail={"code": code, "message": message})


async def _resolve(db: AsyncSession, authorization: str | None) -> tuple[User, DbSession] | None:
    if not authorization or not authorization.lower().startswith("bearer "):
        return None
    token = authorization[7:].strip()
    if not token or len(token) > 128:
        return None
    sess = (await db.execute(select(DbSession).where(DbSession.token_hash == token_digest(token)))).scalar_one_or_none()
    now = datetime.now(UTC)
    if not sess or _aware(sess.expires_at) <= now:
        return None
    user = await db.get(User, sess.user_id)
    if not user:
        return None
    sess.last_used_at = now
    return user, sess


def _aware(dt: datetime) -> datetime:
    return dt if dt.tzinfo else dt.replace(tzinfo=UTC)  # SQLite returns naive datetimes


async def current_session(db: DbDep, authorization: Annotated[str | None, Header()] = None) -> tuple[User, DbSession]:
    found = await _resolve(db, authorization)
    if not found:
        raise HTTPException(status_code=401, detail={"code": "unauthorized", "message": "Sign-in required."},
                            headers={"WWW-Authenticate": "Bearer"})
    return found


async def current_user(found: Annotated[tuple[User, DbSession], Depends(current_session)]) -> User:
    return found[0]


async def optional_user(db: DbDep, authorization: Annotated[str | None, Header()] = None) -> User | None:
    found = await _resolve(db, authorization)
    return found[0] if found else None


UserDep = Annotated[User, Depends(current_user)]
OptionalUserDep = Annotated[User | None, Depends(optional_user)]
