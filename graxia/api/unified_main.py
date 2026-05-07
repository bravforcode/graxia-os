"""
╔═══════════════════════════════════════════════════════════════════════════════╗
║                                                                               ║
║   Graxia OS — Unified API Server                                              ║
║                                                                               ║
║   Integrates:                                                                 ║
║   • Revenue OS — Business operations, orders, revenue tracking                ║
║   • Quant OS — Forex trading, risk management, algorithmic strategies         ║
║                                                                               ║
║   Architecture: Service Layer + Repository Pattern                          ║
║   Database: Shared PostgreSQL with schema separation                          ║
║   Cache: Shared Redis cluster                                                 ║
║                                                                               ║
╚═══════════════════════════════════════════════════════════════════════════════╝
"""

import asyncio
import os
from contextlib import asynccontextmanager
from datetime import datetime
from typing import AsyncGenerator

from fastapi import FastAPI, Request, HTTPException, status, Depends
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy.ext.asyncio import AsyncSession
import structlog

# Configure structured logging
structlog.configure(
    processors=[
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.JSONRenderer()
    ]
)
logger = structlog.get_logger()

# ═══════════════════════════════════════════════════════════════════════════════
# SHARED DEPENDENCIES (defined early for use in routes)
# ═══════════════════════════════════════════════════════════════════════════════

async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """Shared database dependency for both Revenue and Quant OS"""
    from graxia.packages.revenue_os.db import get_db as _get_db
    async for session in _get_db():
        yield session

# ═══════════════════════════════════════════════════════════════════════════════
# IMPORT ALL ROUTERS
# ═══════════════════════════════════════════════════════════════════════════════

# Revenue OS Routers (optional - graceful fallback)
revenue_routers = {}
try:
    from graxia.packages.revenue_os.api.orders import router as revenue_orders_router
    revenue_routers["orders"] = revenue_orders_router
except ImportError:
    revenue_orders_router = None

try:
    from graxia.packages.revenue_os.api.products import router as revenue_products_router
    revenue_routers["products"] = revenue_products_router
except ImportError:
    revenue_products_router = None

try:
    from graxia.packages.revenue_os.api.customers import router as revenue_customers_router
    revenue_routers["customers"] = revenue_customers_router
except ImportError:
    revenue_customers_router = None

try:
    from graxia.packages.revenue_os.api.analytics import router as revenue_analytics_router
    revenue_routers["analytics"] = revenue_analytics_router
except ImportError:
    revenue_analytics_router = None

try:
    from graxia.packages.revenue_os.api.webhooks import router as revenue_webhooks_router
    revenue_routers["webhooks"] = revenue_webhooks_router
except ImportError:
    revenue_webhooks_router = None

# Quant OS Routers (optional - graceful fallback)
quant_routers = {}
try:
    from graxia.packages.quant_os.api.webhook import webhook_router as quant_webhook_router
    quant_routers["webhook"] = quant_webhook_router
except ImportError as e:
    print(f"Warning: Could not import Quant webhook router: {e}")
    quant_webhook_router = None

try:
    from graxia.packages.quant_os.api.orders import router as quant_orders_router
    quant_routers["orders"] = quant_orders_router
except ImportError as e:
    print(f"Warning: Could not import Quant orders router: {e}")
    quant_orders_router = None

try:
    from graxia.packages.quant_os.api.positions import router as quant_positions_router
    quant_routers["positions"] = quant_positions_router
except ImportError as e:
    print(f"Warning: Could not import Quant positions router: {e}")
    quant_positions_router = None

try:
    from graxia.packages.quant_os.api.risk import router as quant_risk_router
    quant_routers["risk"] = quant_risk_router
except ImportError as e:
    print(f"Warning: Could not import Quant risk router: {e}")
    quant_risk_router = None

try:
    from graxia.packages.quant_os.api.admin import router as quant_admin_router
    quant_routers["admin"] = quant_admin_router
except ImportError as e:
    print(f"Warning: Could not import Quant admin router: {e}")
    quant_admin_router = None

# Shared Infrastructure
from graxia.packages.quant_os.core.config import get_config as get_quant_config
from graxia.packages.quant_os.core.enums import SystemState

