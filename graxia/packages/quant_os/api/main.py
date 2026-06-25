"""
Quant OS FastAPI Application

Main FastAPI app that mounts all routers.
"""

from contextlib import asynccontextmanager

from fastapi import FastAPI, Depends, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials

from ..core.config import get_config
from ..core.golden_rules import validate_golden_rules
from ..execution.broker_adapter import BrokerManager
from .webhook import webhook_router
from .orders import orders_router
from .positions import positions_router
from .risk import risk_router
from .admin import admin_router


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
    
    # Initialize broker connection
    broker_manager = BrokerManager()
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
    if hasattr(app.state, 'broker_manager'):
        try:
            await app.state.broker_manager.active.disconnect()
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
    
    # CORS
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],  # Configure for production
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    
    # Include routers
    app.include_router(webhook_router, prefix="/api/v1")
    app.include_router(orders_router, prefix="/api/v1")
    app.include_router(positions_router, prefix="/api/v1")
    app.include_router(risk_router, prefix="/api/v1")
    app.include_router(admin_router, prefix="/api/v1/admin")
    
    # Root endpoint
    @app.get("/")
    async def root():
        return {
            "name": "Quant OS",
            "version": "1.0.0",
            "mode": config.trading_mode.value,
            "status": "operational"
        }
    
    # Health check
    @app.get("/health")
    async def health_check():
        broker_healthy = False
        if hasattr(app.state, 'broker_manager'):
            try:
                broker_healthy = await app.state.broker_manager.health_check()
            except Exception:
                pass
        
        return {
            "status": "healthy" if broker_healthy else "degraded",
            "broker_connected": broker_healthy,
            "trading_mode": config.trading_mode.value,
            "live_trading_enabled": config.live_trading_enabled
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
                "live_trading": config.live_trading_enabled
            },
            "risk": {
                "max_risk_per_trade_pct": config.max_risk_per_trade_pct,
                "max_daily_loss_pct": config.max_daily_loss_pct,
                "max_drawdown_pct": config.max_drawdown_pct,
                "max_positions": config.max_positions
            },
            "strategies": {
                "weights": config.strategy_weights,
                "min_confidence": config.ensemble_confidence_threshold
            }
        }
    
    return app


# Create app instance
app = create_app()


if __name__ == "__main__":
    import uvicorn
    config = get_config()
    
    uvicorn.run(
        "main:app",
        host=config.webhook_host,
        port=config.webhook_port,
        reload=False,
        log_level=config.log_level.lower()
    )
