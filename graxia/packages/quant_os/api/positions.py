"""Positions API endpoints"""

from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException
from fastapi.security import HTTPBearer
from pydantic import BaseModel, ConfigDict
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Session

# Database dependency - use shared session from Revenue OS
from graxia.packages.revenue_os.db import get_db as _get_db

from ..core.enums import CloseReason
from ..data.models import Position

security = HTTPBearer()


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
async def list_positions(is_open: bool | None = True, symbol: str | None = None, db: AsyncSession = Depends(get_db)):
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
async def get_position(position_id: str, db: Session = Depends(get_db)):
    """Get position by ID"""
    position = db.query(Position).filter(Position.id == position_id).first()
    if not position:
        raise HTTPException(status_code=404, detail="Position not found")
    return _position_to_response(position)


@positions_router.get("/symbol/{symbol}", response_model=PositionResponse)
async def get_position_by_symbol(symbol: str, db: Session = Depends(get_db)):
    """Get position by symbol"""
    position = db.query(Position).filter(Position.symbol == symbol.upper(), Position.is_open == True).first()
    if not position:
        raise HTTPException(status_code=404, detail="No open position found for symbol")
    return _position_to_response(position)


@positions_router.post("/{position_id}/close")
async def close_position(
    position_id: str,
    reason: CloseReason = CloseReason.MANUAL,
    db: AsyncSession = Depends(get_db),
    credentials=Depends(security),
):
    """Close a position"""
    position = db.query(Position).filter(Position.id == position_id).first()
    if not position:
        raise HTTPException(status_code=404, detail="Position not found")

    if not position.is_open:
        raise HTTPException(status_code=400, detail="Position already closed")

    # Would integrate with OrderManager to submit closing order
    return {"success": True, "position_id": position_id, "message": "Close order submitted", "reason": reason.value}


@positions_router.post("/{position_id}/update-stops")
async def update_stops(
    position_id: str,
    stop_loss: Decimal | None = None,
    take_profit: Decimal | None = None,
    db: AsyncSession = Depends(get_db),
    credentials=Depends(security),
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
