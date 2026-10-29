"""Sliding-window rate limiter.

The in-memory backend is correct for a single worker process. For multiple workers or
instances, swap `MemoryBackend` for a shared store (Redis INCR+EXPIRE) — see docs/DEPLOYMENT.md.
"""
from __future__ import annotations

import time
from collections import defaultdict, deque

from fastapi import HTTPException, Request


class MemoryBackend:
    def __init__(self) -> None:
        self._hits: dict[str, deque[float]] = defaultdict(deque)

    def hit(self, key: str, limit: int, window: float, now: float | None = None) -> tuple[bool, int, float]:
        now = time.monotonic() if now is None else now
        q = self._hits[key]
        while q and q[0] <= now - window:
            q.popleft()
        if len(q) >= limit:
            retry = window - (now - q[0])
            return False, 0, max(retry, 0.0)
        q.append(now)
        if len(self._hits) > 50_000:  # bound memory under key-spraying
            for k in [k for k, v in self._hits.items() if not v][:10_000]:
                del self._hits[k]
        return True, limit - len(q), 0.0

    def reset(self) -> None:
        self._hits.clear()


backend = MemoryBackend()


def client_ip(request: Request) -> str:
    # Behind a proxy, run uvicorn with --proxy-headers --forwarded-allow-ips=<proxy ip>
    # so request.client is the real caller; never trust X-Forwarded-For directly here.
    return request.client.host if request.client else "unknown"


def enforce(request: Request, bucket: str, principal: str | None, limit: int, window: float = 60.0) -> None:
    for key in {f"{bucket}:ip:{client_ip(request)}", f"{bucket}:p:{principal}" if principal else None} - {None}:
        ok, _remaining, retry = backend.hit(key, limit, window)  # type: ignore[arg-type]
        if not ok:
            raise HTTPException(
                status_code=429,
                detail={"code": "rate_limited", "message": "Too many requests. Please wait and try again."},
                headers={"Retry-After": str(int(retry) + 1)},
            )
