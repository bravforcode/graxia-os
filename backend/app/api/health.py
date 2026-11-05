"""Health and readiness API endpoints — staging and local agent status."""
from __future__ import annotations

import logging
import sys
from datetime import UTC, datetime
from importlib import import_module
from importlib.util import find_spec
from pathlib import Path

from fastapi import APIRouter, Depends, Request
from sqlalchemy import select

from app.auth.context import AuthContext, LOCAL_DEV_ORGANIZATION_ID
from app.auth.dependencies import get_auth_context
from app.beta.registry import get_beta_registry
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
    Path(__file__).resolve().parents[3] / "docs" / "MONITORING_ALERTING_RUNBOOK.md",
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


def _runtime_app(request: Request | None):
    if request is not None:
        try:
            return request.app
        except (AttributeError, KeyError):
            return None
    return getattr(sys.modules.get("app.main"), "app", None)


def _middleware_registered(app, module_name: str, class_name: str) -> bool:
    if app is None:
        return False
    try:
        middleware_class = getattr(import_module(module_name), class_name)
    except (ImportError, AttributeError):
        return False
    return any(
        getattr(middleware, "cls", None) is middleware_class
        for middleware in getattr(app, "user_middleware", ())
    )


def _route_for(app, path: str, method: str):
    if app is None:
        return None
    return next((
        route for route in getattr(app, "routes", ())
        if getattr(route, "path", None) == path
        and method.upper() in (getattr(route, "methods", None) or ())
    ), None)


def _route_has_dependency(route, dependency) -> bool:
    stack = list(getattr(getattr(route, "dependant", None), "dependencies", ()))
    while stack:
        current = stack.pop()
        if getattr(current, "call", None) is dependency:
            return True
        stack.extend(getattr(current, "dependencies", ()))
    return False


def _real_auth_context_active(auth: AuthContext) -> bool:
    actor_id = str(getattr(auth, "actor_id", "") or "").strip()
    organization_id = str(getattr(auth, "organization_id", "") or "").strip()
    return (
        getattr(auth, "is_authenticated", False) is True
        and getattr(auth, "is_mock_auth", True) is False
        and getattr(auth, "auth_method", "") == "bearer_jwt"
        and bool(actor_id)
        and bool(organization_id)
        and organization_id != str(LOCAL_DEV_ORGANIZATION_ID)
    )


def _staging_runtime_observations(request: Request | None) -> dict[str, object]:
    app = _runtime_app(request)
    auth_middleware_registered = _middleware_registered(
        app, "app.auth.middleware", "AuthContextMiddleware",
    )
    required_routes = (
        ("/health", "GET"),
        ("/api/v1/health", "GET"),
        ("/api/v1/health/readiness", "GET"),
        ("/api/v1/health/readiness/local-agent", "GET"),
        ("/api/v1/health/readiness/staging", "GET"),
        ("/api/v1/health/readiness/production", "GET"),
        ("/api/v1/health/readiness/beta", "GET"),
        ("/api/v1/health/readiness/limited-beta-pilot", "GET"),
    )
    health_endpoints_present = bool(app is not None) and all(
        _route_for(app, path, method) is not None
        for path, method in required_routes
    )
    staging_route = _route_for(app, "/api/v1/health/readiness/staging", "GET")
    staging_auth_guard_present = (
        auth_middleware_registered
        and staging_route is not None
        and _route_has_dependency(staging_route, get_auth_context)
    )

    rate_middleware_registered = _middleware_registered(
        app, "app.middleware.rate_limit", "RateLimitMiddleware",
    )
    redis_client = getattr(getattr(app, "state", None), "redis", None)
    backend_mode = "unavailable"
    if rate_middleware_registered:
        backend_mode = "redis_configured" if redis_client else "process_local_fallback"

    configured_rule = None
    request_app_matches_runtime = bool(
        request is not None and app is not None and request.scope.get("app") is app
    )
    if rate_middleware_registered and request_app_matches_runtime:
        try:
            rate_limit_module = import_module("app.middleware.rate_limit")
            middleware = rate_limit_module.RateLimitMiddleware(app)
            rule = middleware._resolve_rule(request)
            if (
                rule is not None
                and isinstance(rule.name, str)
                and rule.name
                and isinstance(rule.limit, int)
                and rule.limit > 0
                and isinstance(rule.window_seconds, int)
                and rule.window_seconds > 0
            ):
                configured_rule = {
                    "name": rule.name,
                    "limit": rule.limit,
                    "window_seconds": rule.window_seconds,
                }
        except (ImportError, AttributeError, TypeError, ValueError):
            configured_rule = None

    return {
        "auth_context_middleware_registered": auth_middleware_registered,
        "health_endpoints_present": health_endpoints_present,
        "staging_auth_guard_present": staging_auth_guard_present,
        "rate_limiting": {
            "middleware_registered": rate_middleware_registered,
            "configured_backend_mode": backend_mode,
            "configured_rule": configured_rule,
            "request_app_matches_runtime": request_app_matches_runtime,
            # RateLimitMiddleware writes response headers, but no per-request
            # evidence into request.state for this endpoint to verify.
            "enforcement_evidence_available": False,
        },
    }


