"""
Revenue OS Lead Scoring
Deterministic scoring algorithms for lead prioritization
"""
from typing import Dict, Any, Tuple
import structlog

logger = structlog.get_logger()


def calculate_lead_score(
    lead_data: Dict[str, Any],
    engagement_data: Dict[str, Any] = None,
) -> Tuple[float, str]:
    """
    Calculate lead score (0-100) based on multiple factors.
    
    Scoring factors:
    - Email domain quality (20 points)
    - Engagement level (30 points)
    - Source quality (20 points)
    - Lead magnet interaction (15 points)
    - Recency (15 points)
    
    Args:
        lead_data: Lead information (email, source, tags, etc.)
        engagement_data: Engagement metrics (opens, clicks, etc.)
    
    Returns:
        Tuple[float, str]: (score, rationale)
    """
    engagement_data = engagement_data or {}
    score = 0.0
    rationale_parts = []
    
    # 1. Email Domain Quality (20 points)
    email = lead_data.get("email", "").lower()
    if email:
        domain = email.split("@")[-1] if "@" in email else ""
        
        # Business domains
        business_domains = ["company.com", "startup.io", "tech.co"]
        if any(bd in domain for bd in business_domains):
            score += 20
            rationale_parts.append("Business email domain (+20)")
        # Free email providers
        elif domain in ["gmail.com", "yahoo.com", "hotmail.com", "outlook.com"]:
            score += 10
            rationale_parts.append("Personal email domain (+10)")
        # Unknown/suspicious
        else:
            score += 5
            rationale_parts.append("Unknown email domain (+5)")
    
    # 2. Engagement Level (30 points)
    email_opens = engagement_data.get("email_opens", 0)
    email_clicks = engagement_data.get("email_clicks", 0)
    page_visits = engagement_data.get("page_visits", 0)
    
    engagement_score = min(30, (email_opens * 3) + (email_clicks * 5) + (page_visits * 2))
    score += engagement_score
    if engagement_score > 0:
        rationale_parts.append(f"Engagement activity (+{engagement_score:.0f})")
    
    # 3. Source Quality (20 points)
    source = lead_data.get("source", "").lower()
    source_scores = {
        "referral": 20,
        "linkedin": 18,
        "twitter": 15,
        "organic_search": 15,
        "content": 12,
        "paid_ad": 10,
        "cold_outreach": 5,
        "unknown": 3,
    }
    source_score = source_scores.get(source, 3)
    score += source_score
    rationale_parts.append(f"Source: {source} (+{source_score})")
    
    # 4. Lead Magnet Interaction (15 points)
    if lead_data.get("lead_magnet_id"):
        score += 15
        rationale_parts.append("Downloaded lead magnet (+15)")
    
    # 5. Recency (15 points)
    # This would be calculated based on created_at timestamp
    # For now, assume recent leads get full points
    days_since_signup = engagement_data.get("days_since_signup", 0)
    if days_since_signup <= 7:
        recency_score = 15
    elif days_since_signup <= 30:
        recency_score = 10
    elif days_since_signup <= 90:
        recency_score = 5
    else:
        recency_score = 2
    
    score += recency_score
    rationale_parts.append(f"Recency (+{recency_score})")
    
    # Cap at 100
    score = min(100.0, score)
    
    rationale = " | ".join(rationale_parts)
    
    logger.info(
        "lead_scored",
        email=email,
        score=score,
        email_opens=email_opens,
        email_clicks=email_clicks,
        page_visits=page_visits,
        source=source,
        days_since_signup=days_since_signup,
        has_lead_magnet=bool(lead_data.get("lead_magnet_id")),
        rationale=rationale,
    )
    
    return score, rationale


def prioritize_leads(leads: list, limit: int = 10) -> list:
    """
    Sort and prioritize leads by score.
    
    Args:
        leads: List of lead dictionaries with 'score' field
        limit: Maximum number of leads to return
    
    Returns:
        list: Top N prioritized leads
    """
    sorted_leads = sorted(
        leads,
        key=lambda x: (x.get("score", 0), x.get("created_at", "")),
        reverse=True,
    )
    
    top_leads = sorted_leads[:limit]
    
    logger.info(
        "leads_prioritized",
        total_leads=len(leads),
        returned_leads=len(top_leads),
        top_score=top_leads[0].get("score", 0) if top_leads else 0,
        bottom_score=top_leads[-1].get("score", 0) if top_leads else 0,
    )
    
    return top_leads


def should_nurture_lead(lead_data: Dict[str, Any]) -> bool:
    """
    Determine if a lead should enter nurture sequence.
    
    Args:
        lead_data: Lead information including score
    
    Returns:
        bool: True if lead should be nurtured
    """
    score = lead_data.get("score", 0)
    status = lead_data.get("status", "new")
    email = lead_data.get("email", "")
    
    # High-value leads (score >= 60) should be nurtured
    if score >= 60 and status == "new":
        logger.info(
            "lead_should_nurture_high_value",
            email=email,
            score=score,
            status=status,
        )
        return True
    
    # Medium-value leads (40-59) with engagement
    if 40 <= score < 60 and status in ["new", "nurtured"]:
        logger.info(
            "lead_should_nurture_medium_value",
            email=email,
            score=score,
            status=status,
        )
        return True
    
    logger.debug(
        "lead_should_not_nurture",
        email=email,
        score=score,
        status=status,
    )
    return False


def calculate_conversion_probability(
    lead_data: Dict[str, Any],
    engagement_data: Dict[str, Any] = None,
) -> float:
    """
    Estimate probability of lead converting to customer (0.0 - 1.0).
    
    Args:
        lead_data: Lead information
        engagement_data: Engagement metrics
    
    Returns:
        float: Conversion probability (0.0 - 1.0)
    """
    score = lead_data.get("score", 0)
    email = lead_data.get("email", "")
    
    # Simple linear model: score/100 with adjustments
    base_probability = score / 100.0
    
    # Adjust based on engagement
    engagement_data = engagement_data or {}
    email_clicks = engagement_data.get("email_clicks", 0)
    if email_clicks > 3:
        base_probability *= 1.2  # 20% boost for high engagement
    
    # Adjust based on source
    source = lead_data.get("source", "").lower()
    if source in ["referral", "linkedin"]:
        base_probability *= 1.15  # 15% boost for quality sources
    
    # Cap at 1.0
    probability = min(1.0, base_probability)
    
    logger.info(
        "conversion_probability_calculated",
        email=email,
        score=score,
        probability=probability,
        email_clicks=email_clicks,
        source=source,
    )
    
    return probability
