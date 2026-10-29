from __future__ import annotations

import asyncio
import contextlib
import logging
from collections.abc import AsyncIterator

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy import text

from . import __version__
from .api import auth, connections, downloads, media
from .config import Settings, get_settings
from .db import get_engine, init_engine, sessionmaker
from .platforms import UnsupportedLink
from .security.http_client import SafeHttpClient
from .security.netguard import UnsafeURLError
from .services import retention_loop

log = logging.getLogger("mediaflow")


def create_app(settings: Settings | None = None, *, http: SafeHttpClient | None = None,
               run_background: bool = True) -> FastAPI:
    settings = settings or get_settings()
    if settings.is_production:
        problems = []
        if not settings.token_encryption_key:
            problems.append("TOKEN_ENCRYPTION_KEY")
        if not settings.require_https:
            problems.append("REQUIRE_HTTPS=true")
        if not settings.public_base_url.startswith("https://"):
            problems.append("PUBLIC_BASE_URL (https)")
        if problems:
            raise RuntimeError(f"Refusing to start in production; set: {', '.join(problems)}")

    @contextlib.asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        engine = init_engine(settings.database_url)
        if settings.auto_create_tables:
            from . import models  # noqa: F401  (register tables)
            from .db import Base
            async with engine.begin() as conn:
                await conn.run_sync(Base.metadata.create_all)
        app.state.http = http or SafeHttpClient(allowed_ports=settings.allowed_ports,
                                                timeout=settings.http_timeout_seconds,
                                                max_redirects=settings.max_redirects)
        task = asyncio.create_task(retention_loop(sessionmaker(), settings)) if run_background else None
        yield
        if task:
            task.cancel()
        await app.state.http.aclose()
        await get_engine().dispose()

    app = FastAPI(title="MediaFlow Pro API", version=__version__, lifespan=lifespan,
                  docs_url=None if settings.is_production else "/docs",
                  redoc_url=None if settings.is_production else "/redoc")
    if settings.cors_origins:
        app.add_middleware(CORSMiddleware, allow_origins=settings.cors_origins, allow_methods=["*"],
                           allow_headers=["Authorization", "Content-Type"])

    @app.middleware("http")
    async def security(request: Request, call_next):
        if settings.require_https and request.url.scheme != "https" and request.url.path != "/api/v1/health":
            return JSONResponse({"code": "https_required", "message": "Use HTTPS."}, status_code=403)
        cl = request.headers.get("content-length") or "0"
        if not cl.isdigit() or int(cl) > 64 * 1024:
            return JSONResponse({"code": "payload_too_large", "message": "Request body too large."}, status_code=413)
        resp = await call_next(request)
        resp.headers["X-Content-Type-Options"] = "nosniff"
        resp.headers["Referrer-Policy"] = "no-referrer"
        resp.headers["Cache-Control"] = "no-store"
        resp.headers["X-Frame-Options"] = "DENY"
        if settings.require_https:
            resp.headers["Strict-Transport-Security"] = "max-age=63072000; includeSubDomains"
        return resp

    @app.exception_handler(UnsafeURLError)
    async def _unsafe(_: Request, exc: UnsafeURLError):
        return JSONResponse({"code": exc.code, "message": str(exc)}, status_code=422)

    @app.exception_handler(UnsupportedLink)
    async def _unsupported(_: Request, exc: UnsupportedLink):
        return JSONResponse({"code": "unsupported_link", "message": str(exc)}, status_code=422)

    @app.exception_handler(RequestValidationError)
    async def _validation(_: Request, exc: RequestValidationError):
        first = exc.errors()[0] if exc.errors() else {}
        field = ".".join(str(x) for x in first.get("loc", [])[1:]) or "request"
        return JSONResponse({"code": "invalid_request", "message": f"Invalid {field}: {first.get('msg', 'bad value')}"},
                            status_code=422)

    from fastapi import HTTPException

    @app.exception_handler(HTTPException)
    async def _http(_: Request, exc: HTTPException):
        body = exc.detail if isinstance(exc.detail, dict) else {"code": "error", "message": str(exc.detail)}
        return JSONResponse(body, status_code=exc.status_code, headers=getattr(exc, "headers", None))

    @app.get("/api/v1/health", tags=["health"])
    async def health() -> dict:
        db_ok = True
        try:
            async with get_engine().connect() as conn:
                await conn.execute(text("SELECT 1"))
        except Exception:
            db_ok = False
        return {"status": "ok" if db_ok else "degraded", "version": __version__, "database": db_ok}

    for r in (media.router, downloads.router, auth.router, connections.router):
        app.include_router(r, prefix="/api/v1")
    return app

