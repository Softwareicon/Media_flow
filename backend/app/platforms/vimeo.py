from __future__ import annotations

import re
from datetime import datetime
from urllib.parse import parse_qs, urlsplit

from ..schemas import AnalysisStatus, Alternative, Capabilities, DownloadMode, MediaOption
from ..security import mime
from .base import (AdapterContext, AdapterResult, PlatformAdapter, PrivateOption, UnsupportedLink, fetch_oembed,
                   label_for, quality_from_height)

_PATH = re.compile(r"^/(?:video/)?(\d{3,12})(?:/([0-9a-f]{6,20}))?/?$")
_ANY_ID = re.compile(r"/(\d{3,12})(?:/([0-9a-f]{6,20}))?(?:/|$)")


def video_ref(url: str) -> tuple[str, str | None]:
    p = urlsplit(url)
    m = _PATH.match(p.path) or _ANY_ID.search(p.path)
    if not m:
        raise UnsupportedLink("Paste a link to a single Vimeo video.")
    h = m.group(2) or (parse_qs(p.query).get("h") or [None])[0]
    return m.group(1), h


class VimeoAdapter(PlatformAdapter):
    key = "vimeo"
    name = "Vimeo"
    domains = ("vimeo.com",)
    download_mode = DownloadMode.CONNECTED_ACCOUNT
    capabilities = Capabilities(official_download=True, api_access=True, user_authorized_export=True,
                                direct_media_urls=False)
    media_types = ["video"]
    requires_connection = True
    oauth_provider = "vimeo"
    summary = "Download your own Vimeo videos in every rendition Vimeo stores, after connecting your account."
    limitations = [
        "Only videos owned by the connected Vimeo account.",
        "Vimeo exposes download files only on Standard plans or above.",
        "Download links expire after 24 hours; re-analyze if a download is started later.",
    ]
    alternatives = [
        Alternative(label="Download button on Vimeo",
                    description="If the owner enabled downloads, use the Download button under the video on vimeo.com."),
    ]

    def is_configured(self, settings) -> bool:
        return bool(settings.vimeo_client_id and settings.vimeo_client_secret)

    def official_url(self, url: str) -> str:
        try:
            vid, h = video_ref(url)
        except UnsupportedLink:
            return url
        return f"https://vimeo.com/{vid}/{h}" if h else f"https://vimeo.com/{vid}"

    async def analyze(self, url: str, ctx: AdapterContext) -> AdapterResult:
        vid, h = video_ref(url)
        if not ctx.access_token:
            meta = await fetch_oembed(ctx, "https://vimeo.com/api/oembed.json", self.official_url(url), ("vimeo.com",))
            if not self.is_configured(ctx.settings):
                return self.link_only(url, "Vimeo downloads aren't set up on this server. Open the video on Vimeo.",
                                      meta, "video", AnalysisStatus.NOT_CONFIGURED)
            r = self.link_only(url, "Connect your Vimeo account to download videos you own. Vimeo doesn't give "
                                    "files for other people's videos to apps.", meta, "video",
                               AnalysisStatus.NEEDS_CONNECTION)
            r.duration_seconds = meta.get("duration")
            return r

        ref = f"{vid}:{h}" if h else vid
        data = await ctx.http.get_json(
            f"https://api.vimeo.com/videos/{ref}?fields=name,duration,user.name,pictures.sizes,download",
            allowed_hosts=("api.vimeo.com",),
            headers={"Authorization": f"bearer {ctx.access_token}", "Accept": "application/vnd.vimeo.*+json;version=3.4"},
        )
        sizes = (data.get("pictures") or {}).get("sizes") or []
        thumb = max(sizes, key=lambda s: s.get("width", 0)).get("link") if sizes else None
        result = AdapterResult(
            status=AnalysisStatus.DOWNLOADABLE, title=data.get("name"), author=(data.get("user") or {}).get("name"),
            thumbnail_url=thumb, duration_seconds=data.get("duration"), media_type="video",
            official_url=self.official_url(url), alternatives=list(self.alternatives),
        )
        for i, d in enumerate(data.get("download") or []):
            link, mt = d.get("link"), (d.get("type") or "video/mp4").lower()
            if not link or not mt.startswith("video/"):
                continue
            is_source = d.get("quality") == "source"
            q = "Original" if is_source else (d.get("rendition") or quality_from_height(d.get("height")))
            ext = mime.extension_for(mt) if mt in mime.SUPPORTED else "mp4"
            exp = d.get("expires")
            result.add(MediaOption(
                id=f"d{i}", kind="video", label=label_for("video", q, ext), quality_label=q,
                width=d.get("width"), height=d.get("height"), mime_type=mt, extension=ext,
                size_bytes=d.get("size"), has_audio=True, is_original=is_source,
                note="Your original upload" if is_source else None),
                PrivateOption(link, expires_at=datetime.fromisoformat(exp) if exp else None))
        if not result.options:
            result.status = AnalysisStatus.LINK_ONLY
            result.explanation = ("Vimeo didn't return any download files. It only does so for videos you own, on a "
                                  "Standard plan or above.")
        return result
