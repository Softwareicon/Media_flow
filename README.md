# MediaFlow Pro

Cross-platform (Android + iOS) app for saving photos and videos **you're allowed to keep**, in the highest quality the source actually offers — with an honest "open it officially" path for platforms that don't permit third-party downloads.

| | |
|---|---|
| **Mobile** | React Native 0.88 · Expo SDK 58 · Expo Router · TypeScript (strict) · SQLite |
| **Backend** | Python 3.13 · FastAPI · SQLAlchemy 2 (async) · PostgreSQL · Alembic |
| **Tests** | 147 backend (pytest) · 50 mobile (jest, incl. the real download manager on mocked native modules) · strict `tsc` · Metro export for Android + iOS · `expo prebuild` |

> **Read first:** [`docs/FEASIBILITY.md`](docs/FEASIBILITY.md) explains which platforms can and can't be downloaded from, and why. [`docs/STATUS.md`](docs/STATUS.md) lists exactly what was verified and what still needs live credentials and devices.

## What it does

1. Paste a link (or tap **Paste**) → **Analyze link**.
2. The server identifies the platform and returns only what that platform authorizes:
   - **Downloadable** → preview + real quality options (resolution, size, format — never invented) → **Download**.
   - **Link only** (YouTube, TikTok, Reddit video…) → preview + **Open in app** + the platform's own offline/export options.
   - **Connect account** (Vimeo, Instagram, Facebook, Pinterest) → OAuth to save *your own* media.
   - **Export only** (dating apps) → how to request your own data.
3. The phone downloads the file **directly from the source** (the server never touches media bytes), verifies its real type by magic bytes, then saves it to Photos, a chosen folder (Android) or keeps it in-app.

Tabs: **Home · Downloads · Gallery · History · Settings**. Downloads supports queue, concurrency limit (1–5), pause/resume (when the source supports range requests), cancel, retry with backoff, duplicate detection, storage checks, search/filter/sort and the native share sheet. Gallery, History and playback work offline.

## Repository layout

```
backend/                 FastAPI service
  app/platforms/         one adapter per platform + capability registry
  app/security/          SSRF guard, pinned-IP HTTP client, MIME sniffing, rate limit, crypto
  app/api/               routes: media, downloads, auth/account, connections
  alembic/               migrations (0001_initial)
  tests/                 pytest suite (all upstreams mocked — see conftest.py)
mobile/                  Expo app
  app/                   screens (Expo Router)
  src/downloads/         DownloadManager + pure, unit-tested logic
  src/lib/               URL, formatting, file-signature, file-name helpers
  src/api/               typed API client
  __tests__/             jest suite
docs/                    feasibility, architecture, API, deployment, builds, store checklists,
                         privacy policy & terms templates, troubleshooting, status
docker-compose.yml       Postgres + migrate + API for local dev
```

## Quick start (local)

**Backend**
```bash
cd backend
cp .env.example .env            # set TOKEN_ENCRYPTION_KEY (command inside the file)
docker compose -f ../docker-compose.yml up --build
# API: http://localhost:8000  ·  docs: http://localhost:8000/docs
```
Without Docker: `pip install -r requirements-dev.txt`, start Postgres, `alembic upgrade head`, then
`uvicorn app.main:create_app --factory --reload`.

**Mobile**
```bash
cd mobile
npm install
EXPO_PUBLIC_API_URL=http://<your-LAN-IP>:8000 npx expo start
```
Expo Go can run most screens, but **use a development build** for the full feature set (background downloads, media library, secure store): `npx expo run:android` / `npx expo run:ios`, or `eas build --profile development`.

**Tests**
```bash
cd backend && python -m pytest -q          # 147 tests
cd mobile && npx tsc --noEmit && npx jest  # strict types + 50 tests
```

## Documentation

| Doc | Contents |
|---|---|
| [FEASIBILITY.md](docs/FEASIBILITY.md) | Stage 1: platform-by-platform policy & API findings |
| [ARCHITECTURE.md](docs/ARCHITECTURE.md) | System design, data flow, schema, security model, screen map |
| [API.md](docs/API.md) | Endpoint reference (+ `openapi.json`) |
| [DEPLOYMENT.md](docs/DEPLOYMENT.md) | Production backend: TLS, secrets, migrations, egress controls, scaling |
| [MOBILE_BUILDS.md](docs/MOBILE_BUILDS.md) | Android APK/AAB and iOS build & signing with EAS |
| [STORE_CHECKLISTS.md](docs/STORE_CHECKLISTS.md) | Google Play & App Store submission checklists |
| [PRIVACY_POLICY.md](docs/PRIVACY_POLICY.md) · [TERMS.md](docs/TERMS.md) | Templates to adapt with your lawyer |
| [TESTING.md](docs/TESTING.md) | Automated suites + device, accessibility and live-integration test plans |
| [TROUBLESHOOTING.md](docs/TROUBLESHOOTING.md) | Common problems and fixes |
| [STATUS.md](docs/STATUS.md) | Stage-by-stage report: files, status, tests, blockers |

## Legal note
MediaFlow Pro only retrieves media through official APIs, user-authorized connections, or plainly downloadable public files. It does not bypass DRM, logins, private accounts, expiring access controls or anti-bot measures. Operators remain responsible for complying with each platform's developer terms and local law; the X and Reddit integrations ship **disabled** until the operator supplies credentials and opts in.
