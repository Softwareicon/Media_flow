"""Download records. The server AUTHORIZES a download and hands the device a URL; the device
transfers the bytes itself, so media never touches the server."""
from __future__ import annotations

from datetime import UTC, datetime
from typing import Annotated

from fastapi import APIRouter, Query, Request, Response
from sqlalchemy import and_, or_, select

from ..models import Download, MediaAnalysis
from ..schemas import DownloadCreate, DownloadList, DownloadOut, DownloadTicket, DownloadUpdate
from ..security import ratelimit
from ..security.filenames import safe_filename
from .deps import DbDep, SettingsDep, UserDep, err

router = APIRouter(tags=["downloads"])
TERMINAL = {"completed", "failed", "cancelled"}


def _aware(dt: datetime | None) -> datetime | None:
    return dt if dt is None or dt.tzinfo else dt.replace(tzinfo=UTC)


async def _owned(db, user, download_id: str) -> Download:
    row = await db.get(Download, download_id)
    if not row or row.user_id != user.id:
        raise err(404, "not_found", "Download not found.")
    return row


@router.post("/downloads", response_model=DownloadTicket, status_code=201)
async def create_download(body: DownloadCreate, request: Request, user: UserDep, db: DbDep,
                          settings: SettingsDep) -> DownloadTicket:
    ratelimit.enforce(request, "downloads", user.id, settings.rate_limit_per_minute)
    analysis = await db.get(MediaAnalysis, body.analysis_id)
    if not analysis or analysis.user_id != user.id:
        raise err(404, "analysis_not_found", "That analysis doesn't exist. Analyze the link again.")
    if _aware(analysis.expires_at) <= datetime.now(UTC):
        raise err(410, "analysis_expired", "This link's analysis has expired. Analyze it again for fresh options.")
    option = next((o for o in analysis.result.get("options", []) if o["id"] == body.option_id), None)
    private = analysis.private.get(body.option_id)
    if not option or not private:
        raise err(404, "option_not_found", "That quality option isn't available for this media.")
    url_exp = datetime.fromisoformat(private["expires_at"]) if private.get("expires_at") else None
    if url_exp and _aware(url_exp) <= datetime.now(UTC):
        raise err(410, "media_link_expired", "The platform's download link has expired. Analyze the link again.")
    if option.get("size_bytes") and option["size_bytes"] > settings.max_media_bytes:
        raise err(413, "too_large", "This file is larger than the app's download limit.")

    row = Download(
        user_id=user.id, analysis_id=analysis.id, platform=analysis.platform, source_url=analysis.source_url,
        title=analysis.result.get("title"), option_id=option["id"], quality_label=option.get("quality_label"),
        mime_type=option["mime_type"],
        file_name=safe_filename(analysis.result.get("title"), option["extension"], fallback=analysis.platform),
        expected_bytes=option.get("size_bytes"), status="authorized",
    )
    db.add(row)
    await db.commit()
    await db.refresh(row)
    return DownloadTicket(download=DownloadOut.model_validate(row), media_url=private["url"],
                          request_headers=private.get("headers") or {}, url_expires_at=url_exp,
                          max_bytes=settings.max_media_bytes)


@router.get("/downloads", response_model=DownloadList)
async def list_downloads(
    user: UserDep, db: DbDep,
    status: Annotated[str | None, Query(pattern="^(authorized|in_progress|completed|failed|cancelled)$")] = None,
    platform: Annotated[str | None, Query(max_length=32)] = None,
    q: Annotated[str | None, Query(max_length=100)] = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 30,
    cursor: Annotated[str | None, Query(max_length=80)] = None,
) -> DownloadList:
    stmt = select(Download).where(Download.user_id == user.id)
    if status:
        stmt = stmt.where(Download.status == status)
    if platform:
        stmt = stmt.where(Download.platform == platform)
    if q:
        escaped = q.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
        like = f"%{escaped}%"
        stmt = stmt.where(or_(Download.title.ilike(like, escape="\\"), Download.file_name.ilike(like, escape="\\")))
    if cursor:
        try:
            ts, cid = cursor.split("|", 1)
            cts = datetime.fromisoformat(ts)
        except ValueError:
            raise err(422, "bad_cursor", "Invalid cursor.") from None
        stmt = stmt.where(or_(Download.created_at < cts, and_(Download.created_at == cts, Download.id < cid)))
    rows = (await db.execute(stmt.order_by(Download.created_at.desc(), Download.id.desc()).limit(limit + 1))).scalars().all()
    nxt = None
    if len(rows) > limit:
        last = rows[limit - 1]
        nxt = f"{last.created_at.isoformat()}|{last.id}"
        rows = rows[:limit]
    return DownloadList(items=[DownloadOut.model_validate(r) for r in rows], next_cursor=nxt)


@router.get("/downloads/{download_id}", response_model=DownloadOut)
async def get_download(download_id: str, user: UserDep, db: DbDep) -> Download:
    return await _owned(db, user, download_id)


@router.patch("/downloads/{download_id}", response_model=DownloadOut)
async def update_download(download_id: str, body: DownloadUpdate, user: UserDep, db: DbDep) -> DownloadOut:
    """Device reports progress / outcome. Records are deleted on completion if the user turned off history."""
    row = await _owned(db, user, download_id)
    if row.status in TERMINAL:
        raise err(409, "already_finished", f"This download is already {row.status}.")
    row.status = body.status
    if body.received_bytes is not None:
        row.received_bytes = body.received_bytes
    if body.status == "failed":
        row.error_code = body.error_code or "unknown"
    if body.status == "completed":
        row.completed_at = datetime.now(UTC)
    out = DownloadOut.model_validate(row)
    if body.status in TERMINAL and not user.keep_server_history:
        await db.delete(row)
    await db.commit()
    return out


@router.post("/downloads/{download_id}/cancel", response_model=DownloadOut)
async def cancel_download(download_id: str, user: UserDep, db: DbDep) -> DownloadOut:
    row = await _owned(db, user, download_id)
    if row.status in TERMINAL:
        raise err(409, "already_finished", f"This download is already {row.status}.")
    row.status = "cancelled"
    out = DownloadOut.model_validate(row)
    if not user.keep_server_history:
        await db.delete(row)
    await db.commit()
    return out


@router.delete("/downloads/{download_id}", status_code=204)
async def delete_download(download_id: str, user: UserDep, db: DbDep) -> Response:
    row = await _owned(db, user, download_id)
    await db.delete(row)
    await db.commit()
    return Response(status_code=204)
