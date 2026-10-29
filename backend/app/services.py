"""Analysis orchestration and retention clean-up."""
from __future__ import annotations

import asyncio
import logging
from datetime import UTC, datetime, timedelta

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from .config import Settings
from .models import Download, MediaAnalysis, OAuthConnection, OAuthState, Session, User
from .platforms import AdapterContext, AdapterError, AdapterResult, adapter_for
from .platforms.base import best_option
from .schemas import AnalysisStatus, AnalyzeResponse
from .security.crypto import get_cipher
from .security.http_client import SafeHttpClient, UpstreamError
from .security.netguard import parse_and_check_url
from .url_tools import normalize_url

log = logging.getLogger(__name__)


async def connection_token(db: AsyncSession, user: User, platform: str | None) -> str | None:
    if not platform:
        return None
    conn = (await db.execute(select(OAuthConnection).where(
        OAuthConnection.user_id == user.id, OAuthConnection.platform == platform))).scalar_one_or_none()
    if not conn:
        return None
    if conn.expires_at:
        exp = conn.expires_at if conn.expires_at.tzinfo else conn.expires_at.replace(tzinfo=UTC)
        if exp <= datetime.now(UTC):
            return None
    return get_cipher().decrypt(conn.access_token_enc)


async def analyze_url(raw: str, user: User, db: AsyncSession, http: SafeHttpClient, settings: Settings) -> AnalyzeResponse:
    url = normalize_url(raw)  # raises UnsafeURLError (→ 422)
    parse_and_check_url(url, settings.allowed_ports)  # static SSRF checks before anything else runs
    adapter = adapter_for(url)
    token = await connection_token(db, user, adapter.oauth_provider)
    ctx = AdapterContext(http=http, settings=settings, access_token=token)
    try:
        res = await adapter.analyze(url, ctx)  # UnsupportedLink / UnsafeURLError propagate → 422
    except (AdapterError, UpstreamError) as exc:
        log.info("analysis unavailable platform=%s code=%s", adapter.key, getattr(exc, "code", "?"))
        res = AdapterResult(status=AnalysisStatus.UNAVAILABLE, explanation=str(exc),
                            official_url=adapter.official_url(url), alternatives=list(adapter.alternatives))

    analysis_id, expires = None, None
    if res.options and res.status == AnalysisStatus.DOWNLOADABLE:
        expires = datetime.now(UTC) + timedelta(seconds=settings.analysis_ttl_seconds)
        private = {k: {"url": v.url, "headers": v.headers,
                       "expires_at": v.expires_at.isoformat() if v.expires_at else None}
                   for k, v in res.private.items()}
        row = MediaAnalysis(user_id=user.id, source_url=url, platform=adapter.key, status=res.status.value,
                            result={"title": res.title, "options": [o.model_dump() for o in res.options]},
                            private=private, expires_at=expires)
        db.add(row)
        await db.commit()
        analysis_id = row.id
    return AnalyzeResponse(
        analysis_id=analysis_id, source_url=url, platform=adapter.key, platform_name=adapter.name,
        status=res.status, title=res.title, author=res.author, thumbnail_url=res.thumbnail_url,
        duration_seconds=res.duration_seconds, media_type=res.media_type,  # type: ignore[arg-type]
        options=res.options, best_option_id=best_option(res.options), explanation=res.explanation,
        official_url=res.official_url, alternatives=res.alternatives, expires_at=expires,
    )


async def purge_expired(db: AsyncSession, settings: Settings) -> None:
    now = datetime.now(UTC)
    await db.execute(delete(MediaAnalysis).where(MediaAnalysis.expires_at < now))
    await db.execute(delete(OAuthState).where(OAuthState.expires_at < now))
    await db.execute(delete(Session).where(Session.expires_at < now))
    cutoff = now - timedelta(days=settings.download_record_retention_days)
    await db.execute(delete(Download).where(Download.created_at < cutoff))
    await db.commit()


async def retention_loop(sessionmaker, settings: Settings, every_seconds: int = 600) -> None:
    while True:
        try:
            async with sessionmaker() as db:
                await purge_expired(db, settings)
        except Exception:  # keep the loop alive; log and retry next cycle
            log.exception("retention purge failed")
        await asyncio.sleep(every_seconds)
