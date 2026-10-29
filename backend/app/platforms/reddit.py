from __future__ import annotations

import html
import re
import time
from urllib.parse import urlsplit

from ..schemas import AnalysisStatus, Alternative, Capabilities, DownloadMode, MediaOption
from ..security import mime
from ..security.http_client import UpstreamError, host_matches
from .base import (AdapterContext, AdapterError, AdapterResult, PlatformAdapter, PrivateOption, UnsupportedLink,
                   label_for, probe_media)

REDDIT_HOSTS = ("reddit.com", "redd.it")
_COMMENTS = re.compile(r"/comments/([a-z0-9]{4,12})", re.I)
_SHORT = re.compile(r"^/([a-z0-9]{4,12})/?$", re.I)
_SHARE = re.compile(r"^/r/[^/]+/s/[A-Za-z0-9]+")
_IMG_MIME = {"image/jpg": "image/jpeg", "image/jpeg": "image/jpeg", "image/png": "image/png",
             "image/gif": "image/gif", "image/webp": "image/webp"}

_token_cache: dict[str, tuple[str, float]] = {}


class RedditAdapter(PlatformAdapter):
    key = "reddit"
    name = "Reddit"
    domains = REDDIT_HOSTS
    download_mode = DownloadMode.OPERATOR_API
    capabilities = Capabilities(official_download=False, api_access=True, user_authorized_export=True,
                                direct_media_urls=True)
    media_types = ["image"]
    summary = "Images and galleries from Reddit posts via Reddit's approved Data API. Reddit videos: link only."
    limitations = [
        "Requires the operator to hold an approved Reddit Data API client; commercial use needs a Reddit contract.",
        "Reddit-hosted videos are split into separate video and audio streams; MediaFlow doesn't remux them, so "
        "they open in Reddit instead of downloading.",
        "NSFW posts are not supported.",
    ]
    alternatives = [
        Alternative(label="Request your Reddit data",
                    description="reddit.com/settings/data-request — exports your own posts and uploads.",
                    url="https://www.reddit.com/settings/data-request"),
    ]

    def is_configured(self, settings) -> bool:
        return bool(settings.reddit_client_id and settings.reddit_client_secret)

    async def _app_token(self, ctx: AdapterContext) -> str:
        cid = ctx.settings.reddit_client_id or ""
        cached = _token_cache.get(cid)
        if cached and cached[1] > time.time() + 60:
            return cached[0]
        resp = await ctx.http.request(
            "POST", "https://www.reddit.com/api/v1/access_token", data={"grant_type": "client_credentials"},
            auth=(cid, ctx.settings.reddit_client_secret.get_secret_value()),  # type: ignore[union-attr]
            headers={"User-Agent": ctx.settings.reddit_user_agent}, allowed_hosts=("www.reddit.com",),
            follow_redirects=False)
        if resp.status != 200:
            raise AdapterError("upstream_forbidden", "Reddit rejected this server's API credentials.")
        body = resp.json()
        _token_cache[cid] = (body["access_token"], time.time() + float(body.get("expires_in", 3600)))
        return body["access_token"]

    async def _post_id(self, url: str, ctx: AdapterContext) -> str:
        p = urlsplit(url)
        host = (p.hostname or "").lower()
        if host in ("i.redd.it", "v.redd.it", "preview.redd.it"):
            raise UnsupportedLink("That's a Reddit media-server link. Paste the link to the Reddit post instead.")
        m = _COMMENTS.search(p.path)
        if m:
            return m.group(1).lower()
        if host_matches(host, ("redd.it",)):
            m = _SHORT.match(p.path)
            if m:
                return m.group(1).lower()
        if _SHARE.match(p.path):  # /r/<sub>/s/<code> share links redirect to the canonical post
            resp = await ctx.http.request("HEAD", url, allowed_hosts=REDDIT_HOSTS,
                                          headers={"User-Agent": ctx.settings.reddit_user_agent})
            m = _COMMENTS.search(urlsplit(resp.url).path)
            if m:
                return m.group(1).lower()
        raise UnsupportedLink("Paste a link to a single Reddit post (…/comments/<id>/…).")

    async def analyze(self, url: str, ctx: AdapterContext) -> AdapterResult:
        if (urlsplit(url).hostname or "").lower() in ("i.redd.it", "v.redd.it", "preview.redd.it"):
            raise UnsupportedLink("That's a Reddit media-server link. Paste the link to the Reddit post instead.")
        if not self.is_configured(ctx.settings):
            return self.link_only(url, "Reddit isn't set up on this server. Open the post in Reddit.",
                                  status=AnalysisStatus.NOT_CONFIGURED)
        pid = await self._post_id(url, ctx)
        token = await self._app_token(ctx)
        data = await ctx.http.get_json(f"https://oauth.reddit.com/api/info?id=t3_{pid}&raw_json=1",
                                       allowed_hosts=("oauth.reddit.com",),
                                       headers={"Authorization": f"bearer {token}",
                                                "User-Agent": ctx.settings.reddit_user_agent})
        children = ((data or {}).get("data") or {}).get("children") or []
        if not children:
            raise AdapterError("not_found", "This Reddit post doesn't exist, was removed, or is private.")
        post = children[0].get("data") or {}
        if post.get("over_18"):
            raise AdapterError("sensitive_content", "NSFW posts aren't supported.")
        official = f"https://www.reddit.com{post.get('permalink', f'/comments/{pid}/')}"
        preview = ((post.get("preview") or {}).get("images") or [{}])[0].get("source") or {}
        thumb = html.unescape(preview["url"]) if preview.get("url") else None
        result = AdapterResult(status=AnalysisStatus.DOWNLOADABLE, title=post.get("title"),
                               author=f"u/{post['author']}" if post.get("author") else None,
                               thumbnail_url=thumb, official_url=official, alternatives=list(self.alternatives))

        if post.get("is_video") or ((post.get("secure_media") or {}).get("reddit_video")):
            vid = (post.get("secure_media") or {}).get("reddit_video") or {}
            result.status = AnalysisStatus.LINK_ONLY
            result.media_type = "video"
            result.duration_seconds = vid.get("duration")
            result.explanation = ("Reddit stores this video's picture and sound as separate streams, so there's no "
                                  "single file with audio to save. Open it in Reddit.")
            return result

        candidates: list[tuple[str, str, int | None, int | None]] = []  # url, mime, w, h
        if post.get("is_gallery"):
            meta = post.get("media_metadata") or {}
            for item in (post.get("gallery_data") or {}).get("items") or []:
                md = meta.get(item.get("media_id")) or {}
                mt = _IMG_MIME.get(md.get("m", ""))
                if md.get("status") != "valid" or md.get("e") != "Image" or not mt:
                    continue
                s = md.get("s") or {}
                candidates.append((f"https://i.redd.it/{item['media_id']}.{mime.extension_for(mt)}", mt,
                                   s.get("x"), s.get("y")))
        else:
            dest = post.get("url_overridden_by_dest") or post.get("url") or ""
            if host_matches(urlsplit(dest).hostname or "", ("i.redd.it",)):
                ext = dest.rsplit(".", 1)[-1].lower()
                mt = _IMG_MIME.get(f"image/{ext}")
                if mt:
                    candidates.append((dest, mt, preview.get("width"), preview.get("height")))
            elif dest and not host_matches(urlsplit(dest).hostname or "", REDDIT_HOSTS):
                result.status = AnalysisStatus.LINK_ONLY
                result.explanation = "This post links to another website. Analyze that link directly."
                result.alternatives.insert(0, Alternative(label="Linked page", description=dest, url=dest))
                return result

        for i, (src, mt, w, h) in enumerate(candidates[:50]):
            size, sniffed = await probe_media(ctx, src, ("i.redd.it",))
            mt = sniffed or mt
            result.add(MediaOption(id=f"i{i}", kind="image",
                                   label=label_for("image", "Original" if len(candidates) == 1 else f"Image {i + 1}",
                                                   mime.extension_for(mt)),
                                   quality_label="Original", width=w, height=h, mime_type=mt,
                                   extension=mime.extension_for(mt), size_bytes=size, is_original=True),
                       PrivateOption(src))
        result.media_type = "gallery" if len(result.options) > 1 else "image"
        if not result.options:
            result.status = AnalysisStatus.UNAVAILABLE
            result.explanation = "This post has no Reddit-hosted images."
        return result


__all__ = ["RedditAdapter", "UpstreamError"]
