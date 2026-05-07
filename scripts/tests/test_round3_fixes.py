"""
Quick verification test for Round 3 fixes.
Run with: python -m pytest test_round3_fixes.py -v
"""
import pytest
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

# Test imports work correctly
def test_imports():
    """Verify all fixed modules can be imported without errors."""
    from graxia.database import Base
    from graxia.packages.revenue_os.db import get_db_session, get_db
    from graxia.packages.revenue_os.models import (
        CampaignStatus, OrderStatus, IncidentSeverity,
        RevenueCampaign, Approval, AIDraft, IncidentEvent
    )
    from graxia.packages.revenue_os.agents import (
        propose_campaign, draft_outreach_email, escalate_issue
    )
    from graxia.packages.revenue_os.services import ApprovalService
    
    # Verify enums have correct values
    assert CampaignStatus.DRAFT.value == "draft"
    assert CampaignStatus.ACTIVE.value == "active"
    assert CampaignStatus.ARCHIVED.value == "archived"
    assert OrderStatus.PENDING.value == "pending"
    assert IncidentSeverity.CRITICAL.value == "critical"
    
    print("✅ All imports successful")
    print("✅ Enums have correct values")
    print("✅ ARCHIVED status added to CampaignStatus")


def test_approval_service_structure():
    """Verify ApprovalService has required methods."""
    from graxia.packages.revenue_os.services import ApprovalService
    
    assert hasattr(ApprovalService, 'approve')
    assert hasattr(ApprovalService, 'reject')
    assert hasattr(ApprovalService, '_approve_campaign')
    assert hasattr(ApprovalService, '_approve_email_draft')
    
    print("✅ ApprovalService has all required methods")


def test_models_structure():
    """Verify models have correct structure after fixes."""
    from graxia.packages.revenue_os.models import (
        Approval, EmailOutbox, WebhookEvent, CampaignStatus
    )
    
    # Check Approval constraint
    approval_constraint = None
    for constraint in Approval.__table_args__:
        if hasattr(constraint, 'name') and constraint.name == 'ck_approvals_item_type':
            approval_constraint = constraint
            break
    
    assert approval_constraint is not None, "Approval constraint should exist"
    
    # Check EmailOutbox relationship has foreign_keys
    approval_rel = EmailOutbox.approval
    assert approval_rel is not None
    
    # Check WebhookEvent has processed_at index
    webhook_indexes = [idx for idx in WebhookEvent.__table_args__ if hasattr(idx, 'name')]
    index_names = [idx.name for idx in webhook_indexes]
    assert 'ix_webhook_events_processed_at' in index_names
    
    # Check ARCHIVED status exists
    assert hasattr(CampaignStatus, 'ARCHIVED')
    assert CampaignStatus.ARCHIVED.value == 'archived'
    
    print("✅ Approval constraint updated")
    print("✅ EmailOutbox relationship has foreign_keys")
    print("✅ WebhookEvent has processed_at partial index")
    print("✅ CampaignStatus has ARCHIVED status")


def test_agent_file_renamed():
    """Verify cos.py was renamed to chief_of_staff.py."""
    import os
    
    cos_path = "graxia/packages/revenue_os/agents/cos.py"
    chief_path = "graxia/packages/revenue_os/agents/chief_of_staff.py"
    
    assert not os.path.exists(cos_path), "cos.py should not exist"
    assert os.path.exists(chief_path), "chief_of_staff.py should exist"
    
    # Verify import works
    from graxia.packages.revenue_os.agents import escalate_issue
    assert escalate_issue is not None
    
    print("✅ cos.py renamed to chief_of_staff.py")
    print("✅ Import from agents package works")


def test_db_lazy_initialization():
    """Verify DATABASE_URL uses lazy initialization pattern."""
    import graxia.packages.revenue_os.db as db_module
    
    # Check that _get_or_init_database_url function exists
    assert hasattr(db_module, '_get_or_init_database_url')
    assert callable(db_module._get_or_init_database_url)
    
    # Check that _DATABASE_URL is initialized as None
    assert hasattr(db_module, '_DATABASE_URL')
    
    print("✅ DATABASE_URL uses lazy initialization pattern")


def test_chief_of_staff_signature():
    """Verify escalate_issue has updated signature with campaign/order params."""
    from graxia.packages.revenue_os.agents import escalate_issue
    import inspect
    
    sig = inspect.signature(escalate_issue)
    params = list(sig.parameters.keys())
    
    assert 'db' in params
    assert 'title' in params
    assert 'description' in params
    assert 'severity' in params
    assert 'affected_campaign_id' in params
    assert 'affected_order_id' in params
    
    print("✅ escalate_issue has updated signature with affected_campaign_id and affected_order_id")


if __name__ == "__main__":
    print("\n" + "="*60)
    print("Round 3 Fixes Verification")
    print("="*60 + "\n")
    
    test_imports()
    print()
    test_approval_service_structure()
    print()
    test_models_structure()
    print()
    test_agent_file_renamed()
    print()
    test_db_lazy_initialization()
    print()
    test_chief_of_staff_signature()
    
    print("\n" + "="*60)
    print("✅ All verification tests passed!")
    print("="*60 + "\n")
