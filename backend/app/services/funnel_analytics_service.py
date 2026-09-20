import logging
from datetime import UTC, datetime, date, timedelta
from decimal import Decimal, InvalidOperation
from typing import Any, Dict, List, Mapping, Optional
from uuid import UUID
from urllib.parse import urlsplit

from sqlalchemy import select, and_, func, desc, Date
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.exc import IntegrityError
from app.models.contact import Contact
from app.models.funnel import ConversionEvent, FunnelOrder, DigitalProduct
from app.models.revenue_bridge import RevenueBridgeEvent

logger = logging.getLogger(__name__)

class FunnelAnalyticsService:
    def __init__(self, db: AsyncSession):
        self.db = db

    @staticmethod
    def _verified_event_amount(event: ConversionEvent) -> Decimal:
        metadata = event.metadata_json or {}
        if event.event_type != "purchase" or event.order_id is not None:
            return Decimal("0")
        if metadata.get("verified") is not True:
            return Decimal("0")
        try:
            amount = Decimal(str(metadata.get("verified_amount")))
        except (InvalidOperation, TypeError, ValueError):
            return Decimal("0")
        return max(amount, Decimal("0"))

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
        first_touch: Optional[Mapping[str, Any]] = None,
        last_touch: Optional[Mapping[str, Any]] = None,
        landing_path: Optional[str] = None,
        content_id: Optional[str] = None,
        referral_code: Optional[str] = None,
        metadata_json: Optional[Dict[str, Any]] = None,
        idempotency_key: Optional[str] = None,
        public: bool = False,
    ) -> ConversionEvent:
        """
        Logs a conversion event for tracking funnel analytics.
        """
        if public:
            from app.services.public_funnel_service import require_public_funnel_organization

            organization_id = require_public_funnel_organization(organization_id)

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
        if public and event_type == "purchase":
            raise ValueError("Purchase events require verified server evidence")

        if public:
            # Public clients may identify a resource only inside the bound
            # tenant. This prevents a caller from attaching an event to an
            # object belonging to another organization.
            checks = (
                (DigitalProduct, product_id, "product"),
                (Contact, contact_id, "contact"),
                (FunnelOrder, order_id, "order"),
            )
            for model, resource_id, label in checks:
                if resource_id is None:
                    continue
                resource = await self.db.scalar(
                    select(model.id).where(
                        model.id == resource_id,
                        model.organization_id == organization_id,
                    )
                )
                if resource is None:
                    raise ValueError(f"Unknown public funnel {label}")

        if idempotency_key:
            existing = await self.db.scalar(
                select(ConversionEvent).where(
                    ConversionEvent.organization_id == organization_id,
                    ConversionEvent.idempotency_key == idempotency_key,
                )
            )
            if existing:
                return existing

        allowed_metadata = {
            "cta", "content_id", "path", "plan", "channel", "locale",
            "lead_magnet_id", "lead_magnet_slug", "landing_path", "referral_code",
            "provider", "provider_event_id", "event_kind", "currency",
            "verified_amount", "verified", "verified_provider_event",
        }
        safe_metadata = {}
        for key, value in (metadata_json or {}).items():
            if key not in allowed_metadata or value is None:
                continue
            if key in {"verified", "verified_provider_event"} and isinstance(value, bool):
                safe_metadata[str(key)] = value
                continue
            safe_value = self._safe_value(value, 200)
            if safe_value is not None:
                safe_metadata[str(key)] = safe_value

        first = self._sanitize_touch(first_touch)
        last = self._sanitize_touch(last_touch)
        source = self._safe_value(source, 100) or last.get("source")
        medium = self._safe_value(medium, 100) or last.get("medium")
        campaign = self._safe_value(campaign, 100) or last.get("campaign")
        referrer = self._safe_referrer(referrer) or last.get("referrer")
        landing_path = self._safe_path(
            landing_path or (metadata_json or {}).get("landing_path")
        ) or first.get("path")
        content_id = self._safe_value(
            content_id or (metadata_json or {}).get("content_id"), 255
        )
        referral_code = self._safe_value(
            referral_code or (metadata_json or {}).get("referral_code"), 160
        )

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
            first_touch_source=first.get("source"),
            first_touch_medium=first.get("medium"),
            first_touch_campaign=first.get("campaign"),
            first_touch_referrer=first.get("referrer"),
            first_touch_path=first.get("path"),
            last_touch_source=last.get("source") or source,
            last_touch_medium=last.get("medium") or medium,
            last_touch_campaign=last.get("campaign") or campaign,
            last_touch_referrer=last.get("referrer") or referrer,
            last_touch_path=last.get("path"),
            landing_path=landing_path,
            content_id=content_id,
            referral_code=referral_code,
            metadata_json=safe_metadata,
            idempotency_key=idempotency_key,
            occurred_at=datetime.utcnow(),
        )
        self.db.add(event)
        try:
            await self.db.commit()
        except IntegrityError:
            await self.db.rollback()
            if idempotency_key:
                existing = await self.db.scalar(
                    select(ConversionEvent).where(
                        ConversionEvent.organization_id == organization_id,
                        ConversionEvent.idempotency_key == idempotency_key,
                    )
                )
                if existing:
                    return existing
            raise
        await self.db.refresh(event)
        return event

    @staticmethod
    def _safe_value(value: Any, limit: int) -> str | None:
        if value is None:
            return None
        normalized = str(value).strip()
        if not normalized or "@" in normalized:
            return None
        return normalized[:limit]

    @classmethod
    def _safe_referrer(cls, value: Any) -> str | None:
        if value is None:
            return None
        raw = str(value).strip()
        if not raw:
            return None
        parsed = urlsplit(raw)
        if parsed.netloc:
            return cls._safe_value(
                f"{parsed.scheme}://{parsed.netloc}{parsed.path}", 2000
            )
        if parsed.path.startswith("/"):
            return cls._safe_value(parsed.path, 2000)
        return None

    @classmethod
    def _safe_path(cls, value: Any) -> str | None:
        if value is None:
            return None
        raw = str(value).strip()
        parsed = urlsplit(raw)
        path = parsed.path if parsed.scheme or parsed.netloc else raw
        return cls._safe_value(path, 500)

    @classmethod
    def _sanitize_touch(cls, touch: Optional[Mapping[str, Any]]) -> dict[str, str]:
        if not touch:
            return {}
        return {
            key: value
            for key, value in {
                "source": cls._safe_value(touch.get("source"), 100),
                "medium": cls._safe_value(touch.get("medium"), 100),
                "campaign": cls._safe_value(touch.get("campaign"), 100),
                "referrer": cls._safe_referrer(touch.get("referrer")),
                "path": cls._safe_path(touch.get("path")),
            }.items()
            if value is not None
        }

    async def get_attribution_summary(
        self,
        organization_id: UUID,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
    ) -> List[Dict[str, Any]]:
        """Group funnel outcomes by attribution and product without exposing PII."""
        filters = [ConversionEvent.organization_id == organization_id]
        if start_date:
            filters.append(ConversionEvent.occurred_at >= start_date)
        if end_date:
            filters.append(ConversionEvent.occurred_at <= end_date)

        stmt = (
            select(ConversionEvent, FunnelOrder.total_amount, DigitalProduct.name)
            .select_from(ConversionEvent)
            .outerjoin(
                FunnelOrder,
                and_(
                    FunnelOrder.id == ConversionEvent.order_id,
                    FunnelOrder.status == "paid",
                    FunnelOrder.refunded_at.is_(None),
                ),
            )
            .outerjoin(DigitalProduct, DigitalProduct.id == ConversionEvent.product_id)
            .where(and_(*filters))
            .order_by(ConversionEvent.occurred_at)
        )
        result = await self.db.execute(stmt)
        grouped: Dict[tuple, Dict[str, Any]] = {}
        for event, order_total, product_name in result.all():
            metadata = event.metadata_json or {}
            plan = metadata.get("plan")
            key = (
                event.source, event.medium, event.campaign,
                event.product_id, plan,
            )
            row = grouped.setdefault(
                key,
                {
                    "source": event.source,
                    "medium": event.medium,
                    "campaign": event.campaign,
                    "product_id": event.product_id,
                    "product_name": product_name,
                    "plan": plan,
                    "views": 0,
                    "leads": 0,
                    "checkout_starts": 0,
                    "purchases": 0,
                    "revenue": 0.0,
                },
            )
            if event.event_type == "page_view":
                row["views"] += 1
            elif event.event_type == "lead_capture":
                row["leads"] += 1
            elif event.event_type in {"checkout_start", "checkout_success"}:
                row["checkout_starts"] += 1
            elif event.event_type == "purchase":
                row["purchases"] += 1
                row["revenue"] += float(
                    order_total if order_total is not None
                    else self._verified_event_amount(event)
                )

        for row in grouped.values():
            row["revenue"] = round(row["revenue"], 2)
        return list(grouped.values())

    async def get_dashboard(
        self,
        organization_id: UUID,
        *,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
        source: Optional[str] = None,
        medium: Optional[str] = None,
        campaign: Optional[str] = None,
        product_id: Optional[UUID] = None,
        plan: Optional[str] = None,
        referral_code: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Return a tenant-safe, evidence-labelled conversion dashboard."""
        def as_utc(value: Optional[datetime]) -> Optional[datetime]:
            if value is None or value.tzinfo is not None:
                return value
            return value.replace(tzinfo=UTC)

        start_date = as_utc(start_date)
        end_date = as_utc(end_date)
        now = datetime.now(UTC)
        effective_end = end_date or now
        effective_start = start_date or (effective_end - timedelta(days=90))
        if start_date is None and end_date is not None:
            effective_start = end_date - timedelta(days=90)
        elif start_date is not None and end_date is None:
            effective_end = min(now, start_date + timedelta(days=90))

        if effective_end < effective_start:
            raise ValueError("Dashboard end date must be after start date")
        if effective_end - effective_start > timedelta(days=90):
            raise ValueError("Dashboard date range cannot exceed 90 days")

        event_filters = [
            ConversionEvent.organization_id == organization_id,
            ConversionEvent.occurred_at >= effective_start,
            ConversionEvent.occurred_at <= effective_end,
        ]
        if source is not None:
            event_filters.append(ConversionEvent.source == source)
        if medium is not None:
            event_filters.append(ConversionEvent.medium == medium)
        if campaign is not None:
            event_filters.append(ConversionEvent.campaign == campaign)
        if product_id is not None:
            event_filters.append(ConversionEvent.product_id == product_id)
        event_result = await self.db.execute(
            select(ConversionEvent, DigitalProduct.name)
            .select_from(ConversionEvent)
            .outerjoin(DigitalProduct, DigitalProduct.id == ConversionEvent.product_id)
            .where(and_(*event_filters))
        )
        event_rows = []
        for event, product_name in event_result.all():
            event_plan = (event.metadata_json or {}).get("plan")
            if plan is not None and event_plan != plan:
                continue
            if referral_code is not None and event.referral_code != referral_code:
                continue
            event_rows.append((event, product_name))

        order_ids = {
            event.order_id
            for event, _ in event_rows
            if event.event_type == "purchase" and event.order_id is not None
        }
        paid_orders: dict[UUID, FunnelOrder] = {}
        if order_ids:
            paid_order_result = await self.db.execute(
                select(FunnelOrder).where(
                    FunnelOrder.organization_id == organization_id,
                    FunnelOrder.id.in_(order_ids),
                    FunnelOrder.status == "paid",
                    FunnelOrder.refunded_at.is_(None),
                    FunnelOrder.paid_at >= effective_start,
                    FunnelOrder.paid_at <= effective_end,
                )
            )
            paid_orders = {order.id: order for order in paid_order_result.scalars().all()}

        refund_filters = [
            FunnelOrder.organization_id == organization_id,
            FunnelOrder.status == "refunded",
            FunnelOrder.refunded_at.isnot(None),
            FunnelOrder.refunded_at >= effective_start,
            FunnelOrder.refunded_at <= effective_end,
        ]
        if order_ids:
            refund_filters.append(FunnelOrder.id.in_(order_ids))
        refund_result = await self.db.execute(
            select(FunnelOrder).where(and_(*refund_filters))
        )
        refunded_orders = list(refund_result.scalars().all())

        def verified_purchase_amount(event: ConversionEvent) -> Decimal:
            if event.order_id is not None:
                order = paid_orders.get(event.order_id)
                return Decimal(str(order.total_amount)) if order else Decimal("0")
            return self._verified_event_amount(event)

        counts = {event_type: 0 for event_type in (
            "page_view", "lead_capture", "checkout_start", "purchase", "delivery_opened"
        )}
        for event, _ in event_rows:
            if event.event_type in counts:
                counts[event.event_type] += 1
        views = counts["page_view"]
        leads = counts["lead_capture"]
        checkout_starts = counts["checkout_start"]
        purchases = counts["purchase"]
        unique_visitors = len({
            event.session_id for event, _ in event_rows
            if event.event_type == "page_view" and event.session_id
        })
        bridge_purchase_events = [
            event for event, _ in event_rows
            if event.event_type == "purchase"
            and event.order_id is None
            and self._verified_event_amount(event) > Decimal("0")
        ]
        total_revenue = sum(
            (order.total_amount for order in paid_orders.values()), Decimal("0")
        ) + sum(
            (self._verified_event_amount(event) for event in bridge_purchase_events),
            Decimal("0"),
        )
        sales_count = len(paid_orders) + len(bridge_purchase_events)
        funnel = {
            "views": views,
            "unique_visitors": unique_visitors,
            "leads": leads,
            "checkout_starts": checkout_starts,
            "purchases": purchases,
            "delivery_opened": counts["delivery_opened"],
            "lead_conversion_rate": round(leads / views * 100, 2) if views else 0.0,
            "checkout_rate": round(checkout_starts / views * 100, 2) if views else 0.0,
            "purchase_conversion_rate": round(purchases / views * 100, 2) if views else 0.0,
            "checkout_to_purchase_rate": round(purchases / checkout_starts * 100, 2)
            if checkout_starts else 0.0,
            "sales_count": sales_count,
            "total_revenue": round(float(total_revenue), 2),
            "average_order_value": round(float(total_revenue) / sales_count, 2)
            if sales_count else 0.0,
        }

        def blank_row(**values: Any) -> dict[str, Any]:
            return {
                "source": None, "medium": None, "campaign": None,
                "product_id": None, "product_name": None, "plan": None,
                "views": 0, "leads": 0, "checkout_starts": 0,
                "purchases": 0, "revenue": 0.0, **values,
            }

        def add_event(row: dict[str, Any], event: ConversionEvent) -> None:
            if event.event_type == "page_view":
                row["views"] += 1
            elif event.event_type == "lead_capture":
                row["leads"] += 1
            elif event.event_type in {"checkout_start", "checkout_success"}:
                row["checkout_starts"] += 1
            elif event.event_type == "purchase":
                row["purchases"] += 1
                row["revenue"] += float(verified_purchase_amount(event))

        grouped: dict[tuple[Any, ...], dict[str, Any]] = {}
        by_source: dict[tuple[Any, ...], dict[str, Any]] = {}
        by_product: dict[tuple[Any, ...], dict[str, Any]] = {}
        by_plan: dict[tuple[Any, ...], dict[str, Any]] = {}
        for event, product_name in event_rows:
            metadata = event.metadata_json or {}
            event_plan = metadata.get("plan")
            full_key = (event.source, event.medium, event.campaign, event.product_id, event_plan)
            source_key = (event.source, event.medium, event.campaign)
            product_key = (event.product_id, product_name)
            plan_key = (event_plan,)
            for target, key, values in (
                (grouped, full_key, {
                    "source": event.source, "medium": event.medium,
                    "campaign": event.campaign, "product_id": event.product_id,
                    "product_name": product_name, "plan": event_plan,
                }),
                (by_source, source_key, {
                    "source": event.source, "medium": event.medium,
                    "campaign": event.campaign,
                }),
                (by_product, product_key, {
                    "product_id": event.product_id, "product_name": product_name,
                }),
                (by_plan, plan_key, {"plan": event_plan}),
            ):
                row = target.setdefault(key, blank_row(**values))
                add_event(row, event)
        for collection in (grouped, by_source, by_product, by_plan):
            for row in collection.values():
                row["revenue"] = round(row["revenue"], 2)

        bridge_filters = [
            RevenueBridgeEvent.organization_id == organization_id,
            RevenueBridgeEvent.event_kind == "subscription_activated",
            RevenueBridgeEvent.occurred_at >= effective_start,
            RevenueBridgeEvent.occurred_at <= effective_end,
        ]
        bridge_events = (
            await self.db.execute(select(RevenueBridgeEvent).where(and_(*bridge_filters)))
        ).scalars().all()
        if any(value is not None for value in (source, medium, campaign, product_id, plan, referral_code)):
            matching_provider_ids = {
                (event.metadata_json or {}).get("provider_event_id")
                for event, _ in event_rows
                if (event.metadata_json or {}).get("verified_provider_event") is True
            }
            bridge_events = [
                event for event in bridge_events
                if event.provider_event_id in matching_provider_ids
            ]

        purchase_rows = [
            event for event, _ in event_rows
            if event.event_type == "purchase" and verified_purchase_amount(event) > Decimal("0")
        ]
        referral_totals: dict[str, dict[str, Any]] = {}
        for event in purchase_rows:
            key = event.referral_code or "unattributed"
            row = referral_totals.setdefault(key, {"referral_code": key, "purchases": 0, "revenue": 0.0})
            row["purchases"] += 1
            row["revenue"] += float(verified_purchase_amount(event))
        for row in referral_totals.values():
            row["revenue"] = round(row["revenue"], 2)

        attributed = sum(1 for event in event_rows if event.source or event.referral_code)
        return {
            "period": {"start": effective_start, "end": effective_end, "max_days": 90},
            "funnel": funnel,
            "rates": {
                key: funnel[key]
                for key in (
                    "lead_conversion_rate", "checkout_rate",
                    "purchase_conversion_rate", "checkout_to_purchase_rate",
                )
            },
            "verified_revenue": {
                "amount": funnel["total_revenue"],
                "currency": "THB",
                "evidence_state": "verified" if sales_count else "unavailable",
            },
            "verified_subscriptions": {
                "count": len(bridge_events),
                "amount": round(sum(float(event.amount) for event in bridge_events), 2),
                "currency": "THB",
                "evidence_state": "verified" if bridge_events else "unavailable",
            },
            "refunds": {
                "count": len(refunded_orders),
                "amount": round(sum(float(order.total_amount) for order in refunded_orders), 2),
                "currency": "THB",
                "evidence_state": "verified",
            },
            "by_source": list(by_source.values()),
            "by_product": list(by_product.values()),
            "by_plan": list(by_plan.values()),
            "by_referral": list(referral_totals.values()),
            "content": {"evidence_state": "unavailable"},
            "data_quality": {
                "event_count": len(event_rows),
                "attributed_event_count": attributed,
                "attribution_completeness": round(
                    attributed / len(event_rows) * 100, 2
                ) if event_rows else 0.0,
                "unattributed_purchases": sum(
                    1 for event, _ in event_rows
                    if event.event_type == "purchase"
                    and not event.source and not event.referral_code
                ),
            },
        }

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
            FunnelOrder.refunded_at.is_(None),
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

        bridge_stmt = select(ConversionEvent).where(
            and_(*filters),
            ConversionEvent.event_type == "purchase",
            ConversionEvent.order_id.is_(None),
        )
        bridge_events = (await self.db.execute(bridge_stmt)).scalars().all()
        total_revenue += sum(
            (float(self._verified_event_amount(event)) for event in bridge_events),
            0.0,
        )
        sales_count += sum(
            1 for event in bridge_events
            if self._verified_event_amount(event) > Decimal("0")
        )

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
            FunnelOrder.refunded_at.is_(None),
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
            daily_data[day_str]["revenue"] = round(
                daily_data[day_str]["revenue"] + rev, 2
            )

        bridge_events_stmt = select(ConversionEvent).where(
            and_(*filters),
            ConversionEvent.event_type == "purchase",
            ConversionEvent.order_id.is_(None),
        )
        bridge_events = (await self.db.execute(bridge_events_stmt)).scalars().all()
        for event in bridge_events:
            amount = float(self._verified_event_amount(event))
            if not amount:
                continue
            day_str = str(event.occurred_at.date())
            if day_str not in daily_data:
                daily_data[day_str] = {
                    "date": day_str,
                    "views": 0,
                    "leads": 0,
                    "purchases": 0,
                    "revenue": 0.0,
                }
            daily_data[day_str]["revenue"] = round(
                daily_data[day_str]["revenue"] + amount, 2
            )

        return sorted(list(daily_data.values()), key=lambda x: x["date"])
