from __future__ import annotations

from fastapi import APIRouter, Request
from sqlalchemy import select

from ..models import OAuthConnection
from ..platforms import ADAPTERS
from ..schemas import AnalyzeRequest, AnalyzeResponse, PlatformInfo
from ..security import ratelimit
from ..services import analyze_url
from .deps import DbDep, HttpDep, OptionalUserDep, SettingsDep, UserDep

router = APIRouter(tags=["media"])


@router.post("/media/analyze", response_model=AnalyzeResponse)
async def analyze(body: AnalyzeRequest, request: Request, user: UserDep, db: DbDep, http: HttpDep,
                  settings: SettingsDep) -> AnalyzeResponse:
    """Identify the platform and return ONLY the media options that platform authorizes.

    `status` tells the client what to show: `downloadable` (pick an option), `link_only`
    (open officially), `needs_connection` (connect account), `not_configured`, `export_only`,
    or `unavailable` (with `explanation`). Invalid or unsafe links return 422.
    """
    ratelimit.enforce(request, "analyze", user.id, settings.rate_limit_per_minute)
    return await analyze_url(body.url, user, db, http, settings)


@router.get("/platforms", response_model=list[PlatformInfo])
async def platforms(user: OptionalUserDep, db: DbDep, settings: SettingsDep) -> list[PlatformInfo]:
    """The capability registry. `configured=false` means the operator hasn't supplied credentials."""
    connected: set[str] = set()
    if user:
        connected = set((await db.execute(select(OAuthConnection.platform)
                                          .where(OAuthConnection.user_id == user.id))).scalars().all())
    return [a.info(settings, connected=(a.oauth_provider in connected)) for a in ADAPTERS]
