"""
Revenue OS Campaign Service
Revenue campaign management with budget tracking and auto-pause
"""
from typing import Optional, Dict, Any
from uuid import UUID
from datetime import datetime, date
import structlog

from sqlalchemy import select, and_, func
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.exc import OperationalError, TimeoutError as SQLTimeoutError

from ..models import (
    RevenueCampaign, AttributionEvent, IncidentEvent,
    Order, Lead
)
from ..enums import CampaignStatus, IncidentSeverity
from ..constants import (
    CAMPAIGN_BUDGET_WARNING_THRESHOLD,
    CAMPAIGN_BUDGET_CRITICAL_THRESHOLD,
)
from ..core.db_ops import atomic_operation
from ..core.validators import (
    validate_string_length,
    validate_slug,
    validate_budget_cents,
    validate_non_negative_integer,
    ValidationError,
)

logger = structlog.get_logger()


class RevenueCampaignService:
    """
    Revenue campaign management service.
    Handles campaign lifecycle, budget tracking, and auto-pause on incidents.
    """
    
    @staticmethod
    async def create_campaign(
        db: AsyncSession,
        name: str,
        slug: str,
        product_id: Optional[UUID] = None,
        objective: str = "lead_to_sale",
        target_audience: Optional[str] = None,
        offer_angle: Optional[str] = None,
        primary_cta: Optional[str] = None,
        budget_cents: int = 0,
        target_revenue_cents: int = 0,
        utm_source: Optional[str] = None,
        utm_medium: Optional[str] = None,
        utm_campaign: Optional[str] = None,
        start_date: Optional[date] = None,
        end_date: Optional[date] = None,
        guardrails: Optional[Dict[str, Any]] = None,
    ) -> RevenueCampaign:
        """
        Create a new revenue campaign.
        
        Args:
            db: Database session
            name: Campaign name
            slug: Unique campaign slug
            product_id: Optional product reference
            objective: Campaign objective
            target_audience: Target audience description
            offer_angle: Offer positioning
            primary_cta: Primary call-to-action
            budget_cents: Campaign budget in cents
            target_revenue_cents: Target revenue in cents
            utm_source: UTM source parameter
            utm_medium: UTM medium parameter
            utm_campaign: UTM campaign parameter
            start_date: Campaign start date
            end_date: Campaign end date
            guardrails: Optional guardrails configuration
        
        Returns:
            RevenueCampaign: Created campaign
        
        Raises:
            ValidationError: If input validation fails
        """
        # Validate inputs
        try:
            validate_string_length(name, "name", max_length=255)
            validate_slug(slug)
            validate_budget_cents(budget_cents)
            validate_non_negative_integer(target_revenue_cents, "target_revenue_cents")
            validate_string_length(objective, "objective", max_length=100)
            
            if target_audience:
                validate_string_length(target_audience, "target_audience", max_length=1000)
            if offer_angle:
                validate_string_length(offer_angle, "offer_angle", max_length=1000)
            if primary_cta:
                validate_string_length(primary_cta, "primary_cta", max_length=255)
            if utm_source:
                validate_string_length(utm_source, "utm_source", max_length=100)
            if utm_medium:
                validate_string_length(utm_medium, "utm_medium", max_length=100)
            if utm_campaign:
                validate_string_length(utm_campaign, "utm_campaign", max_length=100)
                
        except ValidationError as e:
            logger.error(
                "campaign_validation_failed",
                error=str(e),
                name=name,
                slug=slug,
            )
            raise
        
        async with atomic_operation(db):
            campaign = RevenueCampaign(
                name=name,
                slug=slug,
                product_id=product_id,
                objective=objective,
                target_audience=target_audience,
                offer_angle=offer_angle,
                primary_cta=primary_cta,
                budget_cents=budget_cents,
                target_revenue_cents=target_revenue_cents,
                utm_source=utm_source,
                utm_medium=utm_medium,
                utm_campaign=utm_campaign,
                start_date=start_date,
                end_date=end_date,
                guardrails=guardrails or {},
                status=CampaignStatus.DRAFT,
            )
            db.add(campaign)
            await db.flush()
            
            logger.info(
                "campaign_created",
                campaign_id=str(campaign.id),
                name=name,
                budget_cents=budget_cents,
                target_revenue_cents=target_revenue_cents,
            )
            
            return campaign
    
    @staticmethod
    async def pause_campaign(
        db: AsyncSession,
        campaign_id: UUID,
        reason: str,
    ) -> RevenueCampaign:
        """
        Pause a campaign.
        
        Args:
            db: Database session
            campaign_id: Campaign ID
            reason: Pause reason
        
        Returns:
            RevenueCampaign: Paused campaign
        """
        result = await db.execute(
            select(RevenueCampaign).where(RevenueCampaign.id == campaign_id)
        )
        campaign = result.scalar_one_or_none()
        
        if not campaign:
            raise ValueError(f"Campaign {campaign_id} not found")
        
        old_status = campaign.status
        campaign.status = CampaignStatus.PAUSED
        campaign.paused_reason = reason
        await db.commit()
        
        logger.info(
            "campaign_paused",
            campaign_id=str(campaign_id),
            old_status=old_status.value,
            reason=reason,
        )
        
        return campaign
    
    @staticmethod
    async def resume_campaign(
        db: AsyncSession,
        campaign_id: UUID,
    ) -> RevenueCampaign:
        """
        Resume a paused campaign.
        
        Args:
            db: Database session
            campaign_id: Campaign ID
        
        Returns:
            RevenueCampaign: Resumed campaign
        """
        result = await db.execute(
            select(RevenueCampaign).where(RevenueCampaign.id == campaign_id)
        )
        campaign = result.scalar_one_or_none()
        
        if not campaign:
            raise ValueError(f"Campaign {campaign_id} not found")
        
        if campaign.status != CampaignStatus.PAUSED:
            raise ValueError(f"Campaign {campaign_id} is not paused")
        
        campaign.status = CampaignStatus.ACTIVE
        campaign.paused_reason = None
        await db.commit()
        
        logger.info(
            "campaign_resumed",
            campaign_id=str(campaign_id),
        )
        
        return campaign
    
    @staticmethod
    async def update_campaign_metrics(
        db: AsyncSession,
        campaign_id: UUID,
    ) -> RevenueCampaign:
        """
        Update campaign metrics from attribution events and orders.
        
        Args:
            db: Database session
            campaign_id: Campaign ID
        
        Returns:
            RevenueCampaign: Updated campaign
        
        Raises:
            ValueError: If campaign not found
        """
        try:
            result = await db.execute(
                select(RevenueCampaign).where(RevenueCampaign.id == campaign_id)
            )
            campaign = result.scalar_one_or_none()
            
            if not campaign:
                raise ValueError(f"Campaign {campaign_id} not found")
            
            # Calculate total revenue from attribution events
            revenue_result = await db.execute(
                select(func.sum(AttributionEvent.value_cents))
                .where(
                    and_(
                        AttributionEvent.campaign_id == campaign_id,
                        AttributionEvent.event_type == "sale",
                    )
                )
            )
            total_revenue = revenue_result.scalar() or 0
            
            # Calculate total spend from attribution events
            spend_result = await db.execute(
                select(func.sum(AttributionEvent.value_cents))
                .where(
                    and_(
                        AttributionEvent.campaign_id == campaign_id,
                        AttributionEvent.event_type.in_(["impression", "click"]),
                    )
                )
            )
            total_spend = spend_result.scalar() or 0
            
            # Count leads
            leads_result = await db.execute(
                select(func.count(AttributionEvent.id))
                .where(
                    and_(
                        AttributionEvent.campaign_id == campaign_id,
                        AttributionEvent.event_type == "lead",
                    )
                )
            )
            total_leads = leads_result.scalar() or 0
            
            # Update campaign
            campaign.actual_revenue_cents = total_revenue
            campaign.spend_cents = total_spend
            
            # Calculate ROAS (Return on Ad Spend)
            roas = (total_revenue / total_spend) if total_spend > 0 else 0
            
            campaign.metrics = {
                "total_revenue_cents": total_revenue,
                "total_spend_cents": total_spend,
                "total_leads": total_leads,
                "roas": roas,
                "updated_at": datetime.utcnow().isoformat(),
            }
            
            await db.commit()
            
            logger.info(
                "campaign_metrics_updated",
                campaign_id=str(campaign_id),
                revenue_cents=total_revenue,
                spend_cents=total_spend,
                roas=roas,
            )
            
            return campaign
            
        except (OperationalError, SQLTimeoutError) as e:
            await db.rollback()
            logger.error(
                "campaign_metrics_database_error",
                campaign_id=str(campaign_id),
                error=str(e),
                error_type=type(e).__name__,
            )
            raise ValueError(f"Database error: {str(e)}") from e
    
    @staticmethod
    async def check_campaign_budget(
        db: AsyncSession,
        campaign_id: UUID,
    ) -> Dict[str, Any]:
        """
        Check campaign budget status and return warnings.
        
        Args:
            db: Database session
            campaign_id: Campaign ID
        
        Returns:
            Dict with budget status and warnings
        """
        result = await db.execute(
            select(RevenueCampaign).where(RevenueCampaign.id == campaign_id)
        )
        campaign = result.scalar_one_or_none()
        
        if not campaign:
            raise ValueError(f"Campaign {campaign_id} not found")
        
        if campaign.budget_cents == 0:
            return {
                "status": "no_budget",
                "warning": None,
                "should_pause": False,
            }
        
        budget_used_ratio = campaign.spend_cents / campaign.budget_cents
        
        status = {
            "campaign_id": str(campaign_id),
            "budget_cents": campaign.budget_cents,
            "spend_cents": campaign.spend_cents,
            "remaining_cents": campaign.budget_cents - campaign.spend_cents,
            "budget_used_ratio": budget_used_ratio,
            "status": "ok",
            "warning": None,
            "should_pause": False,
        }
        
        if budget_used_ratio >= CAMPAIGN_BUDGET_CRITICAL_THRESHOLD:
            status["status"] = "critical"
            status["warning"] = f"Budget {budget_used_ratio*100:.1f}% used (critical threshold)"
            status["should_pause"] = True
        elif budget_used_ratio >= CAMPAIGN_BUDGET_WARNING_THRESHOLD:
            status["status"] = "warning"
            status["warning"] = f"Budget {budget_used_ratio*100:.1f}% used (warning threshold)"
        
        return status
    
    @staticmethod
    async def auto_pause_over_budget_campaigns(
        db: AsyncSession,
    ) -> int:
        """
        Auto-pause campaigns that have exceeded their budget.
        
        Args:
            db: Database session
        
        Returns:
            int: Number of campaigns paused
        """
        # Get all active campaigns
        result = await db.execute(
            select(RevenueCampaign)
            .where(RevenueCampaign.status == CampaignStatus.ACTIVE)
        )
        active_campaigns = result.scalars().all()
        
        paused_count = 0
        
        for campaign in active_campaigns:
            if campaign.budget_cents == 0:
                continue
            
            budget_status = await RevenueCampaignService.check_campaign_budget(
                db, campaign.id
            )
            
            if budget_status["should_pause"]:
                await RevenueCampaignService.pause_campaign(
                    db=db,
                    campaign_id=campaign.id,
                    reason=f"Auto-paused: {budget_status['warning']}",
                )
                paused_count += 1
        
        logger.info(
            "campaigns_auto_paused_budget",
            count=paused_count,
        )
        
        return paused_count
    
    @staticmethod
    async def auto_pause_campaigns_with_critical_incidents(
        db: AsyncSession,
    ) -> int:
        """
        Auto-pause campaigns linked to open critical incidents.
        
        Args:
            db: Database session
        
        Returns:
            int: Number of campaigns paused
        """
        # Get campaigns with open critical incidents
        result = await db.execute(
            select(RevenueCampaign)
            .join(
                IncidentEvent,
                IncidentEvent.affected_campaign_id == RevenueCampaign.id,
            )
            .where(
                and_(
                    RevenueCampaign.status == CampaignStatus.ACTIVE,
                    IncidentEvent.status == "open",
                    IncidentEvent.severity == IncidentSeverity.CRITICAL,
                )
            )
        )
        campaigns_with_incidents = result.scalars().all()
        
        paused_count = 0
        
        for campaign in campaigns_with_incidents:
            await RevenueCampaignService.pause_campaign(
                db=db,
                campaign_id=campaign.id,
                reason="Auto-paused: Critical incident detected",
            )
            paused_count += 1
        
        logger.info(
            "campaigns_auto_paused_incidents",
            count=paused_count,
        )
        
        return paused_count
    
    @staticmethod
    async def get_campaign_by_id(
        db: AsyncSession,
        campaign_id: UUID,
    ) -> Optional[RevenueCampaign]:
        """Get campaign by ID."""
        result = await db.execute(
            select(RevenueCampaign).where(RevenueCampaign.id == campaign_id)
        )
        return result.scalar_one_or_none()
    
    @staticmethod
    async def get_active_campaigns(
        db: AsyncSession,
        limit: int = 50,
    ) -> list[RevenueCampaign]:
        """Get all active campaigns."""
        result = await db.execute(
            select(RevenueCampaign)
            .where(RevenueCampaign.status == CampaignStatus.ACTIVE)
            .limit(limit)
        )
        return list(result.scalars().all())
