# Project status — stage reports

*Build date: 29 Oct 2026. "Verified" means executed in the build sandbox; "not verified" means it needs real credentials, devices, or stores that the sandbox doesn't have.*

## Stage 1 — Feasibility ✅
- **Files:** `docs/FEASIBILITY.md`
- **Outcome:** YouTube & TikTok link-only; Instagram/Facebook/Vimeo/Pinterest user-authorized (own content); Reddit images & X via operator API (opt-in); public web direct files; dating apps export-only.
- **Blockers:** Platform terms change frequently — re-verify before each release. Reddit reportedly closing new Data API requests at end of Oct 2026 (unconfirmed).

## Stage 2 — Architecture ✅
- **Files:** `docs/ARCHITECTURE.md`, `docs/API.md`, `docs/openapi.json`, `docs/schema.postgres.sql`, `backend/app/models.py`, `backend/app/schemas.py`, `backend/alembic/versions/0001_initial.py`
- **Tests:** migration applied and diffed against the models with Alembic autogenerate → no differences. Postgres DDL rendered offline (no Postgres server in the sandbox, so not applied to a live Postgres).

## Stage 3 — Mobile UI & navigation ✅
- **Files:** `mobile/app/**` (5 tabs + player, platforms, account), `mobile/src/components/*`, `mobile/src/theme/*`, `mobile/assets/*`
- **Tests:** strict TypeScript passes; Metro export produces Android + iOS Hermes bundles; `expo prebuild` generates both native projects.
- **Not verified:** visual rendering on devices/simulators (no emulator in sandbox) — see `docs/TESTING.md` device matrix.

## Stage 4 — Backend, security, integrations ✅ (logic) / ⏳ (live)
- **Files:** `backend/app/**`
- **Tests:** 147 pytest tests pass — SSRF suite, API integration, every adapter against mocked documented responses. A real uvicorn server was started and smoke-tested (health, anonymous session, SSRF rejections, platform registry, 16 OpenAPI paths).

| Integration | Code | Live-tested |
|---|---|---|
| Public web direct files | ✅ | ⏳ sandbox has no general internet |
| YouTube preview (oEmbed) | ✅ | ⏳ |
| TikTok preview (oEmbed) | ✅ | ⏳ |
| Vimeo OAuth + renditions | ✅ | ⏳ needs app credentials + paid account |
| Instagram (Instagram Login) | ✅ | ⏳ needs Meta app review |
| Facebook Page videos | ✅ | ⏳ needs Meta app review; confirm required permission |
| Pinterest images | ✅ | ⏳ needs Pinterest app access |
| Reddit images | ✅ | ⏳ needs Reddit Data API approval |
| X photos/videos | ✅ (off by default) | ⏳ needs paid API credits + legal sign-off |

Per the brief, **none of these is claimed to work against the live platform** until the live checklist in `docs/TESTING.md` passes.

## Stage 5 — Download manager, saving, previews ✅ (logic) / ⏳ (device)
- **Files:** `mobile/src/downloads/*`, `mobile/src/db/database.ts`, `mobile/src/lib/*`
- **Tests:** 50 jest tests — the pure logic (state machine, scheduler, speed/ETA, duplicates, storage, error classification/backoff, file-signature verification, file names, URL hints) plus 17 that drive the real `DownloadManager` against mocked native modules.
- **Not verified:** the native transfer path (`File.createDownloadTask`, pause/resume, background session, `Asset.create`, Android SAF copy) needs a device — test rows D1–D16.

## Independent review (29 Oct) ✅
A separate reviewer audited the code and docs and found 16 code issues and 6 inaccurate doc claims. All were fixed and each fix has a regression test:
- **Security:** platform-CDN block could be bypassed by a redirect (now checked on every hop); OAuth state wasn't bound to the app that started the flow (now a verifier + authenticated `complete` step); Docker image trusted forwarded headers from anyone (now `FORWARDED_ALLOW_IPS`); `fec0::/10` blocked; IPv6 Host header bracketed.
- **Download manager:** cancel during authorization/verification could still save to Photos; resume after restart used a stale URL; Android folder save always failed; a Photos rejection triggered repeated re-downloads; removed items could reappear from retry timers; orphaned server records; double-pause; Wi-Fi-only queue never restarted.
- **Testing also caught** (before review): HTML charset decoding swallowed page parsing; the size-integrity check compared the file with itself.

## Stage 6 — Testing, errors, performance ✅
- Error handling: typed error codes end-to-end; every non-downloadable result carries an explanation and official route; transient download errors auto-retry with 2 s / 4 s / 8 s backoff.
- Performance: progress events throttled to 4 UI updates/s; SQLite writes throttled to every 2 s per item; Gallery uses `FlatList` + `expo-image` with disk cache and recycling keys; HTML parsing capped at 512 KB; probes read 64 bytes.
- CI: `.github/workflows/ci.yml` runs pytest, tsc, jest and the Metro export.

## Stage 7 — Builds & deployment docs ✅
- **Files:** `docs/MOBILE_BUILDS.md`, `docs/DEPLOYMENT.md`, `docs/STORE_CHECKLISTS.md`, `docs/PRIVACY_POLICY.md`, `docs/TERMS.md`, `docs/TROUBLESHOOTING.md`, `backend/Dockerfile`, `docker-compose.yml`, `mobile/eas.json`
- **Not verified:** signed builds and store submission (needs your Apple/Google accounts).

## Remaining blockers (owner: you)
1. Replace `com.yourcompany.mediaflowpro`, the EAS project ID, API URLs, and the privacy/terms URLs.
2. Apply for the platform developer access you want (table in `DEPLOYMENT.md` §6). Without it those platforms correctly show "not set up".
3. Run the device matrix (D1–D16) and the live integration checklist before release.
4. Legal review of the privacy policy/terms and of enabling X/Reddit.
5. For multi-replica deployments, move rate limiting to Redis.

## Known limitations (by design or platform)
- No remuxing: sources with separate audio/video streams (Reddit video, HLS/DASH) are link-only rather than "downloaded without sound".
- No conversion between formats (the brief allows it only where legally permitted; omitted to avoid shipping ffmpeg and its licensing obligations).
- Android has no guaranteed background execution; interrupted downloads resume on demand.
- iOS has no arbitrary "folder" target; files go to Photos, stay in-app, or are exported via the share sheet (*Save to Files*).
- Local push notifications for completed downloads are not included (in-app toasts only); add `expo-notifications` if wanted.
