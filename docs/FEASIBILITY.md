# Stage 1 — Technical Feasibility Assessment

*MediaFlow Pro · assessed 29 Oct 2026 · re-verify every platform row before each release — these terms change often.*

## Bottom line

A "paste any link, get the original file" app is **not** buildable for the big social platforms without breaking their terms, and the spec forbids that. What *is* buildable, and what this repository implements:

| Bucket | Platforms | What the user gets |
|---|---|---|
| **Downloadable directly** | Public websites serving a direct media file (`.mp4`, `.jpg`, `og:video` pointing at a file…) | Real download, original quality, size + MIME verified |
| **Downloadable with the user's own authorization** | Vimeo (own videos, paid plan), Instagram (own Business/Creator account), Facebook (own videos/Page videos), Pinterest (own pins, images only), Reddit images (approved API client), X (operator-paid API, off by default) | Real download after the user connects their account (OAuth) or the operator configures credentials |
| **Official link only** | YouTube, TikTok, Reddit-hosted video, video Pins, any platform with no credentials configured | Preview (title, author, thumbnail via the platform's public oEmbed) + "Open in app" + the platform's own offline/export route |
| **Export only** | Tinder, Bumble, Hinge and other dating apps | Explanation + link to the platform's own "download my data" page |

The registry (`backend/app/platforms/`) encodes this per platform and the app never labels a platform "downloadable" unless its adapter is configured and the specific link resolves to an authorized file.

## Platform-by-platform

### YouTube — official link only
- YouTube's Terms forbid downloading unless YouTube shows a download button/link. YouTube Legal has sent cease-and-desist letters to third-party clients for exactly this (e.g. the 2024 letter to FUTO's Grayjay over "downloading of YouTube Content").
- The YouTube Data API returns metadata, never media files.
- **Implemented:** oEmbed preview (title, channel, thumbnail); optional duration via Data API key; official alternatives — *YouTube Premium offline* in the YouTube app, and *YouTube Studio → Download* for the creator's own uploads.

### Instagram — own professional account only
- The Instagram Basic Display API (which allowed personal-account media reads) was shut down on **4 Dec 2024**. The remaining *Instagram API with Instagram Login* works only for **Business/Creator** accounts and only for the connected account's own media; it returns `media_url`.
- **Implemented:** OAuth connection; the pasted post/reel is matched by shortcode against the user's own `/me/media` list; if it matches, the API's `media_url` becomes the download. Anything else → official link. Requires Meta app review before production.

### Facebook — own videos / managed Pages only
- Graph API exposes a video's `source` only to the owner or an admin of the Page that posted it.
- **Implemented:** OAuth connection + Graph lookup by video ID. Everyone else → official link + Facebook's *Download your information* export.

### TikTok — official link only
- The Display API returns `share_url`, `embed_link`, and a 6-hour cover image — no video file. TikTok's own in-app *Save video* (when the creator allows it) and the account data export are the authorized routes.
- **Implemented:** public oEmbed preview + official link + those alternatives.

### X (Twitter) — API-based, operator must opt in
- API v2 returns photo URLs and MP4 `variants` (with bitrates) for video through `expansions=attachments.media_keys`. Since 6 Feb 2026 X bills pay-per-use by default.
- Whether *saving media to an end user's device* is allowed under the operator's X developer agreement is a legal call for the operator, so the adapter is **disabled unless `X_BEARER_TOKEN` is set and `X_MEDIA_DOWNLOADS_ENABLED=true`**. Without it → oEmbed preview + official link.

### Pinterest — own pins, images only
- API v5 `GET /v5/pins/{id}` returns image renditions up to `1200x` wide; Pinterest staff have stated the API does not provide a direct link to uploaded originals or video files.
- **Implemented:** OAuth connection; largest available image rendition (labelled honestly as "1200px – largest the API provides", not "original"). Video pins → official link.

### Reddit — images via approved API client; video link-only
- Reddit requires explicit approval before any Data API access; commercial use needs a written contract. One source reports Reddit is closing new Data API requests at the end of Oct 2026 — **confirm with Reddit before planning on it.**
- Reddit-hosted video (`v.redd.it`) is DASH with **separate video and audio streams**. The spec requires synced audio+video and forbids inventing qualities, and the app does not remux, so Reddit video is link-only.
- **Implemented:** app-only OAuth (`REDDIT_CLIENT_ID/SECRET`), `i.redd.it` images and galleries. Video → official link.

### Vimeo — own videos on a paid plan
- With a token holding `public private video_files` scopes, `GET /videos/{id}` returns a `download` array: one entry per rendition with width/height/size and a link valid 24 h. Requires Standard plan or above, and only for the token owner's videos.
- **Implemented:** OAuth connection; every rendition in `download` becomes a quality option exactly as Vimeo reports it. Without a connection → oEmbed preview + official link.

### Public websites — direct files
- **Implemented:** SSRF-guarded probe of the URL. A direct `image/*`, `video/*` or `audio/*` response → option with real size and MIME (verified by magic bytes). An HTML page → `og:video`, `og:image`, `<video>/<source>` candidates, each probed the same way. HLS/DASH manifests (`.m3u8`, `.mpd`) are refused — those are segmented streams, frequently DRM-protected.
- Known platform media CDNs (googlevideo.com, tiktokcdn, cdninstagram, fbcdn, v.redd.it…) are refused by the generic adapter — including when a short link or page *redirects* to them: those URLs are signed, expiring copies that the spec says not to bypass.

### Dating apps (Tinder, Bumble, Hinge) — export only
- None offers a third-party media API. Each offers a personal data export from account settings. The app explains this and links to it.

## App-store implications
- **Google Play** removes apps that help users violate other services' terms; YouTube downloaders are the classic rejection. Because YouTube and TikTok are link-only here, the build is policy-compatible — but **do not use platform logos or "YouTube downloader" wording** in the listing (Play's impersonation/IP policy).
- **Apple** reviews downloaders under guideline 5.2.3 (third-party media must be authorized). Keep the in-app explanations visible to reviewers; the review notes template is in `docs/STORE_CHECKLISTS.md`.

## Mobile OS limits
- **iOS:** downloads use `URLSession` background sessions (`sessionType: BACKGROUND`), so a transfer can finish after the app is suspended. iOS decides when; there's no guarantee of continuous execution and force-quitting the app cancels transfers.
- **Android:** transfers run while the app process lives. Android may kill the process in the background (Doze, OEM battery savers); a transfer interrupted that way is re-queued and starts again from zero when the app next runs. An item the user *paused* keeps its resume data and continues from where it stopped, as long as the source URL hasn't changed. No foreground service is used, so nothing is promised beyond that.

## What cannot be verified from this build environment
The build sandbox can't reach platform APIs and has no provider credentials. Every adapter's request/response handling is unit-tested against **recorded response shapes from official docs**, clearly marked as mocks. Live verification steps are in `docs/STATUS.md` → *Live integration checklist*. Per the spec, no adapter is claimed to work until that checklist is run.
