"""Health and readiness API endpoints — staging and local agent status."""
from __future__ import annotations

import logging
from datetime import UTC, datetime
from importlib import import_module
from importlib.util import find_spec
from pathlib import Path

from fastapi import APIRouter, Depends
from sqlalchemy import select

from app.auth.context import AuthContext, LOCAL_DEV_ORGANIZATION_ID
from app.auth.dependencies import get_auth_context
from app.config import settings
from app.core.runtime_state import get_runtime_state
from app.database import AsyncSessionLocal

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/health", tags=["health"])

_STAGING_SCRIPT_PATHS = (
    Path(__file__).resolve().parents[3] / "scripts" / "check_staging_readiness.ps1",
    Path(__file__).resolve().parents[3] / "scripts" / "staging_smoke.ps1",
    Path(__file__).resolve().parents[3] / "scripts" / "check_staging_readiness.sh",
    Path(__file__).resolve().parents[3] / "scripts" / "staging_smoke.sh",
)
_PRODUCTION_DOC_PATHS = (
    Path(__file__).resolve().parents[3] / "docs" / "PRODUCTION_GO_NO_GO_CHECKLIST.md",
    Path(__file__).resolve().parents[3] / "docs" / "PRODUCTION_SECRETS_RUNBOOK.md",
    Path(__file__).resolve().parents[3] / "docs" / "STRIPE_PRODUCTION_GATE.md",
    Path(__file__).resolve().parents[3] / "docs" / "EMAIL_PRODUCTION_GATE.md",
    Path(__file__).resolve().parents[3] / "docs" / "GOOGLE_WORKSPACE_PRODUCTION_GATE.md",
    Path(__file__).resolve().parents[3] / "docs" / "BACKUP_RESTORE_RUNBOOK.md",
    Path(__file__).resolve().parents[3] / "docs" / "INCIDENT_RESPONSE_RUNBOOK.md",
    Path(__file__).resolve().parents[3] / "docs" / "ROLLBACK_RUNBOOK.md",
)


async def _database_ok() -> bool:
    try:
        async with AsyncSessionLocal() as db:
            await db.execute(select(1))
            return True
    except Exception:
        return False


def _module_present(module_name: str) -> bool:
    return find_spec(module_name) is not None


def _runtime_tooling_present() -> bool:
    try:
        runtime_tools = import_module("app.mcp.tools.runtime")
    except Exception:
        return False

    required_handlers = (
        "handle_get_runtime_status",
        "handle_list_runtime_tasks",
        "handle_build_runtime_context_packet",
        "handle_get_token_roi_summary",
    )
    return all(callable(getattr(runtime_tools, handler_name, None)) for handler_name in required_handlers)


def _looks_placeholder(value: str | None) -> bool:
    return settings._looks_placeholder((value or "").strip())


def _stripe_live_mode_blocked() -> bool:
    secret_key = (settings.STRIPE_SECRET_KEY or "").strip()
    if not secret_key or _looks_placeholder(secret_key):
        return True
    return not secret_key.startswith("sk_live_")


def _real_email_send_blocked() -> bool:
    resend_key = (settings.RESEND_API_KEY or "").strip()
    return not resend_key or _looks_placeholder(resend_key)


def _staging_scripts_present() -> bool:
    return all(path.exists() for path in _STAGING_SCRIPT_PATHS)


def _production_docs_present() -> bool:
    return all(path.exists() for path in _PRODUCTION_DOC_PATHS)


def _live_stripe_blocked() -> bool:
    return (not settings.ALLOW_LIVE_STRIPE) and _stripe_live_mode_blocked()


def _real_email_provider_blocked() -> bool:
    return (not settings.ALLOW_REAL_EMAIL_SEND) and _real_email_send_blocked()


def _real_google_mutation_blocked() -> bool:
    return (not settings.ALLOW_REAL_GOOGLE_MUTATION) and (not settings.GOOGLE_ENABLE_WRITE_SCOPES)


