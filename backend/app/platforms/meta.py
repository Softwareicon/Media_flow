"""Instagram and Facebook (Meta). Both only expose media to the account that owns it."""
from __future__ import annotations

import re
from urllib.parse import parse_qs, urlencode, urlsplit

from ..schemas import AnalysisStatus, Alternative, Capabilities, DownloadMode, MediaOption
from ..security import mime
from .base import (AdapterContext, AdapterError, AdapterResult, PlatformAdapter, PrivateOption, UnsupportedLink,
                   label_for, probe_media)

META_CDN = ("cdninstagram.com", "fbcdn.net")
_IG_CODE = re.compile(r"^/(?:[^/]+/)?(?:p|reel|reels|tv)/([A-Za-z0-9_-]{5,40})")


def ig_shortcode(url: str) -> str:
    m = _IG_CODE.match(urlsplit(url).path)
    if not m:
        raise UnsupportedLink("Paste a link to a single Instagram post or reel (…/p/… or …/reel/…).")
    return m.group(1)


class InstagramAdapter(PlatformAdapter):
    key = "instagram"
    name = "Instagram"
    domains = ("instagram.com", "instagr.am")
    download_mode = DownloadMode.CONNECTED_ACCOUNT
    capabilities = Capabilities(official_download=False, api_access=True, user_authorized_export=True,
                                direct_media_urls=False)
    media_types = ["video", "image"]
    requires_connection = True
    oauth_provider = "instagram"
    summary = "Save posts and reels from your own Instagram professional (Business/Creator) account."
    limitations = [
        "Only media posted by the connected account. Other people's posts can't be downloaded.",
        "Personal accounts aren't supported: Meta shut down the Basic Display API on 4 Dec 2024.",
        "The API doesn't report pixel dimensions; you get the file Instagram serves via the API.",
    ]
    alternatives = [
        Alternative(label="Download your Instagram data",
                    description="Instagram → Settings → Accounts Centre → Your information and permissions → "
                                "Download your information. Includes your original photos and videos."),
    ]

    def is_configured(self, settings) -> bool:
        return bool(settings.instagram_app_id and settings.instagram_app_secret)

    def official_url(self, url: str) -> str:
        try:
            return f"https://www.instagram.com/p/{ig_shortcode(url)}/"
        except UnsupportedLink:
            return url

    async def analyze(self, url: str, ctx: AdapterContext) -> AdapterResult:
        code = ig_shortcode(url)
        if not self.is_configured(ctx.settings):
            return self.link_only(url, "Instagram downloads aren't set up on this server. Open the post in Instagram.",
                                  status=AnalysisStatus.NOT_CONFIGURED)
        if not ctx.access_token:
            return self.link_only(url, "Instagram only lets apps access media from your own professional account. "
                                       "Connect it to save your posts; other people's posts can only be opened in "
                                       "Instagram.", status=AnalysisStatus.NEEDS_CONNECTION)

        fields = "id,permalink,media_type,media_url,thumbnail_url,caption,username,children{media_type,media_url,thumbnail_url}"
        next_url: str | None = ("https://graph.instagram.com/me/media?"
                                + urlencode({"fields": fields, "limit": 50, "access_token": ctx.access_token}))
        found = None
        for _ in range(6):  # up to ~300 most recent posts
            if not next_url:
                break
            page = await ctx.http.get_json(next_url, allowed_hosts=("graph.instagram.com",))
            for item in page.get("data") or []:
                try:
                    if ig_shortcode(item.get("permalink") or "") == code:
                        found = item
                        break
                except UnsupportedLink:
                    continue
            if found:
                break
            next_url = (page.get("paging") or {}).get("next")
        if not found:
            return self.link_only(url, "This post isn't one of the recent posts on your connected account, so "
                                       "Instagram won't release it. Open it in Instagram instead.")

        result = AdapterResult(
            status=AnalysisStatus.DOWNLOADABLE, title=(found.get("caption") or "")[:140] or None,
            author=f"@{found['username']}" if found.get("username") else None,
            thumbnail_url=found.get("thumbnail_url") or found.get("media_url"),
            official_url=self.official_url(url), alternatives=list(self.alternatives),
        )
        children = (found.get("children") or {}).get("data") or [found]
        for i, item in enumerate(children):
            src = item.get("media_url")
            if not src:
                continue
            kind = "video" if item.get("media_type") == "VIDEO" else "image"
            size, sniffed = await probe_media(ctx, src, META_CDN)
            mt = sniffed or ("video/mp4" if kind == "video" else "image/jpeg")
            result.add(MediaOption(
                id=f"m{i}", kind=kind, label=label_for(kind, f"Item {i + 1}" if len(children) > 1 else "As provided",
                                                       mime.extension_for(mt)),
                quality_label="As provided by Instagram", mime_type=mt, extension=mime.extension_for(mt),
                size_bytes=size, has_audio=True if kind == "video" else None,
                note="Instagram's API serves this file; it may be re-encoded from your upload."),
                PrivateOption(src))
        result.media_type = "gallery" if len(result.options) > 1 else (result.options[0].kind if result.options else "unknown")
        return result


