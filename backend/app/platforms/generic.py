"""Public websites: direct media files, or pages that declare a direct file via og:video / og:image / <video>."""
from __future__ import annotations

import posixpath
import re
from html.parser import HTMLParser
from urllib.parse import unquote, urljoin, urlsplit

from ..schemas import AnalysisStatus, Capabilities, DownloadMode, MediaOption
from ..security import mime
from ..security.filenames import safe_filename
from ..security.http_client import SafeResponse, UpstreamError, host_matches
from ..security.netguard import UnsafeURLError
from .base import AdapterContext, AdapterError, AdapterResult, PlatformAdapter, PrivateOption, label_for

# Signed, expiring copies on platform CDNs. Fetching them would side-step the platform's own access rules.
PROTECTED_CDNS = (
    "googlevideo.com", "ytimg.com", "ggpht.com", "tiktokcdn.com", "tiktokcdn-us.com", "tiktokv.com",
    "tiktokv.us", "byteoversea.com", "ibytedtos.com", "muscdn.com", "cdninstagram.com", "fbcdn.net",
    "fbsbx.com", "redd.it", "twimg.com", "vimeocdn.com", "pinimg.com", "snapchat.com", "sc-cdn.net",
    "nflxvideo.net", "nflxso.net", "aiv-cdn.net", "dssott.com", "hulustream.com",
)
MANIFEST_TYPES = {"application/vnd.apple.mpegurl", "application/x-mpegurl", "audio/mpegurl", "application/dash+xml"}
MAX_CANDIDATES = 6


