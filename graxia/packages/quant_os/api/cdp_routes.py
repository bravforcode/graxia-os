"""
TradingView CDP API Routes — Chrome DevTools Protocol control endpoints.

Provides REST API for chart control, drawing tools, Pine Script,
layout management, and screenshots via TradingView CDP bridge.
"""

from __future__ import annotations

from typing import Any

import structlog
from fastapi import APIRouter, HTTPException, Query

from .tv_cdp import TradingViewCDP

logger = structlog.get_logger(__name__)

cdp_router = APIRouter(prefix="/cdp", tags=["tradingview-cdp"])


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


async def _get_cdp() -> TradingViewCDP:
    """Create and connect a TradingViewCDP instance."""
    cdp = TradingViewCDP()
    connected = await cdp.connect()
    if not connected:
        raise HTTPException(
            status_code=503,
            detail=(
                "Cannot connect to TradingView CDP. " "Ensure TradingView is running with --remote-debugging-port=9222"
            ),
        )
    return cdp


# ---------------------------------------------------------------------------
# Symbol & Timeframe
# ---------------------------------------------------------------------------


@cdp_router.get("/symbol")
async def get_current_symbol() -> dict[str, Any]:
    """Get current chart symbol from TradingView."""
    cdp = await _get_cdp()
    try:
        symbol = await cdp.get_current_symbol()
        return {"symbol": symbol}
    except Exception as exc:
        logger.error("cdp_get_symbol_failed", error=str(exc))
        raise HTTPException(status_code=500, detail=str(exc))
    finally:
        await cdp.disconnect()


@cdp_router.post("/symbol/{symbol}")
async def change_symbol(symbol: str) -> dict[str, Any]:
    """Change chart symbol in TradingView."""
    cdp = await _get_cdp()
    try:
        ok = await cdp.change_symbol(symbol)
        if not ok:
            raise HTTPException(status_code=400, detail=f"Failed to change symbol to {symbol}")
        return {"status": "ok", "symbol": symbol}
    except HTTPException:
        raise
    except Exception as exc:
        logger.error("cdp_change_symbol_failed", symbol=symbol, error=str(exc))
        raise HTTPException(status_code=500, detail=str(exc))
    finally:
        await cdp.disconnect()


@cdp_router.post("/timeframe/{timeframe}")
async def change_timeframe(timeframe: str) -> dict[str, Any]:
    """Change chart timeframe in TradingView.

    Valid timeframes: 1m, 3m, 5m, 15m, 30m, 1h, 2h, 4h, 6h, 8h, 12h, 1D, 1W, 1M.
    """
    cdp = await _get_cdp()
    try:
        ok = await cdp.change_timeframe(timeframe)
        if not ok:
            raise HTTPException(
                status_code=400,
                detail=f"Failed to change timeframe to {timeframe}",
            )
        return {"status": "ok", "timeframe": timeframe}
    except HTTPException:
        raise
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except Exception as exc:
        logger.error("cdp_change_timeframe_failed", timeframe=timeframe, error=str(exc))
        raise HTTPException(status_code=500, detail=str(exc))
    finally:
        await cdp.disconnect()


# ---------------------------------------------------------------------------
# Drawing Tools
# ---------------------------------------------------------------------------


@cdp_router.post("/draw/support")
async def draw_support(price: float = Query(..., description="Price level")) -> dict[str, Any]:
    """Draw a support line at the given price level."""
    cdp = await _get_cdp()
    try:
        ok = await cdp.draw_support_line(price)
        if not ok:
            raise HTTPException(status_code=400, detail="Failed to draw support line")
        return {"status": "ok", "type": "support", "price": price}
    except HTTPException:
        raise
    except Exception as exc:
        logger.error("cdp_draw_support_failed", price=price, error=str(exc))
        raise HTTPException(status_code=500, detail=str(exc))
    finally:
        await cdp.disconnect()


@cdp_router.post("/draw/resistance")
async def draw_resistance(price: float = Query(..., description="Price level")) -> dict[str, Any]:
    """Draw a resistance line at the given price level."""
    cdp = await _get_cdp()
    try:
        ok = await cdp.draw_resistance_line(price)
        if not ok:
            raise HTTPException(status_code=400, detail="Failed to draw resistance line")
        return {"status": "ok", "type": "resistance", "price": price}
    except HTTPException:
        raise
    except Exception as exc:
        logger.error("cdp_draw_resistance_failed", price=price, error=str(exc))
        raise HTTPException(status_code=500, detail=str(exc))
    finally:
        await cdp.disconnect()


# ---------------------------------------------------------------------------
# Pine Script
# ---------------------------------------------------------------------------


@cdp_router.post("/pine/write")
async def write_pine(script: str = Query(..., description="Pine Script source code")) -> dict[str, Any]:
    """Write Pine Script to the TradingView editor."""
    cdp = await _get_cdp()
    try:
        ok = await cdp.write_pine_script(script)
        if not ok:
            raise HTTPException(status_code=400, detail="Failed to write Pine Script")
        return {"status": "ok", "script_length": len(script)}
    except HTTPException:
        raise
    except Exception as exc:
        logger.error("cdp_write_pine_failed", error=str(exc))
        raise HTTPException(status_code=500, detail=str(exc))
    finally:
        await cdp.disconnect()


@cdp_router.post("/pine/compile")
async def compile_pine() -> dict[str, Any]:
    """Compile the current Pine Script in the editor."""
    cdp = await _get_cdp()
    try:
        result = await cdp.compile_pine_script()
        return {
            "success": result.success,
            "errors": result.errors,
            "warnings": result.warnings,
            "script_id": result.script_id,
        }
    except Exception as exc:
        logger.error("cdp_compile_pine_failed", error=str(exc))
        raise HTTPException(status_code=500, detail=str(exc))
    finally:
        await cdp.disconnect()


# ---------------------------------------------------------------------------
# Layout & Screenshot
# ---------------------------------------------------------------------------


@cdp_router.post("/layout/{layout}")
async def set_layout(layout: str = "2x2") -> dict[str, Any]:
    """Set chart layout (e.g. 1x1, 2x1, 2x2, 3x1)."""
    cdp = await _get_cdp()
    try:
        ok = await cdp.set_layout(layout)
        if not ok:
            raise HTTPException(status_code=400, detail=f"Failed to set layout to {layout}")
        return {"status": "ok", "layout": layout}
    except HTTPException:
        raise
    except Exception as exc:
        logger.error("cdp_set_layout_failed", layout=layout, error=str(exc))
        raise HTTPException(status_code=500, detail=str(exc))
    finally:
        await cdp.disconnect()


@cdp_router.post("/screenshot")
async def screenshot_chart() -> dict[str, Any]:
    """Take a screenshot of the current TradingView chart."""
    cdp = await _get_cdp()
    try:
        path = await cdp.screenshot_chart()
        return {"status": "ok", "path": str(path)}
    except Exception as exc:
        logger.error("cdp_screenshot_failed", error=str(exc))
        raise HTTPException(status_code=500, detail=str(exc))
    finally:
        await cdp.disconnect()
