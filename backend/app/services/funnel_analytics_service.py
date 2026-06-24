import logging
from datetime import datetime, date
from typing import Any, Dict, List, Optional
from uuid import UUID

from sqlalchemy import select, and_, func, desc, Date
from sqlalchemy.ext.asyncio import AsyncSession
from app.models.funnel import ConversionEvent, FunnelOrder, DigitalProduct

logger = logging.getLogger(__name__)

class FunnelAnalyticsService:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def log_event(
        self,
        organization_id: UUID,
        event_type: str,
        product_id: Optional[UUID] = None,
        contact_id: Optional[UUID] = None,
        order_id: Optional[UUID] = None,
        session_id: Optional[str] = None,
        source: Optional[str] = None,
        medium: Optional[str] = None,
        campaign: Optional[str] = None,
        referrer: Optional[str] = None,
        metadata_json: Optional[Dict[str, Any]] = None,
    ) -> ConversionEvent:
        """
        Logs a conversion event for tracking funnel analytics.
        """
        # Validate event type against model constraint:
        valid_types = {
            "page_view",
            "lead_capture",
            "checkout_start",
            "checkout_success",
            "purchase",
            "delivery_opened",
        }
        if event_type not in valid_types:
            raise ValueError(f"Invalid event type: {event_type}")

        event = ConversionEvent(
            organization_id=organization_id,
            event_type=event_type,
            product_id=product_id,
            contact_id=contact_id,
            order_id=order_id,
            session_id=session_id,
            source=source,
            medium=medium,
            campaign=campaign,
            referrer=referrer,
            metadata_json=metadata_json or {},
            occurred_at=datetime.utcnow(),
        )
        self.db.add(event)
        await self.db.commit()
        await self.db.refresh(event)
        return event

    async def get_analytics_summary(
        self,
        organization_id: UUID,
        product_id: Optional[UUID] = None,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
    ) -> Dict[str, Any]:
        """
        Computes key conversion funnel metrics for an organization.
        """
        # Base filter
        filters = [ConversionEvent.organization_id == organization_id]
        if product_id:
            filters.append(ConversionEvent.product_id == product_id)
        if start_date:
            filters.append(ConversionEvent.occurred_at >= start_date)
        if end_date:
            filters.append(ConversionEvent.occurred_at <= end_date)

        # Count events by type
        stmt = (
            select(ConversionEvent.event_type, func.count(ConversionEvent.id))
            .where(and_(*filters))
            .group_by(ConversionEvent.event_type)
        )
        res = await self.db.execute(stmt)
        counts = {row[0]: row[1] for row in res.all()}

        views = counts.get("page_view", 0)
        leads = counts.get("lead_capture", 0)
        checkout_starts = counts.get("checkout_start", 0)
        purchases = counts.get("purchase", 0)
        delivery_opened = counts.get("delivery_opened", 0)

        # Let's count unique visitors (sessions) for views
        stmt_visitors = (
            select(func.count(func.distinct(ConversionEvent.session_id)))
            .where(and_(
                ConversionEvent.organization_id == organization_id,
                ConversionEvent.event_type == "page_view",
                *( [ConversionEvent.product_id == product_id] if product_id else [] ),
                *( [ConversionEvent.occurred_at >= start_date] if start_date else [] ),
                *( [ConversionEvent.occurred_at <= end_date] if end_date else [] ),
            ))
        )
        res_visitors = await self.db.execute(stmt_visitors)
        unique_visitors = res_visitors.scalar() or 0

        # Calculate conversion rates
        lead_conversion_rate = (leads / views * 100.0) if views > 0 else 0.0
        checkout_rate = (checkout_starts / views * 100.0) if views > 0 else 0.0
        purchase_conversion_rate = (purchases / views * 100.0) if views > 0 else 0.0
        checkout_to_purchase_rate = (purchases / checkout_starts * 100.0) if checkout_starts > 0 else 0.0

        # Sum total revenue and order counts from FunnelOrder
        order_filters = [
            FunnelOrder.organization_id == organization_id,
            FunnelOrder.status == "paid",
        ]
        if start_date:
            order_filters.append(FunnelOrder.paid_at >= start_date)
        if end_date:
            order_filters.append(FunnelOrder.paid_at <= end_date)

        # If product_id is specified, we filter by orders containing that product
        if product_id:
            from app.models.funnel import FunnelOrderItem
            order_stmt = (
                select(func.sum(FunnelOrderItem.total_amount), func.count(func.distinct(FunnelOrder.id)))
                .select_from(FunnelOrder)
                .join(FunnelOrderItem, FunnelOrderItem.order_id == FunnelOrder.id)
                .where(and_(
                    *order_filters,
                    FunnelOrderItem.product_id == product_id
                ))
            )
        else:
            order_stmt = (
                select(func.sum(FunnelOrder.total_amount), func.count(FunnelOrder.id))
                .where(and_(*order_filters))
            )
            
        order_res = await self.db.execute(order_stmt)
        total_revenue_val, sales_count = order_res.first() or (0.0, 0)
        total_revenue = float(total_revenue_val or 0.0)

        # Average Order Value (AOV)
        aov = (total_revenue / sales_count) if sales_count > 0 else 0.0

        return {
            "views": views,
            "unique_visitors": unique_visitors,
            "leads": leads,
            "checkout_starts": checkout_starts,
            "purchases": purchases,
            "delivery_opened": delivery_opened,
            "lead_conversion_rate": round(lead_conversion_rate, 2),
            "checkout_rate": round(checkout_rate, 2),
            "purchase_conversion_rate": round(purchase_conversion_rate, 2),
            "checkout_to_purchase_rate": round(checkout_to_purchase_rate, 2),
            "sales_count": sales_count,
            "total_revenue": round(total_revenue, 2),
            "average_order_value": round(aov, 2),
        }

    async def get_daily_analytics(
        self,
        organization_id: UUID,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
    ) -> List[Dict[str, Any]]:
        """
        Aggregates daily funnel activity: page views, lead captures, purchases, and revenue.
        """
        # Daily metrics computed using SQL date grouping
        # SQLite uses strftime('%Y-%m-%d', occurred_at)
        # PostgreSQL uses func.date_trunc('day', occurred_at)
        # Let's write a database-agnostic/SQLite-compatible representation
        
        # Determine the date grouping expression:
        # We can detect engine name or use date(ConversionEvent.occurred_at)
        date_expr = func.date(ConversionEvent.occurred_at)

        filters = [ConversionEvent.organization_id == organization_id]
        if start_date:
            filters.append(ConversionEvent.occurred_at >= start_date)
        if end_date:
            filters.append(ConversionEvent.occurred_at <= end_date)

        # Query events grouped by day and type
        stmt = (
            select(
                date_expr.label("day"),
                ConversionEvent.event_type,
                func.count(ConversionEvent.id),
            )
            .where(and_(*filters))
            .group_by(date_expr, ConversionEvent.event_type)
            .order_by("day")
        )
        res = await self.db.execute(stmt)
        rows = res.all()

        daily_data = {}
        for row in rows:
            day_str = str(row[0])
            event_type = row[1]
            count = row[2]
            if day_str not in daily_data:
                daily_data[day_str] = {
                    "date": day_str,
                    "views": 0,
                    "leads": 0,
                    "purchases": 0,
                    "revenue": 0.0,
                }
            if event_type == "page_view":
                daily_data[day_str]["views"] = count
            elif event_type == "lead_capture":
                daily_data[day_str]["leads"] = count
            elif event_type == "purchase":
                daily_data[day_str]["purchases"] = count

        # Load daily revenue
        order_date_expr = func.date(FunnelOrder.paid_at)
        order_filters = [
            FunnelOrder.organization_id == organization_id,
            FunnelOrder.status == "paid",
        ]
        if start_date:
            order_filters.append(FunnelOrder.paid_at >= start_date)
        if end_date:
            order_filters.append(FunnelOrder.paid_at <= end_date)

        order_stmt = (
            select(
                order_date_expr.label("day"),
                func.sum(FunnelOrder.total_amount),
            )
            .where(and_(*order_filters))
            .group_by(order_date_expr)
        )
        order_res = await self.db.execute(order_stmt)
        for row in order_res.all():
            day_str = str(row[0])
            rev = float(row[1] or 0.0)
            if day_str not in daily_data:
                daily_data[day_str] = {
                    "date": day_str,
                    "views": 0,
                    "leads": 0,
                    "purchases": 0,
                    "revenue": 0.0,
                }
            daily_data[day_str]["revenue"] = round(rev, 2)

        return sorted(list(daily_data.values()), key=lambda x: x["date"])
