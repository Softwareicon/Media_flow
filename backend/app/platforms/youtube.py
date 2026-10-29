from __future__ import annotations

import re
from urllib.parse import parse_qs, urlsplit

from ..schemas import Alternative, Capabilities, DownloadMode
from ..security.http_client import UpstreamError
from .base import AdapterContext, AdapterResult, PlatformAdapter, UnsupportedLink, fetch_oembed

_ID = re.compile(r"^[A-Za-z0-9_-]{11}$")
_ISO_DUR = re.compile(r"^P(?:(\d+)D)?T?(?:(\d+)H)?(?:(\d+)M)?(?:(\d+)S)?$")


def video_id(url: str) -> tuple[str, bool]:
    p = urlsplit(url)
    host = (p.hostname or "").lower()
    segs = [s for s in p.path.split("/") if s]
    vid, short = None, False
    if host.endswith("youtu.be") and segs:
        vid = segs[0]
    elif segs[:1] == ["watch"] or p.path in ("/watch", "/watch/"):
        vid = (parse_qs(p.query).get("v") or [None])[0]
    elif len(segs) >= 2 and segs[0] in ("shorts", "live", "embed", "v", "e"):
        vid, short = segs[1], segs[0] == "shorts"
    if not vid or not _ID.match(vid):
        raise UnsupportedLink("Paste a link to a single YouTube video (watch, youtu.be or Shorts link).")
    return vid, short


def iso_duration(value: str) -> float | None:
    m = _ISO_DUR.match(value or "")
    if not m:
        return None
    d, h, mi, s = (int(x or 0) for x in m.groups())
    return float(d * 86400 + h * 3600 + mi * 60 + s)


class YouTubeAdapter(PlatformAdapter):
    key = "youtube"
    name = "YouTube"
    domains = ("youtube.com", "youtu.be", "youtube-nocookie.com")
    download_mode = DownloadMode.LINK_ONLY
    capabilities = Capabilities(official_download=True, api_access=False, user_authorized_export=True,
                                direct_media_urls=False)
    media_types = ["video"]
    summary = "Preview only. YouTube's Terms of Service do not allow third-party apps to download videos."
    limitations = [
        "YouTube's Terms forbid downloading unless YouTube itself shows a download button.",
        "The YouTube Data API provides metadata only, never video files.",
    ]
    alternatives = [
        Alternative(label="Save offline in the YouTube app",
                    description="YouTube Premium members can download videos for offline viewing inside the YouTube app."),
        Alternative(label="Your own uploads: YouTube Studio",
                    description="Creators can download their own uploaded videos from YouTube Studio → Content → ⋮ → Download.",
                    url="https://studio.youtube.com"),
        Alternative(label="Your account data: Google Takeout",
                    description="Export your own YouTube uploads and data.", url="https://takeout.google.com"),
    ]

    def official_url(self, url: str) -> str:
        try:
            vid, short = video_id(url)
        except UnsupportedLink:
            return url
        return f"https://www.youtube.com/shorts/{vid}" if short else f"https://www.youtube.com/watch?v={vid}"

    async def analyze(self, url: str, ctx: AdapterContext) -> AdapterResult:
        vid, _ = video_id(url)
        canonical = self.official_url(url)
        meta = await fetch_oembed(ctx, "https://www.youtube.com/oembed", canonical, ("youtube.com",))
        result = self.link_only(
            url,
            "YouTube doesn't allow other apps to download its videos. Open it in YouTube, or use one of the "
            "official options below.",
            meta, media_type="video",
        )
        key = ctx.settings.youtube_api_key
        if key:
            try:
                data = await ctx.http.get_json(
                    f"https://www.googleapis.com/youtube/v3/videos?part=contentDetails&id={vid}&key={key.get_secret_value()}",
                    allowed_hosts=("googleapis.com",))
                items = data.get("items") or []
                if items:
                    result.duration_seconds = iso_duration(items[0].get("contentDetails", {}).get("duration", ""))
            except UpstreamError:
                pass
        return result
