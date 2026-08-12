import logging
import time
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request, Response
from fastapi.middleware.cors import CORSMiddleware

from app.api.router import api_router
from app.api.internal import router as internal_router
from app.config import settings
from app.core.exception_handlers import register_exception_handlers
from app.core.logging_config import setup_logging
from app.core.monitoring import metrics_collector
from app.core.request_context import RequestContextMiddleware
from app.core.runtime_state import get_runtime_state, set_runtime_state
from app.core.setup import init_sentry
from app.core.swarm_bootstrap import initialize_graxia_components
from app.cqrs.setup import setup_cqrs
from app.auth.middleware import AuthContextMiddleware
from app.middleware.auth import AuthMiddleware
from app.middleware.rate_limit import RateLimitMiddleware, get_redis_client
from app.core.security_hardening import (
    APIKeyRotationTracker,
    IPFilterMiddleware,
    RequestSanitizationMiddleware,
    SecureHeaders,
    api_key_tracker,
)
from app.middleware.security import (
    CSRFMiddleware,
    RequestSizeLimitMiddleware,
    SecurityHeadersMiddleware,
)

setup_logging(settings.LOG_LEVEL)
logger = logging.getLogger(__name__)

# Initialize Error Tracking
init_sentry()

# Initialize CQRS
setup_cqrs()

@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Graxia OS starting up")
    set_runtime_state(False, "booting", [])

    settings.validate_production_configuration()
    redis_client = await get_redis_client()
    app.state.redis = redis_client

    try:
        from app.core.bootstrap import (
            check_system_ready,
            initialize_telegram_notifier,
            seed_admin_user,
            wire_event_handlers,
        )

        # Enterprise Database Policy: Schema creation MUST be handled by Alembic migrations.
        logger.info("Database initialization bypassed. Ensure `alembic upgrade head` is run before deployment.")

        wire_event_handlers()
        await seed_admin_user()

        if not settings.TESTING:
            await initialize_telegram_notifier()

        # Initialize Graxia AI Components (Swarm, Pipeline, etc.)
        await initialize_graxia_components()

        is_ready, mode, issues = await check_system_ready()
        set_runtime_state(is_ready, mode, issues)
        logger.info("Startup readiness mode=%s issues=%s", mode, len(issues))
    except Exception as exc:
        set_runtime_state(False, "blocked", [str(exc)])
        logger.error("Startup error: %s", exc, exc_info=True)

    yield

    if hasattr(app.state, "redis") and app.state.redis:
        await app.state.redis.close()
    logger.info("Graxia OS shut down")


app = FastAPI(
    title="Graxia OS — Enterprise Revenue OS",
    description="Canonical API for the Graxia OS control plane",
    version="3.0.0",
    lifespan=lifespan,
    docs_url=None if settings.STRICT_BOOTSTRAP else "/docs",
    redoc_url=None if settings.STRICT_BOOTSTRAP else "/redoc",
    openapi_url=None if settings.STRICT_BOOTSTRAP else "/openapi.json",
)

register_exception_handlers(app)


@app.middleware("http")
async def add_metrics_middleware(request: Request, call_next):
    start_time = time.time()
    response = await call_next(request)
    duration = time.time() - start_time
    metrics_collector.record_http_request(
        method=request.method,
        endpoint=request.url.path,
        status=response.status_code,
        duration=duration,
    )
    response.headers["X-Process-Time"] = str(duration)
    return response