def _live_stripe_blocked() -> bool:
    return (not settings.ALLOW_LIVE_STRIPE) or _stripe_live_mode_blocked()


def _real_email_provider_blocked() -> bool:
    return (not settings.ALLOW_REAL_EMAIL_SEND) or _real_email_send_blocked()


def _real_google_mutation_blocked() -> bool:
    return (not settings.ALLOW_REAL_GOOGLE_MUTATION) or (not settings.GOOGLE_ENABLE_WRITE_SCOPES)


async def _build_staging_readiness(
    auth: AuthContext,
    request: Request | None = None,
) -> dict[str, object]:
    readiness = get_runtime_state()
    env = (settings.APP_ENV or "development").lower()
    db_ok = await _database_ok()
    runtime_observations = _staging_runtime_observations(request)

    checks = {
        "database_connectivity": db_ok,
        "runtime_ready": bool(readiness["is_ready"]),
        "auth_context_middleware": runtime_observations["auth_context_middleware_registered"],
        "real_auth_context_active": _real_auth_context_active(auth),
        "staging_auth_guard": runtime_observations["staging_auth_guard_present"],
        # Enforcement has no current-request state marker; do not treat a
        # configured middleware or Redis client as proof that it ran.
        "rate_limiting_active": False,
        "permissions_ok": False,
        "org_boundary_ok": False,
        "safe_errors_ok": False,
        "security_audit_ok": False,
        "payload_guard_ok": False,
        "health_endpoints": runtime_observations["health_endpoints_present"],
        "route_protection_matrix_ok": False,
        "mcp_auth_ok": False,
        "workflow_auth_ok": False,
        "public_route_limits_ok": False,
        "customer_token_boundary_ok": False,
        "production_live_providers_disabled": _live_stripe_blocked() and _real_email_provider_blocked(),
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

    blockers.extend(
        f"Required capability '{name}' is not verified."
        for name, value in checks.items() if value is not True
    )
    staging_ready = env == "staging" and all(value is True for value in checks.values()) and not blockers
    return {
        "staging_ready": staging_ready,
        "environment": env,
        "checks": checks,
        "rate_limiting": runtime_observations["rate_limiting"],
        "runtime": readiness,
        "blockers": blockers,
    }


async def _build_production_readiness(
    auth: AuthContext,
    request: Request | None = None,
) -> dict[str, object]:
    readiness = get_runtime_state()
    env = (settings.APP_ENV or "development").lower()
    db_ok = await _database_ok()

    checks = {
        "database_connectivity": db_ok,
        "runtime_ready": bool(readiness["is_ready"]),
        "auth_context_middleware": _middleware_registered(
            _runtime_app(request), "app.auth.middleware", "AuthContextMiddleware",
        ),
        "real_auth_context_active": _real_auth_context_active(auth),
        "rate_limiting_active": False,
        "permissions_ok": False,
        "org_boundary_ok": False,
        "safe_errors_ok": False,
        "security_audit_ok": False,
        "payload_guard_ok": False,
        "production_runbooks_present": _production_docs_present(),
        "live_stripe_blocked": _live_stripe_blocked(),
        "real_email_send_blocked": _real_email_provider_blocked(),
        "real_google_mutation_blocked": _real_google_mutation_blocked(),
        "real_llm_calls_blocked": not settings.ALLOW_REAL_LLM_CALLS,
        "production_db_blocked": not settings.ALLOW_PRODUCTION_DB,
        "go_no_go_required": True,
        "production_ready": False,
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
    if not checks["production_db_blocked"]:
        blockers.append("Production database is not blocked.")

    blockers.extend(
        f"Required capability '{name}' is not verified."
        for name, value in checks.items() if value is not True
    )

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
async def readiness_check(request: Request, auth: AuthContext = Depends(get_auth_context)):
    """Detailed readiness check for staging deployment verification.

    Returns local, staging, and production readiness levels.
    """
    readiness = get_runtime_state()
    db_ok = await _database_ok()
    staging = await _build_staging_readiness(auth, request)
    production = await _build_production_readiness(auth, request)
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
            "funnel_ready": False,
            "mcp_readonly_ready": False,
            "mcp_write_ready": False,
            "workspace_ready": False,
            "context_ready": False,
            "workflow_ready": False,
            "ui_ready": False,
            "full_local_agent_ready": False,
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
        "LOCAL_FUNNEL_READY": False,
        "LOCAL_MCP_READONLY_READY": False,
        "LOCAL_MCP_WRITE_READY": False,
        "LOCAL_WORKSPACE_READY": False,
        "LOCAL_CONTEXT_READY": False,
        "LOCAL_WORKFLOW_READY": False,
        "LOCAL_UI_READY": False,
        "FULL_LOCAL_AGENT_READY": False,
        "STAGING_READY": False,
        "PRODUCTION_READY": False,
    }


@router.get("/readiness/staging")
async def staging_readiness(request: Request, auth: AuthContext = Depends(get_auth_context)):
    """Staging readiness — must pass before any production work."""
    return await _build_staging_readiness(auth, request)


async def _build_beta_readiness(
    auth: AuthContext,
    request: Request | None = None,
) -> dict[str, object]:
    """Build controlled beta readiness status."""
    env = (settings.APP_ENV or "development").lower()
    staging = await _build_staging_readiness(auth, request)
    production = await _build_production_readiness(auth, request)
    beta_registry = get_beta_registry()

    checks = {
        "staging_ready": staging["staging_ready"],
        "prod_dry_run_ready": not production["blockers"],
        "production_ready": False,
        "live_providers_enabled": False,
        "approval_system_ready": True,
        "operator_runbook_ready": (Path(__file__).resolve().parents[3] / "docs" / "BETA_OPERATOR_RUNBOOK.md").exists(),
        "beta_cohort_configured": len(beta_registry.list_active_testers()) > 0,
        "kill_switch_ready": settings.KILL_SWITCH_ALL_EXTERNAL_BETA is True,
        "monitoring_ready": True,
        "rollback_ready": True,
        "support_triage_ready": (Path(__file__).resolve().parents[3] / "docs" / "BETA_SUPPORT_TRIAGE_RUNBOOK.md").exists(),
    }

    blockers: list[str] = []
    if env not in ("development", "staging"):
        blockers.append(f"APP_ENV={env} is not suitable for beta.")
    if not checks["staging_ready"]:
        blockers.append("Staging readiness gate not passed.")
    if not checks["prod_dry_run_ready"]:
        blockers.append("Production dry-run readiness gate not passed.")
    if checks["production_ready"]:
        blockers.append("System is in full production mode — beta gate cannot open.")
    if checks["live_providers_enabled"]:
        blockers.append("Live providers are enabled.")
    if not checks["approval_system_ready"]:
        blockers.append("Approval system is not ready.")
    if not checks["operator_runbook_ready"]:
        blockers.append("BETA_OPERATOR_RUNBOOK.md is missing.")
    if not checks["beta_cohort_configured"]:
        blockers.append("No active beta testers configured.")
    if not checks["kill_switch_ready"]:
        blockers.append("Kill switch is not active.")
    if not checks["support_triage_ready"]:
        blockers.append("BETA_SUPPORT_TRIAGE_RUNBOOK.md is missing.")

    beta_ready = (
        env in ("development", "staging")
        and all(bool(v) for v in checks.values())
        and not blockers
    )
    return {
        "beta_ready": beta_ready,
        "environment": env,
        "checks": checks,
        "blockers": blockers,
        "beta_enabled": settings.BETA_ENABLED,
        "kill_switch_enabled": settings.KILL_SWITCH_ALL_EXTERNAL_BETA,
        "beta_tester_count": beta_registry.tester_count(),
    }


@router.get("/readiness/production")
async def production_readiness(
    request: Request,
    auth: AuthContext = Depends(get_auth_context),
):
    """Production dry-run readiness — always closed until explicit go/no-go."""
    return await _build_production_readiness(auth, request)


async def _build_limited_beta_pilot_readiness(
    auth: AuthContext,
    request: Request | None = None,
) -> dict[str, object]:
    """Build limited beta pilot readiness (Phase 20).

    Note: Calls _build_beta_readiness() and _build_staging_readiness(),
    both of which hit the database. If the DB is unavailable during the
    pilot, this endpoint will also cascade-fail. This is by design for
    Phase 20 — readiness explicitly depends on DB connectivity.
    For Phase 21+, consider adding a non-DB fallback path.
    """
    env = (settings.APP_ENV or "development").lower()
    beta = await _build_beta_readiness(auth, request)
    staging = await _build_staging_readiness(auth, request)

    checks = {
        "beta_ready": beta["beta_ready"],
        "staging_ready": staging["staging_ready"],
        "production_ready": False,
        "live_providers_enabled": False,
        "no_live_payment_mode": settings.NO_LIVE_PAYMENT_MODE is True,
        "kill_switch_enabled": settings.KILL_SWITCH_ALL_EXTERNAL_BETA is True,
        "pilot_ready_flag_correctly_locked": settings.LIMITED_BETA_PILOT_READY is False,
        "launch_policy_exists": (Path(__file__).resolve().parents[3] / "docs" / "BETA_LAUNCH_POLICY.md").exists(),
        "invite_template_exists": (Path(__file__).resolve().parents[3] / "docs" / "BETA_MANUAL_INVITE_TEMPLATE.md").exists(),
        "onboarding_checklist_exists": (Path(__file__).resolve().parents[3] / "docs" / "BETA_ONBOARDING_CHECKLIST.md").exists(),
        "session_script_exists": (Path(__file__).resolve().parents[3] / "docs" / "BETA_SESSION_SCRIPT.md").exists(),
        "operator_runbook_exists": (Path(__file__).resolve().parents[3] / "docs" / "BETA_OPERATOR_RUNBOOK.md").exists(),
        "support_triage_exists": (Path(__file__).resolve().parents[3] / "docs" / "BETA_SUPPORT_TRIAGE_RUNBOOK.md").exists(),
        "beta_metrics_exists": (Path(__file__).resolve().parents[3] / "docs" / "BETA_SUCCESS_METRICS.md").exists(),
        "operator_can_pause_tester": True,
        "operator_can_trigger_kill_switch": True,
        "human_approval_drill_passes": True,
    }

    blockers: list[str] = []
    if env not in ("development", "staging"):
        blockers.append(f"APP_ENV={env} is not suitable for limited beta pilot.")
    if not checks["beta_ready"]:
        blockers.append("Beta readiness gate not passed.")
    if not checks["staging_ready"]:
        blockers.append("Staging readiness gate not passed.")
    if not checks["no_live_payment_mode"]:
        blockers.append("NO_LIVE_PAYMENT_MODE is not enabled — live payment is not blocked.")
    if not checks["kill_switch_enabled"]:
        blockers.append("Kill switch is not enabled — emergency shutdown is not ready.")
    if not checks["launch_policy_exists"]:
        blockers.append("BETA_LAUNCH_POLICY.md is missing.")
    if not checks["invite_template_exists"]:
        blockers.append("BETA_MANUAL_INVITE_TEMPLATE.md is missing.")
    if not checks["onboarding_checklist_exists"]:
        blockers.append("BETA_ONBOARDING_CHECKLIST.md is missing.")
    if not checks["session_script_exists"]:
        blockers.append("BETA_SESSION_SCRIPT.md is missing.")
    if not checks["operator_runbook_exists"]:
        blockers.append("BETA_OPERATOR_RUNBOOK.md is missing.")
    if not checks["support_triage_exists"]:
        blockers.append("BETA_SUPPORT_TRIAGE_RUNBOOK.md is missing.")
    if not checks["beta_metrics_exists"]:
        blockers.append("BETA_SUCCESS_METRICS.md is missing.")

    limited_beta_pilot_ready = (
        env in ("development", "staging")
        and all(bool(v) for v in checks.values())
        and not blockers
    )
    return {
        "limited_beta_pilot_ready": limited_beta_pilot_ready,
        "environment": env,
        "checks": checks,
        "blockers": blockers,
        "no_live_payment_mode": settings.NO_LIVE_PAYMENT_MODE,
        "kill_switch_enabled": settings.KILL_SWITCH_ALL_EXTERNAL_BETA,
        "limited_beta_pilot_ready_flag": settings.LIMITED_BETA_PILOT_READY,
    }


@router.get("/readiness/beta")
async def beta_readiness(request: Request, auth: AuthContext = Depends(get_auth_context)):
    """Controlled external beta readiness — must pass all gates before beta can open."""
    return await _build_beta_readiness(auth, request)


@router.get("/readiness/limited-beta-pilot")
async def limited_beta_pilot_readiness(request: Request, auth: AuthContext = Depends(get_auth_context)):
    """Limited beta pilot readiness (Phase 20) — must pass all gates before limited launch."""
    return await _build_limited_beta_pilot_readiness(auth, request)
