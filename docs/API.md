# API reference — v1

Base: `https://<your-api-host>/api/v1` · JSON in/out · machine-readable spec: [`openapi.json`](openapi.json) (interactive docs at `/docs` in non-production environments).

**Auth:** `Authorization: Bearer <token>`. Every install gets a token from `POST /auth/anonymous`; registering upgrades that principal in place.

**Errors:** always `{"code": "<machine_code>", "message": "<human text>"}`.

| HTTP | Typical codes |
|---|---|
| 401 | `unauthorized`, `invalid_credentials` |
| 403 | `connection_not_verified`, `https_required` |
| 404 | `not_found`, `analysis_not_found`, `option_not_found` |
| 409 | `already_finished`, `email_taken`, `already_registered` |
| 410 | `analysis_expired`, `media_link_expired` → analyze again |
| 413 | `too_large`, `payload_too_large` |
| 422 | `invalid_request`, `invalid_url`, `scheme_not_allowed`, `credentials_in_url`, `port_not_allowed`, `host_not_allowed`, `private_address`, `dns_failure`, `unsupported_link` |
| 429 | `rate_limited` (+ `Retry-After` header) |
| 503 | `not_configured` |

## Media

### `POST /media/analyze`
```json
{ "url": "https://example.com/clip.mp4" }
```
Response (`AnalyzeResponse`):
```json
{
  "analysis_id": "6a0c…",          // null unless status = downloadable
  "source_url": "https://example.com/clip.mp4",
  "platform": "web", "platform_name": "Websites (direct media)",
  "status": "downloadable",          // downloadable | link_only | needs_connection | not_configured | export_only | unavailable
  "title": "clip", "author": null, "thumbnail_url": null, "duration_seconds": null,
  "media_type": "video",
  "options": [{
    "id": "f0", "kind": "video", "label": "Original · MP4", "quality_label": "Original",
    "width": null, "height": null, "bitrate": null, "mime_type": "video/mp4", "extension": "mp4",
    "size_bytes": 5242880, "size_is_estimate": false, "has_audio": null, "is_original": true, "note": null
  }],
  "best_option_id": "f0",
  "explanation": null,               // why, when not downloadable
  "official_url": "https://example.com/clip.mp4",
  "alternatives": [],                // official offline/export routes
  "expires_at": "2026-10-29T07:15:00Z"
}
```
`width`/`height`/`size_bytes` are `null` when the source doesn't report them — they are never guessed. `size_is_estimate: true` marks bitrate×duration estimates.

### `GET /platforms`
Capability registry: per platform `capabilities{official_download, api_access, user_authorized_export, direct_media_urls}`, `download_mode`, `configured`, `requires_connection`, `connected` (for the caller), `summary`, `limitations`, `alternatives`. Auth optional.

## Downloads

| Method & path | Body | Returns |
|---|---|---|
| `POST /downloads` | `{analysis_id, option_id}` | `201 DownloadTicket` — `{download, media_url, request_headers, url_expires_at, max_bytes}` |
| `GET /downloads` | query: `status`, `platform`, `q`, `limit` (≤100), `cursor` | `{items[], next_cursor}` newest first |
| `GET /downloads/{id}` | — | `Download` |
| `PATCH /downloads/{id}` | `{status: in_progress\|completed\|failed, received_bytes?, error_code?}` | `Download` |
| `POST /downloads/{id}/cancel` | — | `Download` (`409` if already finished) |
| `DELETE /downloads/{id}` | — | `204` |

`media_url` is returned only to the owner of the analysis, and only until that analysis expires (15 min); calling again (e.g. on retry) creates a new record. When the account has `keep_server_history = false`, records are deleted as soon as the app reports a final status (completed / failed / cancelled). Records that never get a final status (e.g. the app was killed mid-download) are purged after 30 days like everything else.

## Auth & account

| Method & path | Notes |
|---|---|
| `POST /auth/anonymous` | `201 {token, user_id, is_anonymous, email, expires_at}` |
| `POST /auth/register` | `{email, password(≥10)}` — upgrades current anonymous user; rotates sessions |
| `POST /auth/login` | `{email, password}` |
| `POST /auth/logout` | revokes the current session |
| `GET /account` | `{user_id, email, is_anonymous, keep_server_history, connections[], created_at}` |
| `PATCH /account/settings` | `{keep_server_history}` — turning it off also deletes finished records |
| `DELETE /account/history` | deletes all download records and cached analyses |
| `DELETE /account` | deletes the account and **all** server data (sessions, tokens, records) |

## Connected accounts (OAuth)

| Method & path | Notes |
|---|---|
| `GET /connections` | `[{platform, configured, connected, username, expires_at}]` |
| `POST /connections/{platform}/start` | `{authorize_url, return_url, verifier}` — open `authorize_url` in an auth session; keep `verifier` in memory |
| `GET /connections/{platform}/callback` | provider redirect target; exchanges the code server-side and parks the token, then 302 → `mediaflow://connections?platform=…&status=pending&handoff=…` (or `denied` / `expired` / `error`) |
| `POST /connections/{platform}/complete` | `{handoff, verifier}` — must come from the same user that called `start`; only now is the connection saved. `403 connection_not_verified` otherwise |
| `DELETE /connections/{platform}` | deletes the stored token |

Why three steps: the token is attached only to the account whose app started the flow and holds the verifier, so an attacker who sends their own `authorize_url` to a victim can't capture the victim's account.

Platforms: `vimeo`, `instagram`, `facebook`, `pinterest`. Register `https://<api-host>/api/v1/connections/<platform>/callback` as the redirect URI in each developer console.

## Health
`GET /health` → `{status: ok|degraded, version, database}` (no auth; allowed over plain HTTP for load-balancer probes).
