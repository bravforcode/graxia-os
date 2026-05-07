"""Order management API endpoints"""

from typing import List, Optional
from decimal import Decimal
from datetime import datetime

from fastapi import APIRouter, HTTPException, Depends, Query
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from ..data.models import Order as OrderModel, OrderStateHistory
from ..core.enums import OrderStatus, OrderSide, OrderType


orders_router = APIRouter(prefix="/orders", tags=["orders"])


class OrderCreateRequest(BaseModel):
    """Create order request"""
    symbol: str = Field(..., example="EURUSD")
    side: OrderSide
    order_type: OrderType = OrderType.MARKET
    quantity: Decimal = Field(..., gt=0, example=0.01)
    price: Optional[Decimal] = Field(None, example=1.0850)
    stop_price: Optional[Decimal] = Field(None, example=1.0820)
    strategy_id: str = Field(default="manual", example="manual")


class OrderResponse(BaseModel):
    """Order response"""
    id: str
    symbol: str
    side: str
    status: str
    quantity: str
    fill_quantity: str
    avg_fill_price: Optional[str]
    strategy_id: str
    trading_mode: str
    created_at: str

    class Config:
        from_attributes = True


class OrderListResponse(BaseModel):
    """List of orders"""
    orders: List[OrderResponse]
    total: int


@orders_router.post("/", response_model=OrderResponse)
async def create_order(
    request: OrderCreateRequest,
    db: AsyncSession = Depends(get_db)
):
    """Create a new order"""
    # This would integrate with OrderManager
    # For now, return placeholder
    raise HTTPException(status_code=501, detail="Not implemented - use webhook endpoint")


@orders_router.get("/", response_model=OrderListResponse)
async def list_orders(
    status: Optional[OrderStatus] = None,
    symbol: Optional[str] = None,
    strategy_id: Optional[str] = None,
    limit: int = Query(50, ge=1, le=100),
    offset: int = Query(0, ge=0),
    db: AsyncSession = Depends(get_db)
):
    """List orders with optional filters"""
    query = db.query(OrderModel)

    if status:
        query = query.filter(OrderModel.status == status)
    if symbol:
        query = query.filter(OrderModel.symbol == symbol.upper())
    if strategy_id:
        query = query.filter(OrderModel.strategy_id == strategy_id)

    total = query.count()
    orders = query.order_by(OrderModel.created_at.desc()).offset(offset).limit(limit).all()

    return OrderListResponse(
        orders=[_order_to_response(o) for o in orders],
        total=total
    )


@orders_router.get("/{order_id}", response_model=OrderResponse)
async def get_order(order_id: str, db: Session = Depends(get_db)):
    """Get order by ID"""
    order = db.query(OrderModel).filter(OrderModel.id == order_id).first()
    if not order:
        raise HTTPException(status_code=404, detail="Order not found")
    return _order_to_response(order)


@orders_router.post("/{order_id}/cancel")
async def cancel_order(order_id: str, db: Session = Depends(get_db)):
    """Cancel an order"""
    order = db.query(OrderModel).filter(OrderModel.id == order_id).first()
    if not order:
        raise HTTPException(status_code=404, detail="Order not found")

    # Check if cancellable
    if order.status in [OrderStatus.FILLED.value, OrderStatus.CANCELLED.value,
                        OrderStatus.REJECTED.value, OrderStatus.EXPIRED.value]:
        raise HTTPException(status_code=400, detail=f"Order cannot be cancelled (status: {order.status})")

    # Would integrate with OrderManager to cancel
    order.status = OrderStatus.CANCEL_REQUESTED.value
    order.updated_at = datetime.utcnow()
    db.commit()

    return {"success": True, "order_id": order_id, "status": "cancel_requested"}


@orders_router.post("/{order_id}/approve")
async def approve_order(
    order_id: str,
    approver: str = "admin",
    db: AsyncSession = Depends(get_db)
):
    """Approve a MICRO mode order (human approval)"""
    order = db.query(OrderModel).filter(OrderModel.id == order_id).first()
    if not order:
        raise HTTPException(status_code=404, detail="Order not found")

    if order.status != OrderStatus.PENDING_HUMAN.value:
        raise HTTPException(status_code=400, detail=f"Order not in PENDING_HUMAN state (status: {order.status})")

    # Would integrate with OrderManager to approve and submit
    order.approved_by = approver
    db.commit()

    return {"success": True, "order_id": order_id, "approved_by": approver}


def _order_to_response(order: OrderModel) -> OrderResponse:
    """Convert Order model to response"""
    return OrderResponse(
        id=str(order.id),
        symbol=order.symbol,
        side=order.side.value if hasattr(order.side, 'value') else order.side,
        status=order.status.value if hasattr(order.status, 'value') else order.status,
        quantity=str(order.quantity),
        fill_quantity=str(order.fill_quantity),
        avg_fill_price=str(order.avg_fill_price) if order.avg_fill_price else None,
        strategy_id=order.strategy_id,
        trading_mode=order.trading_mode,
        created_at=order.created_at.isoformat() if order.created_at else None
    )


# Database dependency - use shared session from Revenue OS
from graxia.packages.revenue_os.db import get_db as _get_db

async def get_db():
    """Database session dependency"""
    async for session in _get_db():
        yield session