_FB_VIDEO = (re.compile(r"/videos/(?:[^/]+/)?(\d{6,25})"), re.compile(r"/reel/(\d{6,25})"))


def fb_video_id(url: str) -> str:
    p = urlsplit(url)
    for rx in _FB_VIDEO:
        m = rx.search(p.path)
        if m:
            return m.group(1)
    q = parse_qs(p.query)
    for k in ("v", "video_id"):
        if q.get(k) and q[k][0].isdigit():
            return q[k][0]
    raise UnsupportedLink("Paste a facebook.com video or reel link (fb.watch short links: open them first and "
                          "copy the full address).")


class FacebookAdapter(PlatformAdapter):
    key = "facebook"
    name = "Facebook"
    domains = ("facebook.com", "fb.com", "fb.watch")
    download_mode = DownloadMode.CONNECTED_ACCOUNT
    capabilities = Capabilities(official_download=False, api_access=True, user_authorized_export=True,
                                direct_media_urls=False)
    media_types = ["video"]
    requires_connection = True
    oauth_provider = "facebook"
    summary = "Save videos you posted, or that were posted by a Page you manage, after connecting Facebook."
    limitations = [
        "The Graph API only returns a video file to its owner or an admin of the posting Page.",
        "fb.watch short links must be expanded first.",
    ]
    alternatives = [
        Alternative(label="Download your information",
                    description="Facebook → Settings → Accounts Centre → Your information and permissions → "
                                "Download your information. Includes videos you uploaded."),
    ]

    def is_configured(self, settings) -> bool:
        return bool(settings.facebook_app_id and settings.facebook_app_secret)

    async def analyze(self, url: str, ctx: AdapterContext) -> AdapterResult:
        vid = fb_video_id(url)
        if not self.is_configured(ctx.settings):
            return self.link_only(url, "Facebook downloads aren't set up on this server. Open the video on Facebook.",
                                  media_type="video", status=AnalysisStatus.NOT_CONFIGURED)
        if not ctx.access_token:
            return self.link_only(url, "Facebook only gives apps the video file if you posted it or manage the Page "
                                       "that did. Connect Facebook to check.", media_type="video",
                                  status=AnalysisStatus.NEEDS_CONNECTION)
        ver = ctx.settings.facebook_graph_version
        data = await ctx.http.get_json(
            f"https://graph.facebook.com/{ver}/{vid}?"
            + urlencode({"fields": "source,title,description,length,picture,from", "access_token": ctx.access_token}),
            allowed_hosts=("graph.facebook.com",))
        if data.get("error"):
            raise AdapterError("upstream_forbidden", "Facebook didn't allow access to this video.")
        src = data.get("source")
        if not src:
            return self.link_only(url, "Facebook didn't release the video file — it isn't yours or a Page's you "
                                       "manage.", {"title": data.get("title")}, "video")
        size, sniffed = await probe_media(ctx, src, META_CDN)
        mt = sniffed or "video/mp4"
        result = AdapterResult(
            status=AnalysisStatus.DOWNLOADABLE, title=data.get("title") or (data.get("description") or "")[:140] or None,
            author=(data.get("from") or {}).get("name"), thumbnail_url=data.get("picture"),
            duration_seconds=data.get("length"), media_type="video", official_url=url,
            alternatives=list(self.alternatives),
        )
        result.add(MediaOption(id="src", kind="video", label=label_for("video", "As provided", mime.extension_for(mt)),
                               quality_label="As provided by Facebook", mime_type=mt,
                               extension=mime.extension_for(mt), size_bytes=size, has_audio=True), PrivateOption(src))
        return result
