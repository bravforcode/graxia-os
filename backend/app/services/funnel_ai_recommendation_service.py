"""
Funnel AI Recommendation Engine

Analyzes real funnel analytics data and generates actionable, prioritized
recommendations to improve conversion rates, average order value, and revenue.

This engine works without external LLM API calls - it uses rule-based heuristics
combined with statistical analysis to produce high-quality recommendations
that mirror what an expert growth consultant would advise.
"""
import logging
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from typing import Any, Dict, List, Optional
from uuid import UUID

from sqlalchemy import select, and_, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.funnel import (
    ConversionEvent,
    DeliveryAccess,
    DigitalProduct,
    FunnelCheckoutSession,
    FunnelOrder,
    FunnelOrderItem,
)

logger = logging.getLogger(__name__)


class RecommendationPriority(str, Enum):
    CRITICAL = "critical"   # Revenue blocker / major drop-off
    HIGH = "high"           # High-impact, quick win
    MEDIUM = "medium"       # Meaningful improvement
    LOW = "low"             # Nice to have / polish


class RecommendationCategory(str, Enum):
    CONVERSION = "conversion"
    PRICING = "pricing"
    TRAFFIC = "traffic"
    DELIVERY = "delivery"
    EMAIL = "email"
    PRODUCT = "product"
    RETENTION = "retention"


@dataclass
class FunnelRecommendation:
    id: str
    title: str
    description: str
    action: str                    # Specific actionable step
    priority: RecommendationPriority
    category: RecommendationCategory
    impact_estimate: str           # Human-readable impact
    effort: str                    # "low" | "medium" | "high"
    metric_trigger: str            # Which metric triggered this
    metric_value: Optional[float] = None
    metric_benchmark: Optional[float] = None
    product_id: Optional[str] = None
    product_name: Optional[str] = None
    data: Dict[str, Any] = field(default_factory=dict)


@dataclass
class FunnelHealthScore:
    overall: int                   # 0-100
    conversion: int                # 0-100
    traffic: int                   # 0-100
    revenue: int                   # 0-100
    delivery: int                  # 0-100
    label: str                     # "Critical" | "Needs Work" | "Good" | "Excellent"
    summary: str


# ── Industry Benchmarks ────────────────────────────────────────────────────────
BENCHMARKS = {
    "lead_conversion_rate": 2.5,       # % of views → leads (industry avg)
    "checkout_rate": 3.0,              # % of views → checkout starts
    "checkout_to_purchase_rate": 60.0, # % of checkout → purchase (avg digital)
    "purchase_conversion_rate": 1.5,   # % of views → purchase
    "delivery_open_rate": 70.0,        # % of buyers who open delivery
    "aov_usd": 50.0,                   # USD equivalent AOV
    "min_views_for_analysis": 50,      # minimum traffic before recommendations
}