# ============================================================================
# MIDDLEWARE STACK ARCHITECTURE
# ============================================================================
# 
# Middleware execution order in FastAPI/Starlette:
# - Middleware added LAST executes FIRST (outermost layer)
# - Middleware added FIRST executes LAST (innermost layer)
# 
# Request Flow (top to bottom):
#   1. CORS → 2. RequestSizeLimit → 3. IPFilter → 4. RateLimit → 
#   5. SecurityHeaders → 6. CSRF → 7. Auth → 8. RequestSanitization → 
#   9. Application Logic
# 
# Response Flow (bottom to top):
#   9. Application Logic → 8. RequestSanitization → 7. Auth → 6. CSRF → 
#   5. SecurityHeaders → 4. RateLimit → 3. IPFilter → 2. RequestSizeLimit → 
#   1. CORS
# 
# ============================================================================
# SECURITY LAYER DEPENDENCIES & RATIONALE
# ============================================================================
#
# Layer 1: CORS (Outermost - Added Last)
# ----------------------------------------
# Purpose: Handle cross-origin requests, set CORS headers
# Dependencies: None (must be outermost to handle preflight OPTIONS requests)
# Security: Validates origin before any processing, prevents CSRF at browser level
# Position: MUST be outermost to intercept all requests including preflight
#
# Layer 2: Request Size Limit
# ----------------------------
# Purpose: Reject oversized requests early to prevent DoS
# Dependencies: None (should reject before expensive processing)
# Security: Prevents memory exhaustion, reduces attack surface
# Position: Second outermost to fail fast on large payloads
#
# Layer 3: IP Filtering (Enterprise)
# -----------------------------------
# Purpose: Block/allow requests based on source IP (whitelist/blacklist)
# Dependencies: None (edge-level filtering)
# Security: Network-level access control, blocks malicious IPs early
# Position: Third layer to filter before rate limiting (save resources)
#
# Layer 4: Rate Limiting
# -----------------------
# Purpose: Throttle requests per IP/user to prevent abuse
# Dependencies: Requires IP address (from Layer 3), uses Redis
# Security: Prevents brute force, DoS, and API abuse
# Position: Before authentication to protect auth endpoints from brute force
#
# Layer 5: Security Headers (Basic + Enterprise)
# -----------------------------------------------
# Purpose: Add security headers (CSP, HSTS, X-Frame-Options, etc.)
# Dependencies: None (adds headers to all responses)
# Security: Defense-in-depth browser protections (XSS, clickjacking, etc.)
# Position: After rate limiting, before auth (headers apply to all responses)
# Note: Two middleware (Basic + Enterprise) for modular security policies
#
# Layer 6: CSRF Protection
# -------------------------
# Purpose: Validate CSRF tokens for state-changing operations
# Dependencies: Requires session_id from AuthMiddleware (Layer 7)
# Security: Prevents cross-site request forgery attacks
# Position: MUST be after AuthMiddleware to access request.state.session_id
# Critical: Token validation uses constant-time comparison (timing attack protection)
#
# Layer 7: Authentication
# ------------------------
# Purpose: Validate JWT tokens, establish user identity and session
# Dependencies: None (but provides session_id for CSRF layer)
# Security: Enforces authentication, role-based access control (RBAC)
# Position: After CSRF (CSRF needs session_id), before sanitization
# Provides: request.state.session_id, request.state.authenticated_user_id
#
# Layer 8: Request Sanitization (Innermost - Added First)
# --------------------------------------------------------
# Purpose: Detect and block SQL injection, XSS patterns in query params/path
# Dependencies: None (but benefits from auth context for logging)
# Security: Input validation, prevents injection attacks
# Position: Innermost (last defense before application logic)
# Note: Uses regex patterns - may need context-aware improvements (see M-05)
#
# ============================================================================
# CRITICAL ORDERING RULES
# ============================================================================
#
# 1. CORS MUST be outermost (added last) to handle preflight requests
# 2. IP Filtering MUST be before Rate Limiting (save resources on blocked IPs)
# 3. Rate Limiting MUST be before Auth (protect auth endpoints from brute force)
# 4. Auth MUST be before CSRF (CSRF needs session_id from auth)
# 5. Request Sanitization SHOULD be innermost (last defense before app logic)
#
# ============================================================================
# SECURITY IMPLICATIONS OF REORDERING
# ============================================================================
#
# ❌ DANGEROUS: Moving CSRF before Auth
#    → CSRF validation fails (no session_id available)
#    → All state-changing requests blocked
#
# ❌ DANGEROUS: Moving Auth before Rate Limiting
#    → Auth endpoints vulnerable to brute force
#    → Attacker can exhaust auth resources
#
# ❌ DANGEROUS: Moving IP Filter after Rate Limiting
#    → Blocked IPs consume rate limit resources
#    → Legitimate users may be rate limited
#
# ❌ DANGEROUS: Moving CORS inward (not outermost)
#    → Preflight OPTIONS requests may be blocked
#    → CORS headers may not be added to error responses
#
# ✅ SAFE: Reordering Security Headers layers (Basic ↔ Enterprise)
#    → Both add headers, order doesn't matter
#
# ✅ SAFE: Moving Request Sanitization up/down (within reason)
#    → Independent validation, but innermost is optimal
#
# ============================================================================
# ADDING NEW MIDDLEWARE
# ============================================================================
#
# When adding new middleware, consider:
# 1. Does it need data from other middleware? (add after dependencies)
# 2. Should it fail fast? (add closer to outermost)
# 3. Does it modify request.state? (document what it provides)
# 4. Does it need authentication context? (add after AuthMiddleware)
# 5. Does it need to run on all requests? (add before AuthMiddleware)
#
# Example: Adding a new "AuditLogMiddleware"
# - Needs: authenticated_user_id (from AuthMiddleware)
# - Position: After AuthMiddleware, before RequestSanitization
# - Add: app.add_middleware(AuditLogMiddleware)  # Between Auth and Sanitization
#
# ============================================================================

