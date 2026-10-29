"""Adapter interface every platform implements, plus shared helpers."""
from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from urllib.parse import urlencode, urlsplit

from ..config import Settings
from ..schemas import Alternative, AnalysisStatus, Capabilities, DownloadMode, MediaOption, PlatformInfo
from ..security import mime
from ..security.http_client import SafeHttpClient, UpstreamError, host_matches
from ..security.netguard import UnsafeURLError

log = logging.getLogger(__name__)


class AdapterError(Exception):
    """Platform-level failure reported to the user as an `unavailable` analysis."""

    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code


class UnsupportedLink(Exception):
    """The URL belongs to the platform but isn't a single media item (e.g. a profile page)."""


@dataclass
class AdapterContext:
    http: SafeHttpClient
    settings: Settings
    access_token: str | None = None  # this user's OAuth token for the platform, if connected
    external_account_id: str | None = None


@dataclass
class PrivateOption:
    url: str
    headers: dict[str, str] = field(default_factory=dict)
    expires_at: datetime | None = None


@dataclass
class AdapterResult:
    status: AnalysisStatus
    title: str | None = None
    author: str | None = None
    thumbnail_url: str | None = None
    duration_seconds: float | None = None
    media_type: str = "unknown"
    options: list[MediaOption] = field(default_factory=list)
    private: dict[str, PrivateOption] = field(default_factory=dict)
    explanation: str | None = None
    official_url: str | None = None
    alternatives: list[Alternative] = field(default_factory=list)

    def add(self, option: MediaOption, private: PrivateOption) -> None:
        self.options.append(option)
        self.private[option.id] = private


class PlatformAdapter(ABC):
    key: str
    name: str
    domains: tuple[str, ...]
    download_mode: DownloadMode
    capabilities: Capabilities
    media_types: list = ["video", "image"]
    summary: str = ""
    limitations: list[str] = []
    alternatives: list[Alternative] = []
    requires_connection: bool = False
    oauth_provider: str | None = None  # key in app.oauth.PROVIDERS

    def matches(self, host: str) -> bool:
        return host_matches(host, self.domains)

    def is_configured(self, settings: Settings) -> bool:
        return True

    def info(self, settings: Settings, connected: bool = False) -> PlatformInfo:
        return PlatformInfo(
            key=self.key, name=self.name, domains=list(self.domains), capabilities=self.capabilities,
            download_mode=self.download_mode, configured=self.is_configured(settings),
            requires_connection=self.requires_connection, connected=connected, media_types=self.media_types,
            summary=self.summary, limitations=self.limitations, alternatives=self.alternatives,
        )

    def official_url(self, url: str) -> str:
        return url

    @abstractmethod
    async def analyze(self, url: str, ctx: AdapterContext) -> AdapterResult: ...

    # ---- shared helpers -------------------------------------------------------------
    def link_only(self, url: str, explanation: str, meta: dict | None = None, media_type: str = "unknown",
                  status: AnalysisStatus = AnalysisStatus.LINK_ONLY) -> AdapterResult:
        meta = meta or {}
        return AdapterResult(
            status=status, title=meta.get("title"), author=meta.get("author_name"),
            thumbnail_url=meta.get("thumbnail_url"), media_type=media_type, explanation=explanation,
            official_url=self.official_url(url), alternatives=list(self.alternatives),
        )


async def fetch_oembed(ctx: AdapterContext, endpoint: str, url: str, allowed: tuple[str, ...],
                       extra: dict | None = None) -> dict:
    """Public oEmbed metadata. Failure is non-fatal: returns {}."""
    try:
        data = await ctx.http.get_json(f"{endpoint}?{urlencode({'url': url, 'format': 'json', **(extra or {})})}",
                                       allowed_hosts=allowed, max_bytes=256 * 1024)
        if not isinstance(data, dict):
            return {}
        thumb = data.get("thumbnail_url")
        if thumb and not str(thumb).startswith("https://"):
            data["thumbnail_url"] = None
        return {k: data.get(k) for k in ("title", "author_name", "thumbnail_url", "type", "duration")}
    except (UpstreamError, UnsafeURLError) as exc:
        log.info("oembed failed for %s: %s", endpoint, exc)
        return {}


async def probe_media(ctx: AdapterContext, url: str, allowed: tuple[str, ...] | None,
                      headers: dict[str, str] | None = None) -> tuple[int | None, str | None]:
    """(total size, sniffed MIME). Non-fatal: (None, None) when the CDN won't say."""
    try:
        resp = await ctx.http.probe(url, allowed_hosts=allowed, headers=headers)
    except (UpstreamError, UnsafeURLError) as exc:
        log.info("probe failed for %s: %s", urlsplit(url).hostname, exc)
        return None, None
    if resp.status not in (200, 206):
        return None, None
    return resp.content_length, mime.sniff(resp.body)


def label_for(kind: str, quality: str | None, ext: str) -> str:
    return f"{quality} · {ext.upper()}" if quality else f"{kind.capitalize()} · {ext.upper()}"


def quality_from_height(h: int | None) -> str | None:
    if not h:
        return None
    for std in (4320, 2160, 1440, 1080, 720, 480, 360, 240, 144):
        if h >= std * 0.93:
            return "4K" if std == 2160 else ("8K" if std == 4320 else f"{std}p")
    return f"{h}p"


def best_option(options: list[MediaOption]) -> str | None:
    if not options:
        return None
    ranked = sorted(options, key=lambda o: (o.kind == "video", o.is_original, (o.width or 0) * (o.height or 0),
                                             o.bitrate or 0, o.size_bytes or 0), reverse=True)
    return ranked[0].id