class FunnelAIRecommendationService:
    def __init__(self, db: AsyncSession):
        self.db = db

    # ── Public API ─────────────────────────────────────────────────────────────

    async def get_recommendations(
        self,
        organization_id: UUID,
        product_id: Optional[UUID] = None,
        days_back: int = 30,
        max_recommendations: int = 10,
    ) -> Dict[str, Any]:
        """
        Main entry point. Analyzes funnel data and returns prioritized
        recommendations with a health score.
        """
        since = datetime.utcnow() - timedelta(days=days_back)

        # Gather all analytics data
        metrics = await self._gather_metrics(organization_id, product_id, since)
        products = await self._get_products(organization_id)
        draft_products = [p for p in products if p["status"] == "draft"]
        published_products = [p for p in products if p["status"] == "published"]

        # Generate recommendations
        recommendations: List[FunnelRecommendation] = []

        # 1. No products published → top blocker
        if not published_products:
            recommendations.append(self._rec_no_published_products(draft_products))

        # 2. No traffic at all
        if metrics["views"] == 0 and published_products:
            recommendations.append(self._rec_no_traffic())

        # Only generate conversion recs if we have meaningful traffic
        if metrics["views"] >= BENCHMARKS["min_views_for_analysis"]:
            recommendations.extend(self._analyze_conversion_funnel(metrics))

        # 3. Delivery open rate
        if metrics.get("purchases", 0) > 0:
            recommendations.extend(self._analyze_delivery(metrics))

        # 4. Products without assets (can't deliver)
        recommendations.extend(await self._analyze_product_completeness(
            organization_id, published_products
        ))

        # 5. Pricing / AOV analysis
        if metrics.get("sales_count", 0) >= 3:
            recommendations.extend(self._analyze_pricing(metrics))

        # 6. Lead magnet analysis
        recommendations.extend(self._analyze_lead_capture(metrics))

        # 7. Traffic source analysis
        if metrics["views"] > 0:
            recommendations.extend(await self._analyze_traffic_sources(
                organization_id, product_id, since
            ))

        # 8. Abandoned checkouts
        recommendations.extend(await self._analyze_abandoned_checkouts(
            organization_id, product_id, since
        ))

        # Sort by priority, deduplicate, limit
        recommendations = self._rank_and_deduplicate(recommendations)[:max_recommendations]

        # Calculate health score
        health = self._calculate_health_score(metrics, published_products)

        return {
            "health_score": health.__dict__,
            "recommendations": [self._rec_to_dict(r) for r in recommendations],
            "metrics_snapshot": metrics,
            "analysis_period_days": days_back,
            "generated_at": datetime.utcnow().isoformat(),
            "total_recommendations": len(recommendations),
        }

    async def get_product_recommendations(
        self,
        organization_id: UUID,
        product_id: UUID,
        days_back: int = 30,
    ) -> Dict[str, Any]:
        """Get recommendations scoped to a specific product."""
        return await self.get_recommendations(
            organization_id=organization_id,
            product_id=product_id,
            days_back=days_back,
            max_recommendations=8,
        )

    # ── Data Gathering ─────────────────────────────────────────────────────────

    async def _gather_metrics(
        self,
        organization_id: UUID,
        product_id: Optional[UUID],
        since: datetime,
    ) -> Dict[str, Any]:
        """Pull all required metrics from the DB in a single pass."""
        filters = [
            ConversionEvent.organization_id == organization_id,
            ConversionEvent.occurred_at >= since,
        ]
        if product_id:
            filters.append(ConversionEvent.product_id == product_id)

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

        # Revenue & orders
        order_filters = [
            FunnelOrder.organization_id == organization_id,
            FunnelOrder.status == "paid",
            FunnelOrder.paid_at >= since,
        ]
        if product_id:
            from app.models.funnel import FunnelOrderItem as FOI
            rev_stmt = (
                select(func.sum(FOI.total_amount), func.count(func.distinct(FunnelOrder.id)))
                .select_from(FunnelOrder)
                .join(FOI, FOI.order_id == FunnelOrder.id)
                .where(and_(*order_filters, FOI.product_id == product_id))
            )
        else:
            rev_stmt = (
                select(func.sum(FunnelOrder.total_amount), func.count(FunnelOrder.id))
                .where(and_(*order_filters))
            )
        rev_res = await self.db.execute(rev_stmt)
        total_revenue_val, sales_count = rev_res.first() or (0.0, 0)
        total_revenue = float(total_revenue_val or 0.0)

        # Abandoned checkouts (pending sessions older than 1 hour)
        abandoned_filters = [
            FunnelCheckoutSession.organization_id == organization_id,
            FunnelCheckoutSession.status == "pending",
            FunnelCheckoutSession.created_at >= since,
            FunnelCheckoutSession.created_at <= datetime.utcnow() - timedelta(hours=1),
        ]
        if product_id:
            abandoned_filters.append(FunnelCheckoutSession.product_id == product_id)
        abandoned_stmt = select(func.count(FunnelCheckoutSession.id)).where(and_(*abandoned_filters))
        abandoned_res = await self.db.execute(abandoned_stmt)
        abandoned_checkouts = abandoned_res.scalar() or 0

        # Compute rates safely
        def safe_rate(num, denom):
            return round((num / denom * 100.0) if denom > 0 else 0.0, 2)

        return {
            "views": views,
            "leads": leads,
            "checkout_starts": checkout_starts,
            "purchases": purchases,
            "delivery_opened": delivery_opened,
            "sales_count": sales_count or 0,
            "total_revenue": round(total_revenue, 2),
            "aov": round(total_revenue / (sales_count or 1), 2) if sales_count else 0.0,
            "abandoned_checkouts": abandoned_checkouts,
            "lead_conversion_rate": safe_rate(leads, views),
            "checkout_rate": safe_rate(checkout_starts, views),
            "checkout_to_purchase_rate": safe_rate(purchases, checkout_starts),
            "purchase_conversion_rate": safe_rate(purchases, views),
            "delivery_open_rate": safe_rate(delivery_opened, purchases),
        }

    async def _get_products(self, organization_id: UUID) -> List[Dict[str, Any]]:
        stmt = (
            select(DigitalProduct)
            .where(DigitalProduct.organization_id == organization_id)
            .where(DigitalProduct.status.in_(["draft", "published"]))
        )
        res = await self.db.execute(stmt)
        products = res.scalars().all()
        return [
            {
                "id": str(p.id),
                "name": p.name,
                "slug": p.slug,
                "status": p.status,
                "price_amount": float(p.price_amount or 0),
                "stripe_price_id": p.stripe_price_id,
            }
            for p in products
        ]

    async def _analyze_product_completeness(
        self,
        organization_id: UUID,
        published_products: List[Dict[str, Any]],
    ) -> List[FunnelRecommendation]:
        """Detect published products with no delivery assets."""
        from app.models.funnel import DeliveryAsset
        recs = []
        for product in published_products:
            stmt = (
                select(func.count(DeliveryAsset.id))
                .where(
                    and_(
                        DeliveryAsset.product_id == UUID(product["id"]),
                        DeliveryAsset.is_active == True,
                    )
                )
            )
            res = await self.db.execute(stmt)
            asset_count = res.scalar() or 0
            if asset_count == 0:
                recs.append(FunnelRecommendation(
                    id=f"no-assets-{product['id'][:8]}",
                    title=f"'{product['name']}' has no delivery assets",
                    description=(
                        "This product is published but has no active delivery assets. "
                        "Customers who purchase will not receive anything automatically."
                    ),
                    action=(
                        "Add at least one delivery asset (PDF, video URL, or content body) "
                        "to this product before driving traffic."
                    ),
                    priority=RecommendationPriority.CRITICAL,
                    category=RecommendationCategory.DELIVERY,
                    impact_estimate="Prevents failed customer experience after purchase",
                    effort="low",
                    metric_trigger="delivery_asset_count",
                    metric_value=0,
                    product_id=product["id"],
                    product_name=product["name"],
                ))
            if not product.get("stripe_price_id"):
                recs.append(FunnelRecommendation(
                    id=f"no-stripe-{product['id'][:8]}",
                    title=f"'{product['name']}' has no Stripe price linked",
                    description=(
                        "This product is published but has no Stripe price ID configured. "
                        "Checkout will fail without a valid stripe_price_id."
                    ),
                    action=(
                        "Create a product and price in your Stripe dashboard, then update "
                        "this product's stripe_price_id and stripe_product_id fields."
                    ),
                    priority=RecommendationPriority.CRITICAL,
                    category=RecommendationCategory.PRODUCT,
                    impact_estimate="Required for checkout to function",
                    effort="low",
                    metric_trigger="stripe_price_id",
                    product_id=product["id"],
                    product_name=product["name"],
                ))
        return recs

    async def _analyze_traffic_sources(
        self,
        organization_id: UUID,
        product_id: Optional[UUID],
        since: datetime,
    ) -> List[FunnelRecommendation]:
        """Detect if traffic is coming from only 1 source (concentration risk)."""
        recs = []
        filters = [
            ConversionEvent.organization_id == organization_id,
            ConversionEvent.event_type == "page_view",
            ConversionEvent.occurred_at >= since,
        ]
        if product_id:
            filters.append(ConversionEvent.product_id == product_id)

        stmt = (
            select(ConversionEvent.source, func.count(ConversionEvent.id))
            .where(and_(*filters))
            .group_by(ConversionEvent.source)
            .order_by(func.count(ConversionEvent.id).desc())
        )
        res = await self.db.execute(stmt)
        sources = res.all()

        if not sources:
            return recs

        total = sum(s[1] for s in sources)
        top_source = sources[0]
        top_pct = (top_source[1] / total * 100) if total > 0 else 0

        if len(sources) == 1 and total >= 20:
            recs.append(FunnelRecommendation(
                id="traffic-concentration",
                title="Traffic comes from a single source",
                description=(
                    f"100% of your traffic comes from '{top_source[0] or 'unknown'}'. "
                    "Single-source dependency is a major business risk."
                ),
                action=(
                    "Diversify traffic: add at least 2 more sources such as "
                    "email newsletter, content SEO, or social media."
                ),
                priority=RecommendationPriority.HIGH,
                category=RecommendationCategory.TRAFFIC,
                impact_estimate="Reduces single-point-of-failure risk",
                effort="high",
                metric_trigger="traffic_source_count",
                metric_value=1,
                data={"sources": [{"source": s[0], "count": s[1]} for s in sources]},
            ))
        elif top_pct > 80 and total >= 30:
            recs.append(FunnelRecommendation(
                id="traffic-concentration-partial",
                title=f"{top_pct:.0f}% of traffic from single source",
                description=(
                    f"'{top_source[0] or 'unknown'}' drives {top_pct:.0f}% of your views. "
                    "Diversifying will protect and grow revenue."
                ),
                action="Test 1-2 additional traffic channels this week.",
                priority=RecommendationPriority.MEDIUM,
                category=RecommendationCategory.TRAFFIC,
                impact_estimate="5-20% more revenue through additional channels",
                effort="medium",
                metric_trigger="traffic_concentration",
                metric_value=top_pct,
                metric_benchmark=80.0,
            ))
        return recs

    async def _analyze_abandoned_checkouts(
        self,
        organization_id: UUID,
        product_id: Optional[UUID],
        since: datetime,
    ) -> List[FunnelRecommendation]:
        """Flag high abandoned checkout rate."""
        recs = []
        filters = [
            FunnelCheckoutSession.organization_id == organization_id,
            FunnelCheckoutSession.created_at >= since,
        ]
        if product_id:
            filters.append(FunnelCheckoutSession.product_id == product_id)

        total_stmt = select(func.count(FunnelCheckoutSession.id)).where(and_(*filters))
        total_res = await self.db.execute(total_stmt)
        total_sessions = total_res.scalar() or 0

        if total_sessions < 5:
            return recs

        failed_stmt = (
            select(func.count(FunnelCheckoutSession.id))
            .where(and_(*filters, FunnelCheckoutSession.status.in_(["pending", "failed"])))
        )
        failed_res = await self.db.execute(failed_stmt)
        abandoned = failed_res.scalar() or 0

        abandon_rate = (abandoned / total_sessions * 100) if total_sessions > 0 else 0

        if abandon_rate > 60:
            recs.append(FunnelRecommendation(
                id="high-abandon-rate",
                title=f"High checkout abandonment rate: {abandon_rate:.0f}%",
                description=(
                    f"{abandoned} of {total_sessions} checkout sessions were not completed. "
                    "Abandoned cart recovery can recapture 5-15% of lost revenue."
                ),
                action=(
                    "Enable abandoned checkout email sequences (send reminder at 1h and 24h). "
                    "Also review: price anchoring, trust signals, and payment method options."
                ),
                priority=RecommendationPriority.HIGH,
                category=RecommendationCategory.EMAIL,
                impact_estimate=f"Recover ~10% of {abandoned} abandoned sessions",
                effort="medium",
                metric_trigger="abandon_rate",
                metric_value=round(abandon_rate, 1),
                metric_benchmark=40.0,
                data={"abandoned": abandoned, "total": total_sessions},
            ))
        return recs

    # ── Analysis Methods ───────────────────────────────────────────────────────

    def _analyze_conversion_funnel(self, metrics: Dict[str, Any]) -> List[FunnelRecommendation]:
        """Generate recommendations based on funnel conversion rates."""
        recs = []
        views = metrics["views"]
        b = BENCHMARKS

        # Lead conversion rate
        lcr = metrics["lead_conversion_rate"]
        if lcr < b["lead_conversion_rate"] * 0.5:
            recs.append(FunnelRecommendation(
                id="low-lead-conversion",
                title="Lead capture rate is critically low",
                description=(
                    f"Only {lcr:.1f}% of visitors become leads "
                    f"(benchmark: {b['lead_conversion_rate']}%). "
                    "Your opt-in form may be weak, buried, or missing."
                ),
                action=(
                    "Add a prominent opt-in form above the fold with a compelling lead magnet. "
                    "Test: '7-Day Free Trial', checklist, or swipe file relevant to your product."
                ),
                priority=RecommendationPriority.HIGH,
                category=RecommendationCategory.CONVERSION,
                impact_estimate=f"2x lead capture → 2x email pipeline",
                effort="medium",
                metric_trigger="lead_conversion_rate",
                metric_value=lcr,
                metric_benchmark=b["lead_conversion_rate"],
            ))
        elif lcr < b["lead_conversion_rate"]:
            recs.append(FunnelRecommendation(
                id="below-avg-lead-conversion",
                title="Lead conversion rate below industry average",
                description=(
                    f"At {lcr:.1f}%, your lead capture is below the {b['lead_conversion_rate']}% benchmark."
                ),
                action=(
                    "A/B test your CTA copy. Try urgency-based language: "
                    "'Get instant access' vs 'Download free guide'."
                ),
                priority=RecommendationPriority.MEDIUM,
                category=RecommendationCategory.CONVERSION,
                impact_estimate="10-30% more leads from same traffic",
                effort="low",
                metric_trigger="lead_conversion_rate",
                metric_value=lcr,
                metric_benchmark=b["lead_conversion_rate"],
            ))

        # Checkout rate
        cr = metrics["checkout_rate"]
        if cr < b["checkout_rate"] * 0.5 and views > 100:
            recs.append(FunnelRecommendation(
                id="low-checkout-rate",
                title="Very few visitors are starting checkout",
                description=(
                    f"Only {cr:.1f}% of visitors click 'Buy' "
                    f"(benchmark: {b['checkout_rate']}%). "
                    "Your buy button or price may be a friction point."
                ),
                action=(
                    "Make the CTA button more prominent (contrasting color, above the fold). "
                    "Add social proof: testimonials, purchase count, money-back guarantee badge."
                ),
                priority=RecommendationPriority.HIGH,
                category=RecommendationCategory.CONVERSION,
                impact_estimate="Doubling checkout rate doubles revenue potential",
                effort="low",
                metric_trigger="checkout_rate",
                metric_value=cr,
                metric_benchmark=b["checkout_rate"],
            ))

        # Checkout → Purchase rate
        c2p = metrics["checkout_to_purchase_rate"]
        if metrics["checkout_starts"] >= 5 and c2p < b["checkout_to_purchase_rate"] * 0.5:
            recs.append(FunnelRecommendation(
                id="low-checkout-completion",
                title="Checkout completion rate is critically low",
                description=(
                    f"Only {c2p:.1f}% of people who start checkout complete it "
                    f"(benchmark: {b['checkout_to_purchase_rate']}%). "
                    "Something is breaking in the payment flow."
                ),
                action=(
                    "Verify Stripe is properly configured and test checkout manually. "
                    "Check for failed webhooks. Review price presentation for sticker shock."
                ),
                priority=RecommendationPriority.CRITICAL,
                category=RecommendationCategory.CONVERSION,
                impact_estimate="Fixing this could 2-3x your revenue immediately",
                effort="low",
                metric_trigger="checkout_to_purchase_rate",
                metric_value=c2p,
                metric_benchmark=b["checkout_to_purchase_rate"],
            ))
        elif metrics["checkout_starts"] >= 5 and c2p < b["checkout_to_purchase_rate"]:
            recs.append(FunnelRecommendation(
                id="below-avg-checkout-completion",
                title="Checkout completion rate below benchmark",
                description=(
                    f"At {c2p:.1f}%, your checkout completion is below the "
                    f"{b['checkout_to_purchase_rate']}% industry average."
                ),
                action=(
                    "Add an order bump or guarantee on the checkout page. "
                    "Test removing unnecessary form fields."
                ),
                priority=RecommendationPriority.MEDIUM,
                category=RecommendationCategory.CONVERSION,
                impact_estimate="10-25% more revenue from same checkout traffic",
                effort="medium",
                metric_trigger="checkout_to_purchase_rate",
                metric_value=c2p,
                metric_benchmark=b["checkout_to_purchase_rate"],
            ))

        return recs

    def _analyze_delivery(self, metrics: Dict[str, Any]) -> List[FunnelRecommendation]:
        """Analyze delivery open rates."""
        recs = []
        dor = metrics["delivery_open_rate"]
        purchases = metrics["purchases"]

        if purchases >= 3 and dor < BENCHMARKS["delivery_open_rate"] * 0.5:
            recs.append(FunnelRecommendation(
                id="low-delivery-open",
                title="Very few buyers are accessing their purchase",
                description=(
                    f"Only {dor:.1f}% of buyers have opened their delivery link "
                    f"(expected: {BENCHMARKS['delivery_open_rate']}%). "
                    "This means most customers aren't using what they bought."
                ),
                action=(
                    "Check if delivery emails are being sent and not going to spam. "
                    "Send a manual 'How to access your purchase' email to recent buyers. "
                    "Ensure delivery link is prominent and not expired."
                ),
                priority=RecommendationPriority.HIGH,
                category=RecommendationCategory.DELIVERY,
                impact_estimate="Improves customer satisfaction and reduces refund requests",
                effort="low",
                metric_trigger="delivery_open_rate",
                metric_value=dor,
                metric_benchmark=BENCHMARKS["delivery_open_rate"],
            ))
        return recs

    def _analyze_pricing(self, metrics: Dict[str, Any]) -> List[FunnelRecommendation]:
        """Analyze pricing signals."""
        recs = []
        aov = metrics["aov"]
        revenue = metrics["total_revenue"]

        if aov < 20 and metrics["sales_count"] >= 5:
            recs.append(FunnelRecommendation(
                id="low-aov",
                title="Average order value is very low",
                description=(
                    f"Your AOV is ${aov:.2f}. "
                    "At this level, you need high volume to build meaningful revenue."
                ),
                action=(
                    "Add an order bump (complementary product at checkout) or "
                    "create a higher-tier bundle (e.g., 'Pro Package' with coaching call). "
                    "Test price anchoring by listing your premium offer first."
                ),
                priority=RecommendationPriority.MEDIUM,
                category=RecommendationCategory.PRICING,
                impact_estimate="Doubling AOV doubles revenue without more traffic",
                effort="medium",
                metric_trigger="aov",
                metric_value=aov,
                metric_benchmark=BENCHMARKS["aov_usd"],
            ))
        return recs

    def _analyze_lead_capture(self, metrics: Dict[str, Any]) -> List[FunnelRecommendation]:
        """Recommend lead magnet setup if no leads are being captured."""
        recs = []
        if metrics["views"] > 30 and metrics["leads"] == 0:
            recs.append(FunnelRecommendation(
                id="no-lead-capture",
                title="No leads are being captured",
                description=(
                    f"You have {metrics['views']} page views but zero lead captures. "
                    "Without building an email list, you have no re-marketing capability."
                ),
                action=(
                    "Create a lead magnet (free checklist, template, or mini-course) "
                    "and add an opt-in form to your sales pages. "
                    "Set up your first email nurture sequence in your ESP."
                ),
                priority=RecommendationPriority.HIGH,
                category=RecommendationCategory.EMAIL,
                impact_estimate="Email list = owned audience → predictable revenue",
                effort="medium",
                metric_trigger="leads",
                metric_value=0,
                metric_benchmark=BENCHMARKS["lead_conversion_rate"],
            ))
        return recs

    def _rec_no_published_products(self, drafts: List[Dict]) -> FunnelRecommendation:
        if drafts:
            action = (
                f"You have {len(drafts)} draft product(s). "
                "Complete the required fields (name, price, slug, description, at least 1 asset) "
                "and publish to start selling."
            )
        else:
            action = (
                "Create your first digital product: set a name, slug, price, "
                "add a delivery asset, configure Stripe, and publish it."
            )
        return FunnelRecommendation(
            id="no-published-products",
            title="No products are published yet",
            description="You cannot generate revenue without at least one published product.",
            action=action,
            priority=RecommendationPriority.CRITICAL,
            category=RecommendationCategory.PRODUCT,
            impact_estimate="Required to start generating revenue",
            effort="low",
            metric_trigger="published_product_count",
            metric_value=0,
            data={"draft_count": len(drafts)},
        )

    def _rec_no_traffic(self) -> FunnelRecommendation:
        return FunnelRecommendation(
            id="no-traffic",
            title="No traffic to your sales pages",
            description=(
                "Your products are published but receiving zero page views. "
                "Without traffic, you cannot make any sales."
            ),
            action=(
                "Start with 1 traffic channel: share the product URL in a relevant "
                "online community, send it to your email list, or run a small paid ad test ($20)."
            ),
            priority=RecommendationPriority.CRITICAL,
            category=RecommendationCategory.TRAFFIC,
            impact_estimate="Traffic is the #1 prerequisite for any revenue",
            effort="medium",
            metric_trigger="page_views",
            metric_value=0,
        )

    # ── Health Score ───────────────────────────────────────────────────────────

    def _calculate_health_score(
        self,
        metrics: Dict[str, Any],
        published_products: List[Dict],
    ) -> FunnelHealthScore:
        """
        Score 0-100 across 4 dimensions.
        """
        # Conversion score
        if metrics["views"] < BENCHMARKS["min_views_for_analysis"]:
            conversion_score = 50  # neutral, not enough data
        else:
            c2p = metrics["checkout_to_purchase_rate"]
            lcr = metrics["lead_conversion_rate"]
            c2p_score = min(100, (c2p / BENCHMARKS["checkout_to_purchase_rate"]) * 100)
            lcr_score = min(100, (lcr / BENCHMARKS["lead_conversion_rate"]) * 100)
            conversion_score = int((c2p_score * 0.6) + (lcr_score * 0.4))

        # Traffic score
        if metrics["views"] == 0:
            traffic_score = 0
        elif metrics["views"] < 50:
            traffic_score = 25
        elif metrics["views"] < 200:
            traffic_score = 55
        elif metrics["views"] < 1000:
            traffic_score = 75
        else:
            traffic_score = 95

        # Revenue score
        rev = metrics["total_revenue"]
        if rev == 0:
            revenue_score = 0
        elif rev < 100:
            revenue_score = 20
        elif rev < 500:
            revenue_score = 45
        elif rev < 2000:
            revenue_score = 65
        elif rev < 10000:
            revenue_score = 82
        else:
            revenue_score = 97

        # Delivery score
        purchases = metrics.get("purchases", 0)
        if purchases == 0:
            delivery_score = 70 if published_products else 30
        else:
            dor = metrics["delivery_open_rate"]
            delivery_score = min(100, int((dor / BENCHMARKS["delivery_open_rate"]) * 100))

        overall = int(
            conversion_score * 0.35
            + traffic_score * 0.25
            + revenue_score * 0.30
            + delivery_score * 0.10
        )

        if overall >= 80:
            label, summary = "Excellent", "Your funnel is performing well. Focus on scaling traffic."
        elif overall >= 60:
            label, summary = "Good", "Solid foundation. Address the key conversion gaps to grow revenue."
        elif overall >= 35:
            label, summary = "Needs Work", "Several critical issues need attention before scaling."
        else:
            label, summary = "Critical", "Fundamental issues are blocking revenue generation."

        return FunnelHealthScore(
            overall=overall,
            conversion=conversion_score,
            traffic=traffic_score,
            revenue=revenue_score,
            delivery=delivery_score,
            label=label,
            summary=summary,
        )

    # ── Utility ────────────────────────────────────────────────────────────────

    def _rank_and_deduplicate(
        self, recs: List[FunnelRecommendation]
    ) -> List[FunnelRecommendation]:
        priority_order = {
            RecommendationPriority.CRITICAL: 0,
            RecommendationPriority.HIGH: 1,
            RecommendationPriority.MEDIUM: 2,
            RecommendationPriority.LOW: 3,
        }
        seen_ids = set()
        unique_recs = []
        for rec in recs:
            if rec.id not in seen_ids:
                seen_ids.add(rec.id)
                unique_recs.append(rec)
        return sorted(unique_recs, key=lambda r: (priority_order[r.priority], r.id))

    def _rec_to_dict(self, rec: FunnelRecommendation) -> Dict[str, Any]:
        return {
            "id": rec.id,
            "title": rec.title,
            "description": rec.description,
            "action": rec.action,
            "priority": rec.priority.value,
            "category": rec.category.value,
            "impact_estimate": rec.impact_estimate,
            "effort": rec.effort,
            "metric_trigger": rec.metric_trigger,
            "metric_value": rec.metric_value,
            "metric_benchmark": rec.metric_benchmark,
            "product_id": rec.product_id,
            "product_name": rec.product_name,
            "data": rec.data,
        }
