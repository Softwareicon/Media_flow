# Backend deployment

## 1. Requirements
- A container host (Fly.io, Render, Railway, ECS, Cloud Run, Kubernetes, a VM…)
- PostgreSQL 15+ (managed recommended), with automated backups
- A domain + TLS certificate (terminated at your load balancer / reverse proxy)

## 2. Secrets & configuration
Copy `backend/.env.example`; set in your host's secret manager (never commit):

| Variable | Production value |
|---|---|
| `ENVIRONMENT` | `production` |
| `DATABASE_URL` | `postgresql+asyncpg://user:pass@host:5432/db?ssl=require` |
| `PUBLIC_BASE_URL` | `https://api.yourdomain.com` |
| `REQUIRE_HTTPS` | `true` |
| `FORWARDED_ALLOW_IPS` | your reverse proxy's address range |
| `TOKEN_ENCRYPTION_KEY` | `python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"` |
| platform credentials | only for platforms you've been approved for |

The app **refuses to start** in production without an encryption key, `REQUIRE_HTTPS=true` and an https `PUBLIC_BASE_URL`.

Rotating `TOKEN_ENCRYPTION_KEY` makes stored OAuth tokens unreadable; users simply reconnect. (For seamless rotation, switch `TokenCipher` to `MultiFernet`.)

## 3. Build, migrate, run
```bash
docker build -t mediaflow-api ./backend
# one-off migration job before each release
docker run --rm --env-file prod.env mediaflow-api alembic upgrade head
# service
docker run -d --env-file prod.env -p 8000:8000 mediaflow-api
```
Health check: `GET /api/v1/health`.

The image runs as a non-root user, one uvicorn worker per container. Scale horizontally with more containers, then:

- **Rate limiting:** the in-memory limiter is per process. With >1 replica, replace `MemoryBackend` in `app/security/ratelimit.py` with a Redis implementation (`INCR` + `EXPIRE` per window key) or enforce limits at the gateway.
- **Retention job:** every replica runs the purge loop; it is idempotent. Alternatively disable it (`run_background=False`) and run `purge_expired` from a scheduled job.

## 4. Reverse proxy / TLS
Terminate TLS at the proxy, forward `X-Forwarded-For` and `X-Forwarded-Proto`. Uvicorn runs with `--proxy-headers` and trusts those headers **only** from the addresses in `FORWARDED_ALLOW_IPS` (image default `127.0.0.1`). Set it to your proxy / load-balancer address range, e.g. `FORWARDED_ALLOW_IPS=10.0.0.0/8`. Never use `*` on a publicly reachable container: anyone could spoof their IP (bypassing rate limits) or claim HTTPS. Example Caddy:
```
api.yourdomain.com {
  reverse_proxy api:8000
}
```

## 5. Network egress controls (defence in depth for SSRF)
The application already pins connections to vetted public IPs, but also block at the network layer:
- deny egress to RFC 1918, 100.64.0.0/10, 169.254.0.0/16, `fd00::/8`, link-local and your VPC CIDRs
- on AWS require IMDSv2 with hop limit 1 (or block 169.254.169.254 from the task); on GCP block `metadata.google.internal`
- Kubernetes example:
```yaml
apiVersion: networking.k8s.io/v1
kind: NetworkPolicy
metadata: { name: mediaflow-egress }
spec:
  podSelector: { matchLabels: { app: mediaflow-api } }
  policyTypes: [Egress]
  egress:
    - to: [{ podSelector: { matchLabels: { app: postgres } } }]
      ports: [{ port: 5432 }]
    - to: [{ namespaceSelector: {}, podSelector: { matchLabels: { k8s-app: kube-dns } } }]
      ports: [{ port: 53, protocol: UDP }]
    - to:
        - ipBlock:
            cidr: 0.0.0.0/0
            except: [10.0.0.0/8, 172.16.0.0/12, 192.168.0.0/16, 100.64.0.0/10, 169.254.0.0/16]
      ports: [{ port: 443 }, { port: 80 }]
```
- Do **not** route the API's outbound traffic through a generic forward proxy unless that proxy enforces the same deny list — the proxy would resolve DNS itself and bypass IP pinning. The HTTP client deliberately ignores `HTTP(S)_PROXY` env vars.

## 6. Platform developer apps
For each platform you enable, register the redirect URI `https://api.yourdomain.com/api/v1/connections/<platform>/callback` and complete that platform's review:

| Platform | Console | Notes |
|---|---|---|
| Vimeo | developer.vimeo.com | request `video_files` scope; users need Standard plan+ |
| Instagram | developers.facebook.com → Instagram API with Instagram Login | app review for `instagram_business_basic`; Business/Creator accounts only |
| Facebook | developers.facebook.com | app review for Page permissions; verify which permission returns `source` for your use case |
| Pinterest | developers.pinterest.com | trial → standard access review |
| Reddit | reddit.com/prefs/apps + Data API access request | approval required; commercial use needs a contract |
| X | console.x.com | pay-per-use credits; set `X_MEDIA_DOWNLOADS_ENABLED=true` only after legal review |
| YouTube (optional) | console.cloud.google.com | Data API key only adds durations to previews |

## 7. Observability
Logs go to stdout (no URLs with tokens are logged; adapters log platform + error code only). Add your APM of choice via uvicorn middleware. Alert on: health `degraded`, 5xx rate, 429 spikes, `oauth_exchange_failed` counts.

## 8. Backups & data deletion
Postgres holds no media. Account deletion is a hard delete across all tables; make sure backup retention matches the period promised in your privacy policy (template says 30 days).
