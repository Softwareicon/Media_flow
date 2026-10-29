from __future__ import annotations

import re
from urllib.parse import urlsplit

from ..schemas import AnalysisStatus, Alternative, Capabilities, DownloadMode, MediaOption
from ..security import mime
from ..security.http_client import host_matches
from .base import (AdapterContext, AdapterResult, PlatformAdapter, PrivateOption, UnsupportedLink, label_for,
                   probe_media)

PIN_HOSTS = ("pinterest.com", "pinterest.co.uk", "pinterest.ca", "pinterest.de", "pinterest.fr", "pinterest.es",
             "pinterest.it", "pinterest.com.au", "pinterest.co.kr", "pinterest.jp", "pinterest.ph", "pinterest.nz",
             "pinterest.at", "pinterest.ch", "pinterest.cl", "pinterest.com.mx", "pinterest.pt", "pinterest.se",
             "pinterest.dk", "pinterest.ie", "pinterest.co.in", "pin.it")
_PIN = re.compile(r"/pin/(\d{5,25})")


class PinterestAdapter(PlatformAdapter):
    key = "pinterest"
    name = "Pinterest"
    domains = PIN_HOSTS
    download_mode = DownloadMode.CONNECTED_ACCOUNT
    capabilities = Capabilities(official_download=False, api_access=True, user_authorized_export=True,
                                direct_media_urls=False)
    media_types = ["image"]
    requires_connection = True
    oauth_provider = "pinterest"
    summary = "Save images from your own Pins in the largest size Pinterest's API provides (1200px wide)."
    limitations = [
        "Pinterest API v5 serves image renditions up to 1200px wide — not the original upload.",
        "Video Pins: the API does not expose video files.",
        "Only Pins the connected account can read through the API.",
    ]
    alternatives = [
        Alternative(label="Request your Pinterest data",
                    description="Pinterest → Settings → Privacy and data → Request your data."),
    ]

    def is_configured(self, settings) -> bool:
        return bool(settings.pinterest_app_id and settings.pinterest_app_secret)

    async def _pin_id(self, url: str, ctx: AdapterContext) -> str:
        m = _PIN.search(urlsplit(url).path)
        if m:
            return m.group(1)
        if host_matches(urlsplit(url).hostname or "", ("pin.it",)):
            resp = await ctx.http.request("HEAD", url, allowed_hosts=PIN_HOSTS)
            m = _PIN.search(urlsplit(resp.url).path)
            if m:
                return m.group(1)
        raise UnsupportedLink("Paste a link to a single Pin (…/pin/<id>).")

    async def analyze(self, url: str, ctx: AdapterContext) -> AdapterResult:
        if not self.is_configured(ctx.settings):
            return self.link_only(url, "Pinterest downloads aren't set up on this server. Open the Pin in Pinterest.",
                                  status=AnalysisStatus.NOT_CONFIGURED)
        pin_id = await self._pin_id(url, ctx)
        official = f"https://www.pinterest.com/pin/{pin_id}/"
        if not ctx.access_token:
            r = self.link_only(url, "Connect your Pinterest account to save images from your Pins.",
                               status=AnalysisStatus.NEEDS_CONNECTION)
            r.official_url = official
            return r
        data = await ctx.http.get_json(f"https://api.pinterest.com/v5/pins/{pin_id}", allowed_hosts=("api.pinterest.com",),
                                       headers={"Authorization": f"Bearer {ctx.access_token}"})
        media = data.get("media") or {}
        mtype = media.get("media_type") or ""
        result = AdapterResult(status=AnalysisStatus.DOWNLOADABLE, title=data.get("title") or data.get("description"),
                               official_url=official, alternatives=list(self.alternatives))
        if mtype.startswith("video") or mtype == "multiple_videos":
            result.status = AnalysisStatus.LINK_ONLY
            result.media_type = "video"
            result.thumbnail_url = media.get("cover_image_url")
            result.explanation = "Pinterest's API doesn't provide video files. Open the Pin in Pinterest."
            return result
        image_sets = [media.get("images") or {}] if mtype == "image" else [
            (item.get("images") or {}) for item in (media.get("items") or [])]
        for i, images in enumerate(image_sets):
            if not images:
                continue
            biggest = max(images.values(), key=lambda v: (v.get("width") or 0) * (v.get("height") or 0))
            src = biggest.get("url")
            if not src:
                continue
            size, sniffed = await probe_media(ctx, src, ("pinimg.com",))
            mt = sniffed or "image/jpeg"
            w = biggest.get("width")
            q = f"{w}px" if w else "Largest available"
            result.add(MediaOption(
                id=f"i{i}", kind="image", label=label_for("image", q, mime.extension_for(mt)), quality_label=q,
                width=w, height=biggest.get("height"), mime_type=mt, extension=mime.extension_for(mt),
                size_bytes=size, note="Largest size Pinterest's API provides; not the original upload."),
                PrivateOption(src))
            result.thumbnail_url = result.thumbnail_url or src
        result.media_type = "gallery" if len(result.options) > 1 else "image"
        if not result.options:
            result.status = AnalysisStatus.UNAVAILABLE
            result.explanation = "This Pin has no images the API can provide."
        return result
