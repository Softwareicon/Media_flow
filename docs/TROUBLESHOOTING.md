# Troubleshooting

## App

| Symptom | Cause / fix |
|---|---|
| "Can't reach the MediaFlow server" | Check `EXPO_PUBLIC_API_URL` for that build profile. Emulator → `http://10.0.2.2:8000`; phone → your LAN IP, same Wi-Fi; firewall allows port 8000. |
| "This build is misconfigured: the API address must use HTTPS" | Release builds refuse `http://` API URLs. Use HTTPS or a development build. |
| Download button missing for YouTube / TikTok | By design — those platforms don't authorize third-party downloads. Use *Open in…* or the listed official options. |
| "Connect your account" never finishes | The provider redirect URI must be exactly `https://<api>/api/v1/connections/<platform>/callback`; `PUBLIC_BASE_URL` must match the public hostname; the app's scheme is `mediaflow`. |
| "Not available on this server" | That platform's credentials aren't configured (see `GET /platforms → configured`). |
| Download stuck at *Queued* | Concurrency limit reached, or *Wi-Fi only* is on while on mobile data. |
| Resume restarts from 0 | The source server doesn't support HTTP range requests. |
| Downloads stop when the app is closed on Android | Android may kill background apps; the item comes back queued and restarts. Disable battery optimisation for MediaFlow on aggressive OEM ROMs. |
| "The download link expired" | Platform links (e.g. Vimeo, 24 h) or analyses (15 min) expired. Tap Retry — the app re-analyzes automatically. |
| Saved to app, not Photos | Photo permission denied, or Photos rejected the format (e.g. WebM on iOS). Enable the permission in system Settings, or share the file to another app. |
| "The file wasn't a photo, video or audio file" | The site served an HTML/error page or another file type; it was deleted for safety. |
| Features missing in Expo Go | Use a development build (`eas build --profile development`). |

## Backend

| Symptom | Cause / fix |
|---|---|
| `RuntimeError: Refusing to start in production` | Set `TOKEN_ENCRYPTION_KEY`, `REQUIRE_HTTPS=true`, https `PUBLIC_BASE_URL`. |
| 403 `https_required` | TLS proxy not forwarding `X-Forwarded-Proto`, or the proxy isn't listed in `FORWARDED_ALLOW_IPS`. |
| 403 `connection_not_verified` | The connect flow was finished on a different device/account than it started on, or took longer than 5 minutes after approval. Start it again from the app. |
| Every analysis says `private_address` | Your DNS returns internal IPs (split-horizon DNS / corporate resolver). Use a public resolver for the API container. |
| 503 `not_configured` on Connect | Platform client ID/secret or `TOKEN_ENCRYPTION_KEY` missing. |
| OAuth returns `status=error` | Wrong client secret, redirect URI mismatch, or the platform app is still in review/sandbox. Check API logs for `oauth_exchange_failed`. |
| Reddit: "rejected this server's API credentials" | Client not approved for Data API access, or wrong user agent format. |
| 429 for everyone behind one proxy | `FORWARDED_ALLOW_IPS` doesn't include your proxy, so all clients share the proxy IP. |
| Rate limits inconsistent across replicas | In-memory limiter is per process; move it to Redis (see DEPLOYMENT.md). |
| `asyncpg` SSL errors | Add `?ssl=require` to `DATABASE_URL` for managed Postgres. |
| Alembic can't connect | It reads `DATABASE_URL` from the environment / `.env` in `backend/`. |
