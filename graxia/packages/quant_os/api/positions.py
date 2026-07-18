"""Positions API endpoints"""

from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, ConfigDict
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Session

# Database dependency - use shared session from Revenue OS
from graxia.packages.revenue_os.db import get_db as _get_db

from ..core.enums import CloseReason
from ..data.models import Position
from .auth import verify_api_key


async def get_db():
    """Database session dependency"""
    async for session in _get_db():
        yield session


positions_router = APIRouter(prefix="/positions", tags=["positions"])


class PositionResponse(BaseModel):
    """Position response"""

    id: str
    symbol: str
    position_type: str
    quantity: str
    avg_entry_price: str
    current_price: str | None
    unrealized_pnl: str | None
    realized_pnl: str
    stop_loss: str | None
    take_profit: str | None
    is_open: bool
    opened_at: str

    model_config = ConfigDict(from_attributes=True)


class PositionListResponse(BaseModel):
    """List of positions"""

    positions: list[PositionResponse]
    total_pnl: str
    total_exposure: str


@positions_router.get("/", response_model=PositionListResponse)
async def list_positions(
    is_open: bool | None = True,
    symbol: str | None = None,
    db: AsyncSession = Depends(get_db),
    _: str = Depends(verify_api_key),
):
    """List positions with filters"""
    query = db.query(Position)

    if is_open is not None:
        query = query.filter(Position.is_open == is_open)
    if symbol:
        query = query.filter(Position.symbol == symbol.upper())

    positions = query.order_by(Position.opened_at.desc()).all()

    total_pnl = sum(p.unrealized_pnl or Decimal("0") for p in positions)
    total_exposure = sum((p.quantity * p.avg_entry_price) for p in positions)

    return PositionListResponse(
        positions=[_position_to_response(p) for p in positions],
        total_pnl=str(total_pnl),
        total_exposure=str(total_exposure),
    )


@positions_router.get("/{position_id}", response_model=PositionResponse)
async def get_position(
    position_id: str,
    db: Session = Depends(get_db),
    _: str = Depends(verify_api_key),
):
    """Get position by ID"""
    position = db.query(Position).filter(Position.id == position_id).first()
    if not position:
        raise HTTPException(status_code=404, detail="Position not found")
    return _position_to_response(position)


@positions_router.get("/symbol/{symbol}", response_model=PositionResponse)
async def get_position_by_symbol(
    symbol: str,
    db: Session = Depends(get_db),
    _: str = Depends(verify_api_key),
):
    """Get position by symbol"""
    position = db.query(Position).filter(Position.symbol == symbol.upper(), Position.is_open == True).first()
    if not position:
        raise HTTPException(status_code=404, detail="No open position found for symbol")
    return _position_to_response(position)


@positions_router.post("/{position_id}/close")
async def close_position(
    request: Request,
    position_id: str,
    reason: CloseReason = CloseReason.MANUAL,
    db: AsyncSession = Depends(get_db),
    _: str = Depends(verify_api_key),
):
    """Close a position — submits real close order via OMS/broker adapter."""
    position = db.query(Position).filter(Position.id == position_id).first()
    if not position:
        raise HTTPException(status_code=404, detail="Position not found")

    if not position.is_open:
        raise HTTPException(status_code=400, detail="Position already closed")

    # Get orchestrator from app state
    orch = getattr(request.app.state, "orchestrator", None)
    if orch is None:
        raise HTTPException(status_code=503, detail="Orchestrator not initialized")

    # Find the position in the orchestrator's position manager by symbol
    symbol = position.symbol
    orch_position = orch.position_manager.get_position(symbol)
    if orch_position is None:
        raise HTTPException(
            status_code=404,
            detail=f"Position {symbol} not found in orchestrator — may have been closed already",
        )

    # Submit close order via OMS if broker adapter available
    if orch._oms is not None and orch._broker_adapter is not None and orch._broker_adapter.is_connected:
        from ..core.enums import OrderSide

        close_side = OrderSide.SELL if orch_position.side == "BUY" else OrderSide.BUY
        try:
            import uuid
            from ..core.trading_loop import _symbol_to_asset_class

            result = orch._oms.submit_order(
                signal_id=f"close-{position_id}-{uuid.uuid4().hex[:8]}",
                symbol=symbol,
                asset_class=_symbol_to_asset_class(symbol),
                side=close_side.value,
                quantity=orch_position.quantity,
            )
            if result and hasattr(result, "status") and result.status == "FILLED":
                position.is_open = False
                return {
                    "success": True,
                    "position_id": position_id,
                    "symbol": symbol,
                    "message": f"Close order FILLED for {symbol}",
                    "reason": reason.value,
                }
            else:
                status_str = str(result.status) if result else "no result"
                raise HTTPException(
                    status_code=502,
                    detail=f"Broker rejected close order: {status_str}",
                )
        except HTTPException:
            raise
        except Exception as exc:
            raise HTTPException(
                status_code=502,
                detail=f"Broker error closing position: {exc}",
            )
    else:
        raise HTTPException(
            status_code=503,
            detail="Broker not connected — cannot close position",
        )


@positions_router.post("/{position_id}/update-stops")
async def update_stops(
    position_id: str,
    stop_loss: Decimal | None = None,
    take_profit: Decimal | None = None,
    db: AsyncSession = Depends(get_db),
    _: str = Depends(verify_api_key),
):
    """Update stop loss and take profit levels"""
    position = db.query(Position).filter(Position.id == position_id).first()
    if not position:
        raise HTTPException(status_code=404, detail="Position not found")

    if stop_loss:
        position.stop_loss = stop_loss
    if take_profit:
        position.take_profit = take_profit

    db.commit()

    return {
        "success": True,
        "position_id": position_id,
        "stop_loss": str(position.stop_loss) if position.stop_loss else None,
        "take_profit": str(position.take_profit) if position.take_profit else None,
    }


def _position_to_response(position: Position) -> PositionResponse:
    """Convert Position model to response"""
    return PositionResponse(
        id=str(position.id),
        symbol=position.symbol,
        position_type=position.position_type.value
        if hasattr(position.position_type, "value")
        else position.position_type,
        quantity=str(position.quantity),
        avg_entry_price=str(position.avg_entry_price),
        current_price=str(position.current_price) if position.current_price else None,
        unrealized_pnl=str(position.unrealized_pnl) if position.unrealized_pnl else None,
        realized_pnl=str(position.realized_pnl),
        stop_loss=str(position.stop_loss) if position.stop_loss else None,
        take_profit=str(position.take_profit) if position.take_profit else None,
        is_open=position.is_open,
        opened_at=position.opened_at.isoformat() if position.opened_at else None,
    )
