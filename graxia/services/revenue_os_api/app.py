"""
graxia/services/revenue_os_api/app.py
FastAPI application factory — Revenue OS API.

Key design decisions:
  - create_app() factory pattern for clean testing (not a module-level singleton call)
  - Middleware in correct LIFO insertion order (last added = outermost = first executed)
  - Lifespan validates DB on startup — uvicorn refuses to serve if DB is unreachable
  - All imports at module level — no inner-function imports that hide failures
  - OpenAPI docs disabled in production
  - Structured 422/500 error handlers with X-Request-ID correlation
"""
from __future__ import annotations

import logging
import os
from contextlib import asynccontextmanager
from typing import AsyncIterator

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

# ── Module-level imports (not inside lifespan/functions) ─────────────────────
from graxia.packages.revenue_os.db import DATABASE_URL, get_db_session
from .middleware import RateLimitMiddleware, SecurityHeadersMiddleware
from .router import api_router

logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────────────────────────────────────
# Lifespan
# ─────────────────────────────────────────────────────────────────────────────

@asynccontextmanager
async def _lifespan(app: FastAPI) -> AsyncIterator[None]:
    """
    Startup: verify DB is reachable. Failure raises → uvicorn won't accept traffic.
    Shutdown: log for ops visibility.
    """
    env = os.getenv("APP_ENV", "development")
    logger.info("Revenue OS API starting | env=%s", env)

    # Mask credentials in log — show only host/db portion
    safe_url = DATABASE_URL.split("@")[-1] if "@" in DATABASE_URL else "configured"
    try:
        async with get_db_session() as db:
            await db.execute(text("SELECT 1"))
        logger.info("DB reachable: %s", safe_url)
    except SQLAlchemyError as exc:
        logger.critical("DB unreachable at startup: %s", exc)
        raise  # uvicorn will exit non-zero — Kubernetes pod restarts

    logger.info("Revenue OS API ready to serve")
    yield
    logger.info("Revenue OS API shutdown complete")


# ─────────────────────────────────────────────────────────────────────────────
# Application factory
# ─────────────────────────────────────────────────────────────────────────────

def create_app() -> FastAPI:
    env = os.getenv("APP_ENV", "development")
    is_prod = env == "production"

    app = FastAPI(
        title="Graxia Revenue OS API",
        description=(
            "Enterprise Revenue Automation API — orders, ledger, campaigns, "
            "leads, approvals, incidents, email delivery, and CEO dashboard."
        ),
        version="1.0.0",
        # Disable OpenAPI in production to reduce attack surface
        docs_url=None if is_prod else "/docs",
        redoc_url=None if is_prod else "/redoc",
        openapi_url=None if is_prod else "/openapi.json",
        lifespan=_lifespan,
    )

    # ── Middleware: LIFO insertion order ──────────────────────────────────
    # Execution order when a request arrives: CORS → RateLimit → SecurityHeaders → Router
    # We add in reverse: SecurityHeaders first, then RateLimit, then CORS (outermost)

    # 3. Security headers (innermost after rate limit passes)
    app.add_middleware(SecurityHeadersMiddleware)

    # 2. Rate limiter
    app.add_middleware(
        RateLimitMiddleware,
        requests_per_minute=int(os.getenv("RATE_LIMIT_RPM", "60")),
        burst=int(os.getenv("RATE_LIMIT_BURST", "20")),
    )

    # 1. CORS (outermost — handles OPTIONS pre-flight before any auth check)
    cors_origins = [
        o.strip()
        for o in os.getenv("ALLOWED_ORIGINS", "http://localhost:3000").split(",")
        if o.strip()
    ]
    app.add_middleware(
        CORSMiddleware,
        allow_origins=cors_origins,
        allow_credentials=True,
        allow_methods=["GET", "POST", "PATCH", "PUT", "DELETE", "OPTIONS"],
        allow_headers=["*"],
    )

    # ── Routers ────────────────────────────────────────────────────────────
    app.include_router(api_router)

    # ── Global exception handlers ──────────────────────────────────────────

    @app.exception_handler(RequestValidationError)
    async def _validation_error_handler(
        request: Request, exc: RequestValidationError
    ) -> JSONResponse:
        """Structured 422 with field-level error details."""
        errors = [
            {
                "field": " > ".join(str(loc) for loc in err["loc"]),
                "message": err["msg"],
                "type": err["type"],
            }
            for err in exc.errors()
        ]
        return JSONResponse(
            status_code=422,
            content={"detail": "Request validation failed", "errors": errors},
        )

    @app.exception_handler(Exception)
    async def _unhandled_exception_handler(
        request: Request, exc: Exception
    ) -> JSONResponse:
        """Catch-all 500 — log full traceback, return safe response to client."""
        request_id = getattr(request.state, "request_id", "unknown")
        logger.error(
            "Unhandled exception | request_id=%s method=%s path=%s: %s",
            request_id, request.method, request.url.path, exc,
            exc_info=True,
        )
        return JSONResponse(
            status_code=500,
            content={
                "detail": "An unexpected error occurred",
                "request_id": request_id,
            },
        )

    return app


# ── Module-level app instance for uvicorn ─────────────────────────────────────
# Run with: uvicorn graxia.services.revenue_os_api.app:app --reload
app = create_app()