class _MediaTags(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.meta: dict[str, str] = {}
        self.media: list[str] = []
        self.title: str | None = None
        self._in_title = False

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        a = {k.lower(): (v or "") for k, v in attrs}
        if tag == "meta":
            key = (a.get("property") or a.get("name") or "").lower()
            if key and a.get("content") and key not in self.meta:
                self.meta[key] = a["content"].strip()
        elif tag in ("video", "audio", "source") and a.get("src"):
            self.media.append(a["src"].strip())
        elif tag == "title":
            self._in_title = True

    def handle_endtag(self, tag: str) -> None:
        if tag == "title":
            self._in_title = False

    def handle_data(self, data: str) -> None:
        if self._in_title and not self.title and data.strip():
            self.title = data.strip()[:200]


def _name_from(resp: SafeResponse) -> str | None:
    cd = resp.headers.get("content-disposition", "")
    m = re.search(r"filename\*?=(?:UTF-8'')?\"?([^\";]+)", cd, re.I)
    if m:
        return unquote(m.group(1)).rsplit(".", 1)[0]
    base = posixpath.basename(unquote(urlsplit(resp.url).path))
    return base.rsplit(".", 1)[0] if base else None


class GenericWebAdapter(PlatformAdapter):
    key = "web"
    name = "Websites (direct media)"
    domains = ()
    download_mode = DownloadMode.DIRECT
    capabilities = Capabilities(official_download=False, api_access=False, user_authorized_export=False,
                                direct_media_urls=True)
    media_types = ["video", "image", "audio"]
    summary = "Any public web address that serves a media file directly, or a page that declares one."
    limitations = [
        "Streaming formats (HLS .m3u8, DASH .mpd) and DRM-protected media aren't supported.",
        "Links that need a login, or signed links on social-platform servers, aren't fetched.",
        "Pages are read only for their declared media (og:video, og:image, <video>); nothing is scraped beyond that.",
    ]

    def matches(self, host: str) -> bool:
        return True

    async def _inspect(self, ctx: AdapterContext, url: str) -> tuple[MediaOption | None, SafeResponse, str | None]:
        """Probe one URL. Returns (option or None, response, reason-if-rejected)."""
        try:
            # PROTECTED_CDNS is enforced on the first URL AND on every redirect hop
            resp = await ctx.http.probe(url, sniff_bytes=64, blocked_hosts=PROTECTED_CDNS)
        except UnsafeURLError as exc:
            if exc.code == "host_blocked":
                raise AdapterError("protected_cdn", "That file is on a social platform's server. Paste the original "
                                                    "post link instead.") from exc
            raise
        if resp.status in (401, 403):
            raise AdapterError("forbidden", "The site refused access. The link may have expired or need a login.")
        if resp.status in (404, 410):
            raise AdapterError("not_found", "Nothing was found at this link. It may have expired or been removed.")
        if resp.status >= 400:
            raise AdapterError("upstream_error", f"The site returned an error (HTTP {resp.status}).")
        ct = resp.content_type
        path = urlsplit(resp.url).path.lower()
        if ct in MANIFEST_TYPES or path.endswith((".m3u8", ".mpd")):
            return None, resp, "streaming_manifest"
        if ct.startswith(("text/html", "application/xhtml")):
            return None, resp, "html"
        if not (ct.startswith(("image/", "video/", "audio/")) or ct in ("", "application/octet-stream")):
            return None, resp, "not_media"
        danger = mime.dangerous_kind(resp.body)
        if danger:
            return None, resp, f"dangerous:{danger}"
        detected = mime.sniff(resp.body)
        if not detected:
            return None, resp, "unrecognized_format"
        if not mime.compatible(ct, detected):
            return None, resp, "type_mismatch"
        size = resp.content_length
        kind = detected.split("/")[0]
        ext = mime.extension_for(detected)
        option = MediaOption(id="", kind=kind, label=label_for(kind, "Original", ext), quality_label="Original",
                             mime_type=detected, extension=ext, size_bytes=size, is_original=True,
                             has_audio=None)
        if size and size > ctx.settings.max_media_bytes:
            option.note = "Larger than this app's download limit."
        return option, resp, None

    async def analyze(self, url: str, ctx: AdapterContext) -> AdapterResult:
        try:
            option, resp, reason = await self._inspect(ctx, url)
        except UpstreamError as exc:
            raise AdapterError(exc.code, str(exc)) from exc
        result = AdapterResult(status=AnalysisStatus.DOWNLOADABLE, official_url=url)
        if option:
            option.id = "f0"
            result.title = _name_from(resp)
            result.media_type = option.kind
            result.add(option, PrivateOption(resp.url))
            return self._finish(result, ctx)
        if reason == "streaming_manifest":
            raise AdapterError("streaming_unsupported", "This is a streaming playlist (HLS/DASH), not a single file. "
                                                        "Streams can't be saved as a file by this app.")
        if reason and reason.startswith("dangerous:"):
            raise AdapterError("not_media", "This link points to a program, archive or document, not a photo or video.")
        if reason == "type_mismatch":
            raise AdapterError("type_mismatch", "The file's contents don't match the type the site claims. It was "
                                                "blocked for safety.")
        if reason != "html":
            raise AdapterError("not_media", "No photo, video or audio file was found at this link.")

        page = await ctx.http.request("GET", resp.url, max_bytes=ctx.settings.max_html_bytes,
                                      headers={"Accept": "text/html,application/xhtml+xml"},
                                      blocked_hosts=PROTECTED_CDNS)
        parser = _MediaTags()
        cs = re.search(r"charset=([\w-]+)", page.headers.get("content-type", ""), re.I)
        try:
            text = page.body.decode(cs.group(1) if cs else "utf-8", errors="replace")
        except LookupError:  # unknown charset name
            text = page.body.decode("utf-8", errors="replace")
        try:
            parser.feed(text)
        except Exception:  # malformed markup: use whatever was collected
            pass
        m = parser.meta
        candidates = [m.get(k) for k in ("og:video:secure_url", "og:video:url", "og:video", "twitter:player:stream",
                                         "og:audio:secure_url", "og:audio")] + parser.media + [
            m.get(k) for k in ("og:image:secure_url", "og:image", "twitter:image")]
        seen: list[str] = []
        for c in candidates:
            if not c:
                continue
            absolute = urljoin(page.url, c)
            if urlsplit(absolute).scheme in ("http", "https") and absolute not in seen:
                seen.append(absolute)
        result.title = m.get("og:title") or parser.title
        thumb = m.get("og:image:secure_url") or m.get("og:image")
        result.thumbnail_url = urljoin(page.url, thumb) if thumb and urljoin(page.url, thumb).startswith("https://") else None
        for i, cand in enumerate(seen[:MAX_CANDIDATES]):
            try:
                opt, cresp, _ = await self._inspect(ctx, cand)
            except (AdapterError, UpstreamError, UnsafeURLError):
                continue
            if opt:
                if opt.kind == "image":
                    w, h = m.get("og:image:width"), m.get("og:image:height")
                    if cand in (urljoin(page.url, m.get("og:image") or ""), urljoin(page.url, m.get("og:image:secure_url") or "")):
                        opt.width = int(w) if w and w.isdigit() else None
                        opt.height = int(h) if h and h.isdigit() else None
                    opt.quality_label, opt.is_original = "As published", False
                    opt.label = label_for("image", "As published", opt.extension)
                    opt.note = "The page's preview image; the site may hold a larger original."
                opt.id = f"c{i}"
                result.add(opt, PrivateOption(cresp.url))
        if not result.options:
            raise AdapterError("no_media_found", "This page doesn't declare a downloadable photo, video or audio file.")
        result.media_type = next((o.kind for o in result.options if o.kind == "video"), result.options[0].kind)
        return self._finish(result, ctx)

    def _finish(self, result: AdapterResult, ctx: AdapterContext) -> AdapterResult:
        if result.title:
            result.title = safe_filename(result.title, "x").rsplit(".", 1)[0]
        if all(o.size_bytes and o.size_bytes > ctx.settings.max_media_bytes for o in result.options):
            result.status = AnalysisStatus.UNAVAILABLE
            result.explanation = "The file is larger than this app's download limit."
        return result
