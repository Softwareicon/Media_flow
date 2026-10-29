from __future__ import annotations

import re
from urllib.parse import urlsplit

from ..schemas import AnalysisStatus, Alternative, Capabilities, DownloadMode, MediaOption
from ..security import mime
from .base import (AdapterContext, AdapterError, AdapterResult, PlatformAdapter, PrivateOption, UnsupportedLink,
                   fetch_oembed, label_for, probe_media, quality_from_height)

_STATUS = re.compile(r"/status(?:es)?/(\d{5,25})")
_DIMS = re.compile(r"/(\d{2,5})x(\d{2,5})/")
CDN = ("twimg.com",)


def tweet_id(url: str) -> str:
    m = _STATUS.search(urlsplit(url).path)
    if not m:
        raise UnsupportedLink("Paste a link to a single post (…/status/<id>).")
    return m.group(1)


class XAdapter(PlatformAdapter):
    key = "x"
    name = "X (Twitter)"
    domains = ("x.com", "twitter.com")
    download_mode = DownloadMode.OPERATOR_API
    capabilities = Capabilities(official_download=False, api_access=True, user_authorized_export=True,
                                direct_media_urls=False)
    media_types = ["video", "image"]
    summary = ("Photos and videos through the official X API v2, when the app operator has enabled it. "
               "Otherwise preview + link.")
    limitations = [
        "Requires the operator's paid X API access (pay-per-use since Feb 2026).",
        "Disabled until the operator confirms their X developer agreement permits saving media.",
        "Sensitive-media posts are not supported.",
    ]
    alternatives = [
        Alternative(label="Your own posts: download your archive",
                    description="X → Settings → Your account → Download an archive of your data."),
    ]

    def is_configured(self, settings) -> bool:
        return bool(settings.x_bearer_token) and settings.x_media_downloads_enabled

    def official_url(self, url: str) -> str:
        try:
            return f"https://x.com/i/status/{tweet_id(url)}"
        except UnsupportedLink:
            return url

    async def analyze(self, url: str, ctx: AdapterContext) -> AdapterResult:
        tid = tweet_id(url)
        meta = await fetch_oembed(ctx, "https://publish.twitter.com/oembed",
                                  f"https://twitter.com/i/status/{tid}", ("publish.twitter.com",),
                                  {"omit_script": "1"})
        if not self.is_configured(ctx.settings):
            meta["title"] = None  # oEmbed "title" is empty for posts; author is enough
            return self.link_only(url, "Saving media from X isn't enabled on this server. Open the post in X.",
                                  meta, status=AnalysisStatus.NOT_CONFIGURED)

        token = ctx.settings.x_bearer_token.get_secret_value()  # type: ignore[union-attr]
        data = await ctx.http.get_json(
            f"https://api.x.com/2/tweets/{tid}?expansions=attachments.media_keys,author_id"
            "&media.fields=type,url,variants,preview_image_url,width,height,duration_ms"
            "&tweet.fields=text,possibly_sensitive&user.fields=username",
            allowed_hosts=("api.x.com",), headers={"Authorization": f"Bearer {token}"})
        if data.get("errors") and not data.get("data"):
            raise AdapterError("not_found", "This post is unavailable, deleted, or from a protected account.")
        tweet = data.get("data") or {}
        if tweet.get("possibly_sensitive"):
            raise AdapterError("sensitive_content", "Posts marked as sensitive media aren't supported.")
        includes = data.get("includes") or {}
        users = includes.get("users") or []
        media = includes.get("media") or []
        result = AdapterResult(
            status=AnalysisStatus.DOWNLOADABLE, title=(tweet.get("text") or "")[:140] or None,
            author=f"@{users[0]['username']}" if users else meta.get("author_name"),
            official_url=self.official_url(url), alternatives=list(self.alternatives),
        )
        for i, m in enumerate(media):
            mtype = m.get("type")
            if mtype == "photo" and m.get("url"):
                src = m["url"]
                ext = src.rsplit(".", 1)[-1].lower()
                mt = {"jpg": "image/jpeg", "jpeg": "image/jpeg", "png": "image/png", "webp": "image/webp"}.get(ext)
                if not mt:
                    continue
                full = f"{src}?name=orig"
                size, sniffed = await probe_media(ctx, full, CDN)
                result.add(MediaOption(
                    id=f"p{i}", kind="image", label=label_for("image", "Original", mime.extension_for(mt)),
                    quality_label="Original", width=m.get("width"), height=m.get("height"),
                    mime_type=sniffed or mt, extension=mime.extension_for(sniffed or mt),
                    size_bytes=size, is_original=True), PrivateOption(full))
                result.thumbnail_url = result.thumbnail_url or src
            elif mtype in ("video", "animated_gif"):
                result.thumbnail_url = result.thumbnail_url or m.get("preview_image_url")
                dur = (m.get("duration_ms") or 0) / 1000 or None
                result.duration_seconds = result.duration_seconds or dur
                for j, v in enumerate(m.get("variants") or []):
                    if v.get("content_type") != "video/mp4" or not v.get("url"):
                        continue  # skip HLS playlists
                    dm = _DIMS.search(v["url"])
                    w, h = (int(dm.group(1)), int(dm.group(2))) if dm else (None, None)
                    br = v.get("bit_rate")
                    q = quality_from_height(min(w, h) if w and h else None)
                    est = int(br * dur / 8) if br and dur else None
                    result.add(MediaOption(
                        id=f"v{i}_{j}", kind="video", label=label_for("video", q, "mp4"), quality_label=q,
                        width=w, height=h, bitrate=br, mime_type="video/mp4", extension="mp4", size_bytes=est,
                        size_is_estimate=est is not None, has_audio=mtype == "video",
                        note="GIF (no audio)" if mtype == "animated_gif" else None), PrivateOption(v["url"]))
        result.media_type = ("video" if any(o.kind == "video" for o in result.options)
                             else "gallery" if len(result.options) > 1 else "image" if result.options else "unknown")
        if not result.options:
            result.status = AnalysisStatus.UNAVAILABLE
            result.explanation = "This post has no photos or videos."
        return result
