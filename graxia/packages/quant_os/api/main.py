"""
Quant OS FastAPI Application

Main FastAPI app that mounts all routers.
"""

import uuid
from contextlib import asynccontextmanager
from datetime import UTC

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import HTTPBearer
from starlette.responses import Response

from ..core.config import get_config
from ..core.golden_rules import validate_golden_rules
from ..execution.adapters.manager import BrokerManager
from .admin import admin_router
from .health import health_router
from .orders import orders_router
from .positions import positions_router
from .rate_limit import RateLimitMiddleware
from .risk import risk_router
from .webhook import webhook_router

# Security
security = HTTPBearer(auto_error=False)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan manager"""
    # Startup
    print("🚀 Quant OS starting up...")

    # Validate golden rules
    rules_check = validate_golden_rules()
    if not rules_check["all_checks_passed"]:
        print("⚠️  Golden rules validation failed:")
        for check, passed in rules_check.items():
            if check != "all_checks_passed":
                status = "✓" if passed else "✗"
                print(f"  {status} {check}")
    else:
        print("✓ Golden rules validated")

    # Initialize orchestrator (wires EventBus → Agents → TradingLoop → PositionManager)
    from ..core.orchestrator import TradingOrchestrator

    config = get_config()
    orchestrator = TradingOrchestrator(config=config)
    orchestrator.start()
    app.state.orchestrator = orchestrator
    print(f"✓ Orchestrator started (mode={config.trading_mode.value})")

    # Initialize Telegram command handler with coordinator for kill-switch sync
    from .telegram_commands import TelegramCommandHandler

    telegram_handler = TelegramCommandHandler(
        coordinator=orchestrator.coordinator,
        state_store=orchestrator.coordinator._state_store,
        config=config,
    )
    app.state.telegram_handler = telegram_handler
    print("✓ Telegram command handler wired")

    # Initialize broker connection
    broker_manager = BrokerManager.from_config()
    app.state.broker_manager = broker_manager

    try:
        connected = await broker_manager.initialize()
        if connected:
            print(f"✓ Broker connected: {broker_manager.active.name}")
        else:
            print("⚠️  No broker connection available")
    except Exception as e:
        print(f"⚠️  Broker initialization error: {e}")

    # Yield control
    yield

    # Shutdown
    print("🛑 Quant OS shutting down...")
    if hasattr(app.state, "orchestrator"):
        app.state.orchestrator.stop()
        print("✓ Orchestrator stopped")
    if hasattr(app.state, "broker_manager"):
        try:
            app.state.broker_manager.active.disconnect()
            print("✓ Broker disconnected")
        except Exception:
            pass


def create_app() -> FastAPI:
    """Create and configure FastAPI application"""
    config = get_config()

    try:
        from pathlib import Path

        _ver = Path(__file__).parent.parent.joinpath("VERSION").read_text().strip()
    except Exception:
        _ver = "0.0.0"

    app = FastAPI(
        title="Quant OS — Forex Quantitative Trading System",
        summary="Risk-first algorithmic trading platform",
        description="""
        Risk-first automated trading system with:
        - Multi-strategy ensemble (MTM, MRB, MLB)
        - Paper → Live Micro promotion
        - Kill switch and circuit breakers
        - MT5 broker integration
        - TradingView webhook support
        """,
        version=_ver,
        contact={"name": "Quant OS Team", "url": "https://graxia.dev"},
        license_info={"name": "Proprietary — Graxia OS"},
        lifespan=lifespan,
    )

    # CORS — restrict origins in live mode
    config = get_config()
    allowed_origins = ["https://graxia.dev", "http://localhost:5173", "http://localhost:3000"]

    app.add_middleware(
        CORSMiddleware,
        allow_origins=allowed_origins,
        allow_credentials=True,
        allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
        allow_headers=["Content-Type", "Authorization", "X-API-Key"],
    )

    # Rate limiting — per-IP sliding window (middleware runs in reverse order,
    # so this wraps *after* CORS, meaning rate-limited responses still carry
    # CORS headers).
    app.add_middleware(RateLimitMiddleware)

    @app.middleware("http")
    async def count_requests(request, call_next):
        if not hasattr(app.state, "signal_requests"):
            app.state.signal_requests = 0
        if request.url.path == "/api/signal" and request.method == "POST":
            app.state.signal_requests += 1
        response = await call_next(request)
        return response

    # ── Correlation ID middleware ─────────────────────────────────────
    # Reads X-Request-ID from incoming requests (or generates one),
    # injects it into structlog's contextvars so every log line carries
    # the request identity, and returns it in the response headers.
    try:
        from ..monitoring.structured_formatter import correlation_id_var
    except ImportError:
        correlation_id_var = None

    @app.middleware("http")
    async def correlation_id_middleware(request: Request, call_next):
        # Read from header or generate
        corr_id = request.headers.get("x-request-id", "")
        if not corr_id:
            corr_id = uuid.uuid4().hex

        # Inject into structlog context so all loggers inherit it
        if correlation_id_var is not None:
            correlation_id_var.set(corr_id)

        # Also store on request.state for handler access
        request.state.correlation_id = corr_id

        response: Response = await call_next(request)
        response.headers["X-Request-ID"] = corr_id
        return response

    # Include routers
    app.include_router(webhook_router, prefix="/api/v1")
    app.include_router(orders_router, prefix="/api/v1")
    app.include_router(positions_router, prefix="/api/v1")
    app.include_router(risk_router, prefix="/api/v1")
    app.include_router(admin_router, prefix="/api/v1/admin")
    app.include_router(health_router, prefix="/api")

    # TradingView / Visual Search / CDP routers
    from .tv_routes import tv_router
    from .visual_routes import visual_router
    from .cdp_routes import cdp_router

    app.include_router(tv_router, prefix="/api/v1")
    app.include_router(visual_router, prefix="/api/v1")
    app.include_router(cdp_router, prefix="/api/v1")

    # ── Prometheus /metrics endpoint ──────────────────────────────────
    try:
        from prometheus_client import make_asgi_app

        metrics_app = make_asgi_app()
        app.mount("/metrics", metrics_app)
    except ImportError:
        pass  # prometheus_client not installed; /api/metrics fallback remains

    # Root endpoint
    @app.get("/")
    async def root():
        return {"name": "Quant OS", "version": "1.0.0", "mode": config.trading_mode.value, "status": "operational"}

    # Health check
    @app.get("/health")
    async def health_check():
        broker_healthy = False
        if hasattr(app.state, "broker_manager"):
            try:
                broker_healthy = await app.state.broker_manager.health_check()
            except Exception:
                pass

        orch_status = {}
        if hasattr(app.state, "orchestrator"):
            orch_status = app.state.orchestrator.get_status()

        return {
            "status": "healthy" if broker_healthy else "degraded",
            "broker_connected": broker_healthy,
            "trading_mode": config.trading_mode.value,
            "live_trading_enabled": config.live_trading_enabled,
            "orchestrator": orch_status,
        }

    # Status endpoint
    @app.get("/status")
    async def system_status():
        """Get full system status"""
        return {
            "system": {
                "name": "Quant OS",
                "version": "1.0.0",
                "trading_mode": config.trading_mode.value,
                "live_trading": config.live_trading_enabled,
            },
            "risk": {
                "max_risk_per_trade_pct": config.max_risk_per_trade_pct,
                "max_daily_loss_pct": config.max_daily_loss_pct,
                "max_drawdown_pct": config.max_drawdown_pct,
                "max_positions": config.max_positions,
            },
            "strategies": {"weights": config.strategy_weights, "min_confidence": config.ensemble_confidence_threshold},
        }

    @app.get("/api/metrics")
    async def metrics():
        """Basic Prometheus-style metrics endpoint."""
        from datetime import datetime

        # Import actual model state from signal_service
        try:
            from . import signal_service

            model_loaded = signal_service._model_loaded
            feature_count = len(signal_service._feature_names)
        except Exception:
            model_loaded = False
            feature_count = 0

        return {
            "signal_requests_total": getattr(app.state, "signal_requests", 0),
            "model_loaded": model_loaded,
            "features": feature_count,
            "timestamp": datetime.now(UTC).isoformat(),
        }

    return app


# Create app instance
app = create_app()


if __name__ == "__main__":
    import uvicorn

    config = get_config()

    uvicorn.run(
        "main:app", host=config.webhook_host, port=config.webhook_port, reload=False, log_level=config.log_level.lower()
    )
