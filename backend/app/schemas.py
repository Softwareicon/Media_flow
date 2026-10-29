"""API contract (pydantic models). The mobile client's src/api/types.ts mirrors these."""
from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, ConfigDict, EmailStr, Field


class DownloadMode(StrEnum):
    DIRECT = "direct"  # public direct media files
    CONNECTED_ACCOUNT = "connected_account"  # user's own content via OAuth
    OPERATOR_API = "operator_api"  # operator-held API credentials
    LINK_ONLY = "link_only"  # platform does not authorize third-party download
    EXPORT_ONLY = "export_only"  # only the platform's own data export


class AnalysisStatus(StrEnum):
    DOWNLOADABLE = "downloadable"
    LINK_ONLY = "link_only"
    NEEDS_CONNECTION = "needs_connection"
    NOT_CONFIGURED = "not_configured"
    UNAVAILABLE = "unavailable"
    EXPORT_ONLY = "export_only"


class Capabilities(BaseModel):
    official_download: bool  # platform itself offers a download/offline feature
    api_access: bool  # an official API exposes media files to third parties (in some form)
    user_authorized_export: bool  # user can export their own data/media
    direct_media_urls: bool  # links resolve to plain downloadable files


class Alternative(BaseModel):
    label: str
    description: str
    url: str | None = None


class PlatformInfo(BaseModel):
    key: str
    name: str
    domains: list[str]
    capabilities: Capabilities
    download_mode: DownloadMode
    configured: bool  # operator has supplied the credentials this adapter needs
    requires_connection: bool  # user must connect their own account
    connected: bool = False  # this user has connected it
    media_types: list[Literal["video", "image", "audio"]]
    summary: str
    limitations: list[str]
    alternatives: list[Alternative] = []


class MediaOption(BaseModel):
    id: str
    kind: Literal["video", "image", "audio"]
    label: str  # e.g. "1080p · MP4"
    quality_label: str | None = None  # e.g. "1080p", "Original", "1200px"
    width: int | None = None
    height: int | None = None
    bitrate: int | None = None
    mime_type: str
    extension: str
    size_bytes: int | None = None
    size_is_estimate: bool = False
    has_audio: bool | None = None
    is_original: bool = False
    note: str | None = None


class AnalyzeRequest(BaseModel):
    url: str = Field(min_length=4, max_length=4096)


class AnalyzeResponse(BaseModel):
    analysis_id: str | None
    source_url: str
    platform: str
    platform_name: str
    status: AnalysisStatus
    title: str | None = None
    author: str | None = None
    thumbnail_url: str | None = None
    duration_seconds: float | None = None
    media_type: Literal["video", "image", "audio", "gallery", "unknown"] = "unknown"
    options: list[MediaOption] = []
    best_option_id: str | None = None
    explanation: str | None = None
    official_url: str | None = None
    alternatives: list[Alternative] = []
    expires_at: datetime | None = None


class DownloadCreate(BaseModel):
    analysis_id: str = Field(min_length=36, max_length=36)
    option_id: str = Field(min_length=1, max_length=64)


DownloadStatus = Literal["authorized", "in_progress", "completed", "failed", "cancelled"]


class DownloadUpdate(BaseModel):
    status: Literal["in_progress", "completed", "failed"]
    received_bytes: int | None = Field(default=None, ge=0)
    error_code: str | None = Field(default=None, max_length=64, pattern=r"^[a-z0-9_]+$")


class DownloadOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    platform: str
    source_url: str
    title: str | None
    option_id: str
    quality_label: str | None
    mime_type: str
    file_name: str
    expected_bytes: int | None
    received_bytes: int | None
    status: str
    error_code: str | None
    created_at: datetime
    updated_at: datetime
    completed_at: datetime | None


class DownloadTicket(BaseModel):
    """Returned once, on creation: everything the device needs to fetch the file itself."""
    download: DownloadOut
    media_url: str
    request_headers: dict[str, str] = {}
    url_expires_at: datetime | None = None
    max_bytes: int


class DownloadList(BaseModel):
    items: list[DownloadOut]
    next_cursor: str | None = None


class Credentials(BaseModel):
    email: EmailStr
    password: str = Field(min_length=10, max_length=256)


class SessionOut(BaseModel):
    token: str
    user_id: str
    is_anonymous: bool
    email: str | None = None
    expires_at: datetime


class AccountOut(BaseModel):
    user_id: str
    email: str | None
    is_anonymous: bool
    keep_server_history: bool
    connections: list[str]
    created_at: datetime


class AccountSettingsUpdate(BaseModel):
    keep_server_history: bool


class ErrorBody(BaseModel):
    code: str
    message: str
