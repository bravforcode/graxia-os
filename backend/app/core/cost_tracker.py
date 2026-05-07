"""
Cost Tracking and Forecasting

Tracks AI API costs (OpenClaw + Gemini) and provides forecasting.
"""
import logging
from datetime import UTC, datetime, timedelta
from decimal import Decimal

from sqlalchemy import func, select

from app.database import AsyncSessionLocal
from app.models.openclaw_usage import OpenClawUsage

logger = logging.getLogger(__name__)


class CostTracker:
    """
    Cost tracker for AI API usage.
    
    Features:
    - Track OpenClaw costs
    - Track Gemini costs
    - Daily/weekly/monthly aggregation
    - Cost forecasting
    - Budget alerts
    - Cost optimization recommendations
    """
    
    def __init__(self):
        self.daily_budget = 1.67  # $50/month ≈ $1.67/day
        self.monthly_budget = 50.0
        self.alert_threshold = 0.8  # 80%
    
    async def track_openclaw_cost(
        self,
        platform: str,
        action: str,
        cost_usd: float
    ) -> None:
        """Track OpenClaw API cost."""
        try:
            async with AsyncSessionLocal() as db:
                usage = OpenClawUsage(
                    platform=platform,
                    action=action,
                    cost_usd=Decimal(str(cost_usd)),
                    created_at=datetime.now(UTC)
                )
                db.add(usage)
                await db.commit()
                
                # Check if approaching budget
                await self._check_budget_alerts()
        except Exception as e:
            logger.error(f"Failed to track OpenClaw cost: {e}")
    
    async def track_gemini_cost(
        self,
        model: str,
        input_tokens: int,
        output_tokens: int,
        cost_usd: float,
        prompt_preview: str = ""
    ) -> None:
        """Track Gemini API cost."""
        try:
            async with AsyncSessionLocal() as db:
                # Store in openclaw_usage table with gemini/ prefix
                usage = OpenClawUsage(
                    platform=f"gemini/{model}",
                    action="generate",
                    cost_usd=Decimal(str(cost_usd)),
                    created_at=datetime.now(UTC)
                )
                db.add(usage)
                await db.commit()
                
                logger.info(
                    f"Gemini cost tracked: ${cost_usd:.4f} "
                    f"({model}, {input_tokens}+{output_tokens} tokens)"
                )
                
                # Check budget
                await self._check_budget_alerts()
        except Exception as e:
            logger.error(f"Failed to track Gemini cost: {e}")
    
    async def get_daily_cost(self, date: datetime | None = None) -> float:
        """Get total cost for a specific day."""
        try:
            if not date:
                date = datetime.now(UTC)
            
            async with AsyncSessionLocal() as db:
                # OpenClaw costs
                openclaw_query = select(func.sum(OpenClawUsage.cost_usd)).where(
                    func.date(OpenClawUsage.created_at) == date.date()
                )
                openclaw_result = await db.execute(openclaw_query)
                openclaw_cost = float(openclaw_result.scalar() or 0)
                
                # TODO: Add Gemini costs
                gemini_cost = 0.0
                
                return openclaw_cost + gemini_cost
        except Exception as e:
            logger.error(f"Failed to get daily cost: {e}")
            return 0.0
    
    async def get_weekly_cost(self) -> float:
        """Get total cost for current week."""
        try:
            week_ago = datetime.now(UTC) - timedelta(days=7)
            
            async with AsyncSessionLocal() as db:
                # OpenClaw costs
                openclaw_query = select(func.sum(OpenClawUsage.cost_usd)).where(
                    OpenClawUsage.created_at >= week_ago,
                    ~OpenClawUsage.platform.like('gemini/%')
                )
                openclaw_result = await db.execute(openclaw_query)
                openclaw_cost = float(openclaw_result.scalar() or 0)
                
                # Gemini costs (stored with gemini/ prefix)
                gemini_query = select(func.sum(OpenClawUsage.cost_usd)).where(
                    OpenClawUsage.created_at >= week_ago,
                    OpenClawUsage.platform.like('gemini/%')
                )
                gemini_result = await db.execute(gemini_query)
                gemini_cost = float(gemini_result.scalar() or 0)
                
                return openclaw_cost + gemini_cost
        except Exception as e:
            logger.error(f"Failed to get weekly cost: {e}")
            return 0.0
    
    async def get_monthly_cost(self) -> float:
        """Get total cost for current month."""
        try:
            month_start = datetime.now(UTC).replace(day=1, hour=0, minute=0, second=0)
            
            async with AsyncSessionLocal() as db:
                # OpenClaw costs
                openclaw_query = select(func.sum(OpenClawUsage.cost_usd)).where(
                    OpenClawUsage.created_at >= month_start
                )
                openclaw_result = await db.execute(openclaw_query)
                openclaw_cost = float(openclaw_result.scalar() or 0)
                
                # TODO: Add Gemini costs
                gemini_cost = 0.0
                
                return openclaw_cost + gemini_cost
        except Exception as e:
            logger.error(f"Failed to get monthly cost: {e}")
            return 0.0
    
    async def forecast_monthly_cost(self) -> dict:
        """
        Forecast monthly cost based on current usage.
        
        Returns:
            dict with forecasted cost and confidence
        """
        try:
            # Get current month cost
            current_cost = await self.get_monthly_cost()
            
            # Calculate days elapsed and remaining
            now = datetime.now(UTC)
            month_start = now.replace(day=1, hour=0, minute=0, second=0)
            days_elapsed = (now - month_start).days + 1
            
            # Get days in month
            if now.month == 12:
                next_month = now.replace(year=now.year + 1, month=1, day=1)
            else:
                next_month = now.replace(month=now.month + 1, day=1)
            days_in_month = (next_month - month_start).days
            
            # Calculate daily average
            daily_avg = current_cost / days_elapsed if days_elapsed > 0 else 0
            
            # Forecast
            forecasted_cost = daily_avg * days_in_month
            
            # Confidence (higher with more data)
            confidence = min(days_elapsed / 7, 1.0)  # Max confidence after 7 days
            
            return {
                "current_cost": round(current_cost, 2),
                "forecasted_cost": round(forecasted_cost, 2),
                "daily_average": round(daily_avg, 2),
                "days_elapsed": days_elapsed,
                "days_remaining": days_in_month - days_elapsed,
                "confidence": round(confidence, 2),
                "budget": self.monthly_budget,
                "over_budget": forecasted_cost > self.monthly_budget
            }
        except Exception as e:
            logger.error(f"Failed to forecast cost: {e}")
            return {}
    
    async def get_cost_breakdown(self, days: int = 7) -> dict:
        """Get cost breakdown by platform and action."""
        try:
            since = datetime.now(UTC) - timedelta(days=days)
            
            async with AsyncSessionLocal() as db:
                # By platform
                platform_query = select(
                    OpenClawUsage.platform,
                    func.count(OpenClawUsage.id).label("count"),
                    func.sum(OpenClawUsage.cost_usd).label("cost")
                ).where(
                    OpenClawUsage.created_at >= since
                ).group_by(OpenClawUsage.platform)
                
                platform_result = await db.execute(platform_query)
                by_platform = {
                    row.platform: {
                        "requests": row.count,
                        "cost_usd": float(row.cost)
                    }
                    for row in platform_result
                }
                
                # By action
                action_query = select(
                    OpenClawUsage.action,
                    func.count(OpenClawUsage.id).label("count"),
                    func.sum(OpenClawUsage.cost_usd).label("cost")
                ).where(
                    OpenClawUsage.created_at >= since
                ).group_by(OpenClawUsage.action)
                
                action_result = await db.execute(action_query)
                by_action = {
                    row.action: {
                        "requests": row.count,
                        "cost_usd": float(row.cost)
                    }
                    for row in action_result
                }
                
                # Total
                total_query = select(
                    func.count(OpenClawUsage.id).label("count"),
                    func.sum(OpenClawUsage.cost_usd).label("cost")
                ).where(OpenClawUsage.created_at >= since)
                
                total_result = await db.execute(total_query)
                total_row = total_result.first()
                
                return {
                    "period_days": days,
                    "total_requests": total_row.count if total_row else 0,
                    "total_cost_usd": float(total_row.cost) if total_row and total_row.cost else 0.0,
                    "by_platform": by_platform,
                    "by_action": by_action
                }
        except Exception as e:
            logger.error(f"Failed to get cost breakdown: {e}")
            return {}
    
    async def get_optimization_recommendations(self) -> list[str]:
        """Get cost optimization recommendations."""
        recommendations = []
        
        try:
            # Get current costs
            monthly_cost = await self.get_monthly_cost()
            forecast = await self.forecast_monthly_cost()
            breakdown = await self.get_cost_breakdown(days=7)
            
            # Check if over budget
            if forecast.get("over_budget"):
                recommendations.append(
                    f"⚠️ Forecasted cost (${forecast['forecasted_cost']:.2f}) exceeds budget (${self.monthly_budget:.2f})"
                )
            
            # Check high-cost platforms
            by_platform = breakdown.get("by_platform", {})
            for platform, data in by_platform.items():
                if data["cost_usd"] > 10:
                    recommendations.append(
                        f"💡 {platform} costs are high (${data['cost_usd']:.2f}). Consider reducing frequency."
                    )
            
            # Check cache hit rate
            # TODO: Get cache hit rate from metrics
            recommendations.append(
                "💡 Increase cache TTL to 8 hours to reduce API calls by 20-30%"
            )
            
            # General recommendations
            if monthly_cost > self.monthly_budget * 0.5:
                recommendations.append(
                    "💡 Consider using Gemini Flash instead of Pro to save 50% on AI costs"
                )
            
            if not recommendations:
                recommendations.append("✅ Costs are within budget. No optimizations needed.")
        except Exception as e:
            logger.error(f"Failed to get recommendations: {e}")
        
        return recommendations
    
    async def _check_budget_alerts(self) -> None:
        """Check if budget alerts should be sent."""
        try:
            # Daily budget check
            daily_cost = await self.get_daily_cost()
            if daily_cost >= self.daily_budget * self.alert_threshold:
                await self._send_budget_alert("daily", daily_cost, self.daily_budget)
            
            # Monthly budget check
            monthly_cost = await self.get_monthly_cost()
            if monthly_cost >= self.monthly_budget * self.alert_threshold:
                await self._send_budget_alert("monthly", monthly_cost, self.monthly_budget)
        except Exception as e:
            logger.error(f"Failed to check budget alerts: {e}")
    
    async def _send_budget_alert(self, period: str, current: float, limit: float) -> None:
        """Send budget alert via event bus."""
        try:
            from app.core.event_bus import event_bus
            
            percentage = (current / limit) * 100
            
            await event_bus.emit("cost.budget_warning", {
                "period": period,
                "current_usd": current,
                "limit_usd": limit,
                "percentage": round(percentage, 1)
            })
            
            logger.warning(
                f"Budget alert: {period} cost ${current:.2f} / ${limit:.2f} ({percentage:.1f}%)"
            )
        except Exception as e:
            logger.error(f"Failed to send budget alert: {e}")


# Global instance
cost_tracker = CostTracker()
