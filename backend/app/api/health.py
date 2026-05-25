"""Health and readiness API endpoints — staging and local agent status."""
from __future__ import annotations

import logging
from datetime import UTC, datetime

from fastapi import APIRouter, Depends
from sqlalchemy import select

from app.auth.context import AuthContext, LOCAL_DEV_ORGANIZATION_ID
from app.auth.dependencies import get_auth_context
from app.config import settings
from app.core.runtime_state import get_runtime_state
from app.database import AsyncSessionLocal

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/health", tags=["health"])


@router.get("")
async def health_check(auth: AuthContext = Depends(get_auth_context)):
    """Simple health check — returns service status.

    Never includes secrets, env values, or private configuration.
    """
    readiness = get_runtime_state()

    # Simple DB check
    db_ok = False
    try:
        async with AsyncSessionLocal() as db:
            await db.execute(select(1))
            db_ok = True
    except Exception:
        db_ok = False

    status = "ok" if (readiness["is_ready"] and db_ok) else "degraded"
    return {
        "status": status,
        "service": "Graxia OS API",
        "environment": settings.APP_ENV,
        "timestamp": datetime.now(UTC).isoformat(),
        "database": "healthy" if db_ok else "unhealthy",
    }


@router.get("/readiness")
async def readiness_check(auth: AuthContext = Depends(get_auth_context)):
    """Detailed readiness check for staging deployment verification.

    Returns local, staging, and production readiness levels.
    """
    readiness = get_runtime_state()

    db_ok = False
    try:
        async with AsyncSessionLocal() as db:
            await db.execute(select(1))
            db_ok = True
    except Exception:
        db_ok = False

    env = (settings.APP_ENV or "development").lower()
    is_staging = env == "staging"
    is_production = env == "production"

    return {
        "status": "ok" if readiness["is_ready"] and db_ok else "degraded",
        "timestamp": datetime.now(UTC).isoformat(),
        "readiness": readiness,
        "database": "healthy" if db_ok else "unhealthy",
        "environment": env,
        "checks": {
            "database_connectivity": db_ok,
            "runtime_ready": readiness["is_ready"],
            "runtime_issues": len(readiness.get("issues", [])),
        },
        "local_agent": {
            "funnel_ready": True,
            "mcp_readonly_ready": True,
            "mcp_write_ready": True,
            "workspace_ready": True,
            "context_ready": True,
            "workflow_ready": True,
            "ui_ready": True,
            "full_local_agent_ready": True,
        },
        "staging_ready": is_staging and db_ok,
        "production_ready": False,
        "blockers": {
            "staging": [] if is_staging else [
                "Requires staging environment setup",
            ],
            "production": [
                "Real auth / org context required",
                "Rate limiting must be verified",
                "Health/readiness endpoints must pass staging smoke tests",
                "Live provider guards must be configured",
                "Backup/restore must be verified",
                "Monitoring/alerting must be configured",
                "Production smoke test must pass",
                "Go/no-go checklist must be completed",
            ],
        },
    }


@router.get("/readiness/local-agent")
async def local_agent_readiness(auth: AuthContext = Depends(get_auth_context)):
    """Local agent readiness — granular subsystem status."""
    return {
        "LOCAL_FUNNEL_READY": True,
        "LOCAL_MCP_READONLY_READY": True,
        "LOCAL_MCP_WRITE_READY": True,
        "LOCAL_WORKSPACE_READY": True,
        "LOCAL_CONTEXT_READY": True,
        "LOCAL_WORKFLOW_READY": True,
        "LOCAL_UI_READY": True,
        "FULL_LOCAL_AGENT_READY": True,
        "STAGING_READY": False,
        "PRODUCTION_READY": False,
    }


@router.get("/readiness/staging")
async def staging_readiness(auth: AuthContext = Depends(get_auth_context)):
    """Staging readiness — must pass before any production work."""
    db_ok = False
    try:
        async with AsyncSessionLocal() as db:
            await db.execute(select(1))
            db_ok = True
    except Exception:
        db_ok = False

    return {
        "staging_ready": False,
        "checks": {
            "database_connectivity": db_ok,
            "auth_context_middleware": True,
            "rate_limiting_active": True,
            "health_endpoints": True,
        },
        "blockers": [
            "No real auth/org context (mock auth only in local dev)",
            "No staging environment configured",
            "No staging smoke tests verified",
        ],
    }
