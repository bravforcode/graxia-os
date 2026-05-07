"""
Revenue OS — Analytics API
Revenue metrics, dashboards, and reports
"""
from decimal import Decimal
from typing import Dict, List, Optional
from datetime import datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, and_, desc, cast, Date

from ..db import get_db
from ..models import Order, Product, Customer
from ..enums import OrderStatus

router = APIRouter()

# ── Schemas ──
from pydantic import BaseModel

class RevenueMetrics(BaseModel):
    period: str
    total_revenue: float
    total_orders: int
    average_order_value: float
    unique_customers: int
    conversion_rate: Optional[float] = None
    refund_rate: float
    refund_amount: float
    net_revenue: float

class DailyRevenue(BaseModel):
    date: str
    revenue: float
    orders: int

class RevenueTrend(BaseModel):
    period: str
    current_revenue: float
    previous_revenue: float
    change_percent: float
    trend: str  # "up", "down", "flat"

class TopProduct(BaseModel):
    product_id: str
    product_name: str
    quantity_sold: int
    revenue: float

class DashboardSummary(BaseModel):
    today: RevenueMetrics
    this_week: RevenueMetrics
    this_month: RevenueMetrics
    trend: RevenueTrend
    top_products: List[TopProduct]
    
# ── Endpoints ──

@router.get("/dashboard", response_model=DashboardSummary)
async def get_dashboard_summary(
    db: AsyncSession = Depends(get_db)
):
    """Get full dashboard summary"""
    today = datetime.utcnow().date()
    
    # Simplified metrics (would query real data in production)
    today_metrics = RevenueMetrics(
        period=today.isoformat(),
        total_revenue=0.0,
        total_orders=0,
        average_order_value=0.0,
        unique_customers=0,
        refund_rate=0.0,
        refund_amount=0.0,
        net_revenue=0.0
    )
    
    return DashboardSummary(
        today=today_metrics,
        this_week=today_metrics,
        this_month=today_metrics,
        trend=RevenueTrend(
            period="month",
            current_revenue=0.0,
            previous_revenue=0.0,
            change_percent=0.0,
            trend="flat"
        ),
        top_products=[]
    )


@router.get("/revenue/daily")
async def get_daily_revenue(
    start_date: datetime = Query(...),
    end_date: datetime = Query(...),
    db: AsyncSession = Depends(get_db)
):
    """Get daily revenue breakdown"""
    # Query daily aggregations
    query = (
        select(
            cast(Order.created_at, Date).label("date"),
            func.sum(Order.total_amount).label("revenue"),
            func.count(Order.id).label("orders")
        )
        .where(
            and_(
                Order.created_at >= start_date,
                Order.created_at <= end_date,
                Order.status.in_([OrderStatus.COMPLETED, OrderStatus.PAID])
            )
        )
        .group_by(cast(Order.created_at, Date))
        .order_by("date")
    )
    
    result = await db.execute(query)
    rows = result.fetchall()
    
    return [
        {
            "date": str(row.date),
            "revenue": float(row.revenue) if row.revenue else 0.0,
            "orders": row.orders
        }
        for row in rows
    ]


@router.get("/metrics")
async def get_revenue_metrics(
    start_date: datetime = Query(...),
    end_date: datetime = Query(...),
    db: AsyncSession = Depends(get_db)
):
    """Get comprehensive revenue metrics for period"""
    
    # Total revenue
    revenue_query = (
        select(func.sum(Order.total_amount))
        .where(
            and_(
                Order.created_at >= start_date,
                Order.created_at <= end_date,
                Order.status.in_([OrderStatus.COMPLETED, OrderStatus.PAID])
            )
        )
    )
    revenue_result = await db.execute(revenue_query)
    total_revenue = float(revenue_result.scalar() or 0)
    
    # Total orders
    orders_query = (
        select(func.count(Order.id))
        .where(
            and_(
                Order.created_at >= start_date,
                Order.created_at <= end_date
            )
        )
    )
    orders_result = await db.execute(orders_query)
    total_orders = orders_result.scalar() or 0
    
    # Refunds
    refund_query = (
        select(func.sum(Order.total_amount))
        .where(
            and_(
                Order.created_at >= start_date,
                Order.created_at <= end_date,
                Order.status == OrderStatus.REFUNDED
            )
        )
    )
    refund_result = await db.execute(refund_query)
    refund_amount = float(refund_result.scalar() or 0)
    
    return {
        "period": {
            "start": start_date.isoformat(),
            "end": end_date.isoformat()
        },
        "total_revenue": total_revenue,
        "total_orders": total_orders,
        "average_order_value": total_revenue / total_orders if total_orders > 0 else 0,
        "refund_amount": refund_amount,
        "refund_rate": refund_amount / total_revenue if total_revenue > 0 else 0,
        "net_revenue": total_revenue - refund_amount
    }


@router.get("/reports/monthly")
async def get_monthly_report(
    year: int = Query(..., ge=2020, le=2030),
    month: int = Query(..., ge=1, le=12),
    db: AsyncSession = Depends(get_db)
):
    """Get monthly revenue report"""
    start_date = datetime(year, month, 1)
    if month == 12:
        end_date = datetime(year + 1, 1, 1)
    else:
        end_date = datetime(year, month + 1, 1)
    
    # Would calculate real metrics here
    return {
        "year": year,
        "month": month,
        "total_revenue": 0.0,
        "total_orders": 0,
        "new_customers": 0,
        "refund_rate": 0.0,
        "top_products": []
    }