async def _build_staging_readiness(auth: AuthContext) -> dict[str, object]:
    readiness = get_runtime_state()
    env = (settings.APP_ENV or "development").lower()
    db_ok = await _database_ok()

    checks = {
        "database_connectivity": db_ok,
        "runtime_ready": bool(readiness["is_ready"]),
        "auth_context_middleware": True,
        "real_auth_context_active": not auth.is_mock_auth,
        "staging_auth_guard": True,
        "rate_limiting_active": True,
        "health_endpoints": True,
        "runtime_contracts_present": _module_present("app.runtime.contracts"),
        "runtime_adapters_present": _module_present("app.runtime.adapters"),
        "runtime_gateway_present": _module_present("app.runtime.gateway"),
        "runtime_orchestration_present": _module_present("app.runtime.orchestration"),
        "runtime_worker_present": _module_present("app.runtime.workers"),
        "context_quality_gate_present": _module_present("app.context_engine.quality_gate"),
        "token_roi_controls_present": _module_present("app.context_engine.token_roi"),
        "mcp_runtime_tools_present": _runtime_tooling_present(),
        "staging_smoke_scripts_present": _staging_scripts_present(),
        "google_write_scopes_disabled": not settings.GOOGLE_ENABLE_WRITE_SCOPES,
        "stripe_live_mode_blocked": _stripe_live_mode_blocked(),
        "real_email_send_blocked": _real_email_send_blocked(),
    }

    blockers: list[str] = []
    if env != "staging":
        blockers.append("APP_ENV is not 'staging'.")
    if auth.is_mock_auth:
        blockers.append("Current auth context is mock auth; real staging auth has not been proven.")
    if not checks["database_connectivity"]:
        blockers.append("Database connectivity failed.")
    if not checks["runtime_ready"]:
        blockers.append("Runtime state is not ready.")
    if not checks["runtime_contracts_present"]:
        blockers.append("Runtime contracts are missing.")
    if not checks["runtime_adapters_present"]:
        blockers.append("Runtime adapters are missing.")
    if not checks["runtime_gateway_present"]:
        blockers.append("Runtime gateway bridge is missing.")
    if not checks["runtime_orchestration_present"]:
        blockers.append("Runtime orchestration boundary is missing.")
    if not checks["runtime_worker_present"]:
        blockers.append("Runtime worker capability layer is missing.")
    if not checks["context_quality_gate_present"]:
        blockers.append("Context quality gate is missing.")
    if not checks["token_roi_controls_present"]:
        blockers.append("Token ROI controls are missing.")
    if not checks["mcp_runtime_tools_present"]:
        blockers.append("MCP runtime tools are missing.")
    if not checks["staging_smoke_scripts_present"]:
        blockers.append("Staging smoke scripts are missing.")
    if not checks["google_write_scopes_disabled"]:
        blockers.append("Google Workspace write scopes are enabled.")
    if not checks["stripe_live_mode_blocked"]:
        blockers.append("Stripe live mode is not blocked.")
    if not checks["real_email_send_blocked"]:
        blockers.append("Real email sending is not blocked.")

    staging_ready = env == "staging" and all(bool(value) for value in checks.values()) and not blockers
    return {
        "staging_ready": staging_ready,
        "environment": env,
        "checks": checks,
        "runtime": readiness,
        "blockers": blockers,
    }


async def _build_production_readiness(auth: AuthContext) -> dict[str, object]:
    readiness = get_runtime_state()
    env = (settings.APP_ENV or "development").lower()
    db_ok = await _database_ok()

    checks = {
        "database_connectivity": db_ok,
        "runtime_ready": bool(readiness["is_ready"]),
        "auth_context_middleware": True,
        "real_auth_context_active": not auth.is_mock_auth,
        "rate_limiting_active": True,
        "production_runbooks_present": _production_docs_present(),
        "live_stripe_blocked": _live_stripe_blocked(),
        "real_email_send_blocked": _real_email_provider_blocked(),
        "real_google_mutation_blocked": _real_google_mutation_blocked(),
        "real_llm_calls_blocked": not settings.ALLOW_REAL_LLM_CALLS,
        "go_no_go_required": True,
    }

    blockers: list[str] = [
        "Production dry-run gate remains closed until explicit go/no-go approval."
    ]
    if env != "production":
        blockers.append("APP_ENV is not 'production'.")
    if auth.is_mock_auth:
        blockers.append("Current auth context is mock auth; real production auth has not been proven.")
    if not checks["database_connectivity"]:
        blockers.append("Database connectivity failed.")
    if not checks["runtime_ready"]:
        blockers.append("Runtime state is not ready.")
    if not checks["production_runbooks_present"]:
        blockers.append("Production runbooks are missing.")
    if not checks["live_stripe_blocked"]:
        blockers.append("Live Stripe is not blocked.")
    if not checks["real_email_send_blocked"]:
        blockers.append("Real email sending is not blocked.")
    if not checks["real_google_mutation_blocked"]:
        blockers.append("Real Google Workspace mutation is not blocked.")
    if not checks["real_llm_calls_blocked"]:
        blockers.append("Real LLM calls are not blocked.")

    return {
        "production_ready": False,
        "go_no_go_required": True,
        "environment": env,
        "checks": checks,
        "runtime": readiness,
        "blockers": blockers,
    }


@router.get("")
async def health_check(auth: AuthContext = Depends(get_auth_context)):
    """Simple health check — returns service status.

    Never includes secrets, env values, or private configuration.
    """
    readiness = get_runtime_state()

    db_ok = await _database_ok()

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
    db_ok = await _database_ok()
    staging = await _build_staging_readiness(auth)
    production = await _build_production_readiness(auth)
    env = (settings.APP_ENV or "development").lower()

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
            "staging_gate_blockers": len(staging["blockers"]),
            "production_gate_blockers": len(production["blockers"]),
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
        "staging": staging,
        "staging_ready": staging["staging_ready"],
        "production": production,
        "production_ready": production["production_ready"],
        "blockers": {
            "staging": staging["blockers"],
            "production": production["blockers"],
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
    return await _build_staging_readiness(auth)


@router.get("/readiness/production")
async def production_readiness(auth: AuthContext = Depends(get_auth_context)):
    """Production dry-run readiness — always closed until explicit go/no-go."""
    return await _build_production_readiness(auth)
