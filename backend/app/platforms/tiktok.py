from __future__ import annotations

import re
from urllib.parse import urlsplit

from ..schemas import Alternative, Capabilities, DownloadMode
from .base import AdapterContext, AdapterResult, PlatformAdapter, UnsupportedLink, fetch_oembed

_VIDEO = re.compile(r"/@[^/]+/(video|photo)/(\d+)")


class TikTokAdapter(PlatformAdapter):
    key = "tiktok"
    name = "TikTok"
    domains = ("tiktok.com",)
    download_mode = DownloadMode.LINK_ONLY
    capabilities = Capabilities(official_download=True, api_access=False, user_authorized_export=True,
                                direct_media_urls=False)
    media_types = ["video", "image"]
    summary = "Preview only. TikTok's developer APIs return share and embed links, not video files."
    limitations = [
        "The TikTok Display API returns share_url and embed_link only — no downloadable file.",
        "Cover images from the API expire after 6 hours.",
    ]
    alternatives = [
        Alternative(label="Save in the TikTok app",
                    description="If the creator allows it, tap Share → Save video inside TikTok."),
        Alternative(label="Your own videos: data export",
                    description="TikTok → Settings and privacy → Account → Download your data."),
    ]

    async def analyze(self, url: str, ctx: AdapterContext) -> AdapterResult:
        p = urlsplit(url)
        host = (p.hostname or "").lower()
        is_short = host.startswith(("vm.", "vt.")) or p.path.startswith("/t/")
        m = _VIDEO.search(p.path)
        if not m and not is_short:
            raise UnsupportedLink("Paste a link to a single TikTok video or photo post.")
        meta = await fetch_oembed(ctx, "https://www.tiktok.com/oembed", url, ("tiktok.com",))
        return self.link_only(
            url,
            "TikTok doesn't provide downloadable files to other apps. Open it in TikTok and use Save video if the "
            "creator allows downloads.",
            meta, media_type="image" if m and m.group(1) == "photo" else "video",
        )