# Innermost execution (added first) - Last defense before application logic
app.add_middleware(RequestSanitizationMiddleware)

# CSRF Protection (depends on Auth for session_id, so Auth must execute first)
app.add_middleware(CSRFMiddleware)  # Requires: request.state.session_id

# Authentication (provides session_id for CSRF layer)
app.add_middleware(AuthMiddleware)  # Provides: request.state.session_id

# AuthContext (org-scoped auth context for multi-tenancy)
app.add_middleware(AuthContextMiddleware)  # Provides: request.state.auth_context

# Security Headers (Defense-in-depth browser protections)
# Single middleware reads from settings — configurable per environment (L-01, L-09)
app.add_middleware(SecurityHeadersMiddleware)

# Rate Limiting (Protect auth endpoints from brute force)
app.add_middleware(RateLimitMiddleware)

# IP Filtering (Block malicious IPs at edge before rate limiting)
ip_whitelist = [ip.strip() for ip in settings.IP_WHITELIST.split(",") if ip.strip()] if settings.IP_WHITELIST else []
ip_blacklist = [ip.strip() for ip in settings.IP_BLACKLIST.split(",") if ip.strip()] if settings.IP_BLACKLIST else []
app.add_middleware(
    IPFilterMiddleware,
    whitelist=ip_whitelist,
    blacklist=ip_blacklist,
)

# Request Size Limit (Fail fast on oversized requests)
app.add_middleware(RequestSizeLimitMiddleware)

# Request / correlation IDs for all downstream security and error handling
app.add_middleware(RequestContextMiddleware)

# CORS (Outermost - added last) - Must handle preflight OPTIONS requests
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Unified API Router
app.include_router(api_router)

# Internal API Router
app.include_router(internal_router, prefix="/internal")

@app.get("/health")
async def root_health():
    readiness = get_runtime_state()
    return {
        "status": "ok" if readiness["is_ready"] else "degraded",
        "service": "Graxia OS API",
        "readiness": readiness,
    }


@app.get("/")
async def root():
    return {
        "service": "Graxia OS API",
        "docs": "/docs",
    }


@app.get("/favicon.ico", include_in_schema=False)
async def favicon():
    return Response(status_code=204)

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