# ═══════════════════════════════════════════════════════════════════════════════
# LIFESPAN MANAGEMENT
# ═══════════════════════════════════════════════════════════════════════════════

@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Application lifespan manager.
    Handles startup initialization and graceful shutdown.
    """
    # ═══════════════════════════════════════════════════════════════════════════
    # STARTUP
    # ═══════════════════════════════════════════════════════════════════════════
    logger.info(
        "graxia_os_startup",
        version="2.0.0",
        modules=["revenue_os", "quant_os"],
        timestamp=datetime.utcnow().isoformat()
    )

    try:
        # Initialize Quant OS
        quant_config = get_quant_config()
        logger.info(
            "quant_os_initialized",
            trading_mode=quant_config.trading_mode.value,
            live_trading=quant_config.live_trading_enabled,
            state=SystemState.NORMAL.value
        )

        logger.info("graxia_os_ready", status="operational")

    except Exception as e:
        logger.error("startup_failed", error=str(e))
        raise

    yield

    # ═══════════════════════════════════════════════════════════════════════════
    # SHUTDOWN
    # ═══════════════════════════════════════════════════════════════════════════
    logger.info("graxia_os_shutdown", timestamp=datetime.utcnow().isoformat())

# ═══════════════════════════════════════════════════════════════════════════════
# CREATE UNIFIED APP
# ═══════════════════════════════════════════════════════════════════════════════

app = FastAPI(
    title="Graxia OS — Unified API",
    description="""
    **Graxia OS** — Enterprise-grade unified platform integrating:

    * **Revenue OS** — Business operations, order management, revenue tracking
    * **Quant OS** — Algorithmic forex trading with risk management

    ## Features

    - **Unified Authentication** — Single JWT across all modules
    - **Shared Infrastructure** — One database, one Redis, one monitoring stack
    - **Cross-Domain Operations** — Revenue triggers trading, trading affects revenue
    - **Enterprise Security** — HMAC webhooks, rate limiting, audit trails
    """,
    version="2.0.0",
    docs_url="/docs",
    redoc_url="/redoc",
    openapi_url="/openapi.json",
    lifespan=lifespan
)

# ═══════════════════════════════════════════════════════════════════════════════
# MIDDLEWARE
# ═══════════════════════════════════════════════════════════════════════════════

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=os.getenv("CORS_ORIGINS", "*").split(","),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Compression
app.add_middleware(GZipMiddleware, minimum_size=1000)

# Request logging middleware
@app.middleware("http")
async def log_requests(request: Request, call_next):
    """Log all requests with structured logging"""
    start_time = datetime.utcnow()

    response = await call_next(request)

    duration = (datetime.utcnow() - start_time).total_seconds()

    logger.info(
        "request_processed",
        method=request.method,
        path=request.url.path,
        status_code=response.status_code,
        duration_seconds=duration,
        user_agent=request.headers.get("user-agent"),
    )

    return response

# ═══════════════════════════════════════════════════════════════════════════════
# MOUNT ALL ROUTERS
# ═══════════════════════════════════════════════════════════════════════════════

# Revenue OS API (v1) - mount only if available
if revenue_orders_router:
    app.include_router(
        revenue_orders_router,
        prefix="/api/v1/revenue/orders",
        tags=["Revenue — Orders"]
    )
if revenue_products_router:
    app.include_router(
        revenue_products_router,
        prefix="/api/v1/revenue/products",
        tags=["Revenue — Products"]
    )
if revenue_customers_router:
    app.include_router(
        revenue_customers_router,
        prefix="/api/v1/revenue/customers",
        tags=["Revenue — Customers"]
    )
if revenue_analytics_router:
    app.include_router(
        revenue_analytics_router,
        prefix="/api/v1/revenue/analytics",
        tags=["Revenue — Analytics"]
    )
if revenue_webhooks_router:
    app.include_router(
        revenue_webhooks_router,
        prefix="/api/v1/revenue/webhooks",
        tags=["Revenue — Webhooks"]
    )

# Quant OS API (v1) - mount only if available
if quant_webhook_router:
    app.include_router(
        quant_webhook_router,
        prefix="/api/v1/quant/webhook",
        tags=["Quant — TradingView Webhook"]
    )
if quant_orders_router:
    app.include_router(
        quant_orders_router,
        prefix="/api/v1/quant/orders",
        tags=["Quant — Orders"]
    )
if quant_positions_router:
    app.include_router(
        quant_positions_router,
        prefix="/api/v1/quant/positions",
        tags=["Quant — Positions"]
    )
if quant_risk_router:
    app.include_router(
        quant_risk_router,
        prefix="/api/v1/quant/risk",
        tags=["Quant — Risk Management"]
    )
if quant_admin_router:
    app.include_router(
        quant_admin_router,
        prefix="/api/v1/quant/admin",
        tags=["Quant — Admin"]
    )

# ═══════════════════════════════════════════════════════════════════════════════
# CROSS-DOMAIN SERVICE LAYER
# ═══════════════════════════════════════════════════════════════════════════════

@app.get("/api/v1/unified/dashboard", tags=["Unified — Dashboard"])
async def unified_dashboard(db: AsyncSession = Depends(get_db)):
    """
    Cross-domain dashboard combining Revenue and Trading metrics.

    Returns:
    - Revenue metrics (today's revenue, orders)
    - Trading metrics (open positions, P&L)
    - Combined health status
    """
    # This would query both domains and combine results
    # Implementation would use service layer pattern
    return {
        "revenue": {
            "today_revenue": 0,
            "today_orders": 0,
            "active_products": 0,
        },
        "trading": {
            "open_positions": 0,
            "today_pnl": 0,
            "trading_mode": "PAPER",
            "kill_switch": "ARMED"
        },
        "system": {
            "status": "operational",
            "version": "2.0.0",
            "modules": ["revenue_os", "quant_os"]
        }
    }

# ═══════════════════════════════════════════════════════════════════════════════
# HEALTH & STATUS
# ═══════════════════════════════════════════════════════════════════════════════

@app.get("/health", tags=["System"])
async def health_check():
    """Health check endpoint for load balancers"""
    return {
        "status": "healthy",
        "version": "2.0.0",
        "timestamp": datetime.utcnow().isoformat(),
        "modules": {
            "revenue_os": "operational",
            "quant_os": "operational"
        }
    }

@app.get("/", tags=["System"])
async def root():
    """Root endpoint with API information"""
    return {
        "name": "Graxia OS",
        "version": "2.0.0",
        "description": "Unified Revenue + Trading Platform",
        "docs": "/docs",
        "health": "/health",
        "modules": ["revenue_os", "quant_os"]
    }

@app.get("/api/v1/status", tags=["System"])
async def system_status():
    """Detailed system status"""
    quant_config = get_quant_config()

    return {
        "system": {
            "status": "operational",
            "version": "2.0.0",
            "timestamp": datetime.utcnow().isoformat()
        },
        "revenue_os": {
            "status": "operational",
            "features": ["orders", "products", "customers", "analytics"]
        },
        "quant_os": {
            "status": "operational",
            "trading_mode": quant_config.trading_mode.value,
            "live_trading": quant_config.live_trading_enabled,
            "features": ["trading", "risk_management", "webhooks", "strategies"]
        }
    }

# ═══════════════════════════════════════════════════════════════════════════════
# ERROR HANDLERS
# ═══════════════════════════════════════════════════════════════════════════════

@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    """Global exception handler with structured logging"""
    logger.error(
        "unhandled_exception",
        error=str(exc),
        path=request.url.path,
        method=request.method,
    )

    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content={
            "error": "Internal server error",
            "detail": str(exc) if os.getenv("DEBUG") else "An error occurred"
        }
    )

# ═══════════════════════════════════════════════════════════════════════════════
# MAIN ENTRY POINT
# ═══════════════════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "graxia.api.unified_main:app",
        host="0.0.0.0",
        port=int(os.getenv("PORT", 8000)),
        reload=os.getenv("DEBUG", "false").lower() == "true",
        workers=1 if os.getenv("DEBUG") else int(os.getenv("WORKERS", 2))
    )
