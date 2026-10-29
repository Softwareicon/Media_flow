# Testing

## Automated (run in CI — `.github/workflows/ci.yml`)

> All upstream platform traffic in automated tests is **mocked** (`backend/tests/conftest.py → FakeWeb`). Mock responses follow each platform's documented response shape. Passing tests prove our parsing, policy and security logic — **not** that a live integration works. Live checks are in the last section.

| Suite | Command | Count | Covers |
|---|---|---|---|
| Backend unit + security | `cd backend && python -m pytest -q` | 147 | URL extraction/normalisation, platform detection incl. look-alike domains, ID parsers, quality labelling, MIME sniffing, dangerous-file detection, type spoofing, safe file names, SSRF (private/reserved/mapped IPs, numeric loopback encodings, DNS answers with private records, redirects to internal hosts, https→http downgrade, redirect loops, allow-list escape, credential stripping, IP pinning, body caps, IPv6 Host header, site-local `fec0::/10`) |
| Backend API integration | (same run) | | full download lifecycle, failed downloads with reason, cancel, list/search/filter/cursor pagination, user isolation, expired analysis (410), unknown option, size limit, expired/404/403 links, spoofed & dangerous files, HLS manifests, HTML pages with declared media (private candidates never fetched), protected platform CDNs incl. via redirects and page candidates, rate limiting (429 + Retry-After), history opt-out, register/login/logout/account deletion, invalid input, retention purge |
| Backend platform adapters | (same run) | | YouTube/TikTok link-only + oEmbed failure, dating export-only, X disabled-by-default + variants + sensitive refusal, Vimeo not-configured/needs-connection/OAuth connect/renditions/not-owner/disconnect, OAuth state single-use & platform-bound, OAuth link-to-victim attack refused, verifier required, encryption key required, Instagram own-post matching + long-lived token + someone else's post, Facebook owned vs not owned, Pinterest largest rendition + video link-only, Reddit gallery/video/NSFW/external/media-server links, registry honesty, secrets never returned |
| Mobile unit | `cd mobile && npx jest` | 50 (3 suites) | download state machine, FIFO scheduler + concurrency + Wi-Fi block, speed/ETA meter incl. restart, duplicate detection, insufficient-storage maths, error classification + retry/backoff, URL/platform hints, on-device file-signature verification, file names, formatting |
| Mobile download manager | (same run) | | the real `DownloadManager` against mocked `expo-file-system` / `expo-media-library` / `expo-network` / API: happy path to Photos, HTML-as-video blocked, size mismatch, FIFO concurrency, pause/resume, cancel + retry, network failure auto-retry, expired analysis re-analyzed, duplicates & no-space, permission denied, cancel during authorization, no zombie rows after removal, Android folder save, Photos rejection kept in-app, resume after restart re-authorizes, double-pause, Wi-Fi listener |
| Mobile types | `npx tsc --noEmit` | — | strict + `noUncheckedIndexedAccess` |
| Mobile bundle | `npx expo export -p android -p ios` | — | the whole app compiles to Hermes bytecode for both platforms |
| Migration | `alembic upgrade head` + autogenerate diff | — | migration == models |

## Device testing (manual — required before release)

Run on: Android emulator (API 34+), one physical Android (preferably an aggressive-battery OEM like Xiaomi/Samsung), iOS simulator, one physical iPhone, one iPad / Android tablet.

| # | Scenario | Expected |
|---|---|---|
| D1 | Paste a direct `.mp4` from your own test server, download | progress %, speed, ETA; lands in Photos; appears in Gallery; plays offline |
| D2 | Same link again | "Already downloaded" prompt |
| D3 | Pause mid-download, resume | continues from the same byte (server supports Range) |
| D4 | Pause, force-quit app, reopen, resume | item re-authorizes, then continues from the paused byte if the source URL is unchanged and supports Range; otherwise restarts |
| D4b | Force-quit mid-download (not paused) | item comes back queued and downloads from the start |
| D5 | Airplane mode mid-download | fails with network message, auto-retries with backoff when back online, manual Retry works |
| D6 | Set concurrency 1, queue 3 files | one runs, two *Queued*; next starts when the first finishes |
| D7 | Wi-Fi only on cellular | items stay queued; start automatically when Wi-Fi returns |
| D8 | Fill device storage, download a large file | *Not enough space* before start (known size) or failure *insufficient storage* |
| D9 | Link to an HTML page served as `video/mp4` | blocked, file deleted, nothing in Photos |
| D10 | Deny photo permission | file kept in app, Gallery shows it |
| D11 | Android: Settings → save to Folder → pick a folder | file copied into it |
| D12 | iOS: start a large download, lock phone | completes in background (OS permitting) |
| D13 | YouTube link | preview, *Open in YouTube*, alternatives; no download button |
| D14 | Connect Vimeo (own paid account), paste own video | renditions incl. *Original*; downloads |
| D15 | Share from Gallery | native share sheet; *Save to Files* on iOS |
| D16 | Delete account | server data gone; app gets a fresh anonymous session |

## Accessibility & responsive

- [ ] VoiceOver (iOS) and TalkBack (Android): every control announces a label; quality options are announced as radio buttons with size; progress bars expose value; toasts are announced
- [ ] Dynamic Type / font scale 200%: no clipped text on Home, Downloads, Settings
- [ ] Contrast: check both themes with Accessibility Inspector / Accessibility Scanner (tokens target WCAG AA for text)
- [ ] Touch targets ≥ 44pt / 48dp (enforced by `HIT` and `minHeight` in components)
- [ ] One-handed use: primary actions (Paste, Analyze, Download) sit in the lower-middle of the screen on phones
- [ ] Tablets: content width capped at 760 px; Gallery uses 4–5 columns; preview card goes side-by-side
- [ ] Landscape on phones: screens scroll, no overlap

## Live integration checklist (per platform, with real credentials)

Do not mark a platform "working" in release notes until its row passes against the real API.

| Platform | Test | Pass criteria |
|---|---|---|
| Web direct | public sample MP4/JPEG you host | size + MIME correct, downloads |
| YouTube | any public video | oEmbed title/thumbnail shown, link-only |
| TikTok | any public video | oEmbed preview, link-only |
| Vimeo | own video on Standard+ plan, connected | renditions match Vimeo's *Download* menu |
| Instagram | own post on a Business/Creator account | media matched by shortcode; carousel items listed |
| Facebook | video on a Page you admin | `source` returned, downloads |
| Pinterest | own image Pin | 1200px rendition downloads |
| Reddit | image + gallery post (approved client) | originals from i.redd.it |
| X | photo + video post (opted in) | photo `orig`, MP4 variants by bitrate |
