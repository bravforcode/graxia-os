"""
Test Lead Scoring
Verify deterministic scoring algorithms
"""
import pytest

from ..core.scoring import (
    calculate_lead_score,
    prioritize_leads,
    should_nurture_lead,
    calculate_conversion_probability,
)


def test_lead_score_business_email():
    """Test that business email domains get higher scores."""
    lead_data = {
        "email": "john@company.com",
        "source": "referral",
    }
    
    score, rationale = calculate_lead_score(lead_data)
    
    assert score >= 40  # Business email (20) + referral (20)
    assert "Business email domain" in rationale


def test_lead_score_personal_email():
    """Test that personal email domains get lower scores."""
    lead_data = {
        "email": "john@gmail.com",
        "source": "cold_outreach",
    }
    
    score, rationale = calculate_lead_score(lead_data)
    
    assert score >= 15  # Personal email (10) + cold_outreach (5)
    assert "Personal email domain" in rationale


def test_lead_score_with_engagement():
    """Test that engagement increases score."""
    lead_data = {
        "email": "engaged@example.com",
        "source": "linkedin",
    }
    engagement_data = {
        "email_opens": 5,
        "email_clicks": 3,
        "page_visits": 2,
    }
    
    score, rationale = calculate_lead_score(lead_data, engagement_data)
    
    # Should have engagement bonus
    assert score >= 30  # Base + engagement
    assert "Engagement activity" in rationale


def test_lead_score_with_lead_magnet():
    """Test that lead magnet download increases score."""
    lead_data = {
        "email": "magnet@example.com",
        "source": "content",
        "lead_magnet_id": "some-uuid",
    }
    
    score, rationale = calculate_lead_score(lead_data)
    
    assert score >= 27  # Email (5) + content (12) + lead magnet (15) + recency (15)
    assert "Downloaded lead magnet" in rationale


def test_lead_score_deterministic():
    """Test that scoring is deterministic (same input = same output)."""
    lead_data = {
        "email": "test@example.com",
        "source": "organic_search",
    }
    
    score1, _ = calculate_lead_score(lead_data)
    score2, _ = calculate_lead_score(lead_data)
    
    assert score1 == score2


def test_prioritize_leads():
    """Test lead prioritization by score."""
    leads = [
        {"email": "low@example.com", "score": 30, "created_at": "2024-01-01"},
        {"email": "high@example.com", "score": 80, "created_at": "2024-01-02"},
        {"email": "medium@example.com", "score": 50, "created_at": "2024-01-03"},
    ]
    
    prioritized = prioritize_leads(leads, limit=10)
    
    assert prioritized[0]["email"] == "high@example.com"
    assert prioritized[1]["email"] == "medium@example.com"
    assert prioritized[2]["email"] == "low@example.com"


def test_should_nurture_lead_high_score():
    """Test that high-score leads should be nurtured."""
    lead_data = {
        "score": 70,
        "status": "new",
    }
    
    assert should_nurture_lead(lead_data) is True


def test_should_nurture_lead_low_score():
    """Test that low-score leads should not be nurtured."""
    lead_data = {
        "score": 20,
        "status": "new",
    }
    
    assert should_nurture_lead(lead_data) is False


def test_conversion_probability():
    """Test conversion probability calculation."""
    lead_data = {
        "score": 80,
        "source": "referral",
    }
    engagement_data = {
        "email_clicks": 5,
    }
    
    probability = calculate_conversion_probability(lead_data, engagement_data)
    
    assert 0.0 <= probability <= 1.0
    assert probability > 0.5  # High score should have high probability
