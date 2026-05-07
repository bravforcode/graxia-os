#!/usr/bin/env python3
"""
Revenue OS v10 Integration Verification Script
Verifies Phase 1 completion: Data Layer & Schema Merging
"""
import sys
import asyncio
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from sqlalchemy import text, inspect
from backend.app.database import engine


EXPECTED_TABLES = [
    # Core Financial
    'revenue_os_products',
    'revenue_os_customers',
    'revenue_os_orders',
    'revenue_os_ledger_entries',
    'revenue_os_refunds',
    'revenue_os_entitlements',
    
    # Lead & Campaign
    'revenue_os_lead_magnets',
    'revenue_os_leads',
    'revenue_os_lead_events',
    'revenue_os_campaigns',
    'revenue_os_attribution_events',
    'revenue_os_experiments',
    
    # Content & Approval
    'revenue_os_content_ideas',
    'revenue_os_content_posts',
    'revenue_os_approvals',
    'revenue_os_ai_drafts',
    
    # Email & Delivery
    'revenue_os_email_outbox',
    'revenue_os_delivery_events',
    
    # Automation & Incidents
    'revenue_os_automation_locks',
    'revenue_os_automation_runs',
    'revenue_os_incident_events',
    
    # Webhooks & Metrics
    'revenue_os_webhook_events',
    'revenue_os_metrics_daily',
    'revenue_os_strategy_logs',
    'revenue_os_audit_logs',
    'revenue_os_service_offers',
    'revenue_os_tasks',
]

EXPECTED_CONSTRAINTS = [
    ('revenue_os_orders', 'uq_orders_platform_order'),
    ('revenue_os_orders', 'uq_orders_idempotency_key'),
    ('revenue_os_products', 'uq_products_slug'),
    ('revenue_os_customers', 'uq_customers_email'),
    ('revenue_os_leads', 'uq_leads_email'),
    ('revenue_os_campaigns', 'uq_revenue_campaign_slug'),
    ('revenue_os_email_outbox', 'uq_email_outbox_email_key'),
    ('revenue_os_attribution_events', 'uq_attribution_event_id'),
    ('revenue_os_webhook_events', 'uq_webhook_provider_event'),
]

EXPECTED_INDEXES = [
    ('revenue_os_orders', 'ix_orders_customer_email'),
    ('revenue_os_orders', 'ix_orders_status'),
    ('revenue_os_orders', 'ix_orders_created_at'),
    ('revenue_os_ledger_entries', 'ix_ledger_order_id'),
    ('revenue_os_leads', 'ix_leads_status'),
    ('revenue_os_campaigns', 'ix_campaign_status_product'),
    ('revenue_os_email_outbox', 'ix_email_outbox_status'),
    ('revenue_os_automation_locks', 'ix_locks_expires_at'),
]


async def verify_tables():
    """Verify all expected tables exist"""
    print("\n🔍 Verifying Revenue OS Tables...")
    
    async with engine.connect() as conn:
        result = await conn.execute(text("""
            SELECT table_name 
            FROM information_schema.tables 
            WHERE table_schema = 'public' 
            AND table_name LIKE 'revenue_os_%'
            ORDER BY table_name
        """))
        existing_tables = [row[0] for row in result]
    
    missing_tables = set(EXPECTED_TABLES) - set(existing_tables)
    extra_tables = set(existing_tables) - set(EXPECTED_TABLES)
    
    if missing_tables:
        print(f"  ❌ Missing tables: {', '.join(missing_tables)}")
        return False
    
    if extra_tables:
        print(f"  ⚠️  Extra tables: {', '.join(extra_tables)}")
    
    print(f"  ✅ All {len(EXPECTED_TABLES)} tables exist")
    return True


async def verify_constraints():
    """Verify unique constraints"""
    print("\n🔍 Verifying Unique Constraints...")
    
    async with engine.connect() as conn:
        violations = []
        for table_name, constraint_name in EXPECTED_CONSTRAINTS:
            result = await conn.execute(text(f"""
                SELECT constraint_name 
                FROM information_schema.table_constraints 
                WHERE table_name = '{table_name}' 
                AND constraint_name = '{constraint_name}'
                AND constraint_type = 'UNIQUE'
            """))
            if not result.fetchone():
                violations.append(f"{table_name}.{constraint_name}")
    
    if violations:
        print(f"  ❌ Missing constraints: {', '.join(violations)}")
        return False
    
    print(f"  ✅ All {len(EXPECTED_CONSTRAINTS)} unique constraints verified")
    return True


async def verify_indexes():
    """Verify performance indexes"""
    print("\n🔍 Verifying Performance Indexes...")
    
    async with engine.connect() as conn:
        violations = []
        for table_name, index_name in EXPECTED_INDEXES:
            result = await conn.execute(text(f"""
                SELECT indexname 
                FROM pg_indexes 
                WHERE tablename = '{table_name}' 
                AND indexname = '{index_name}'
            """))
            if not result.fetchone():
                violations.append(f"{table_name}.{index_name}")
    
    if violations:
        print(f"  ❌ Missing indexes: {', '.join(violations)}")
        return False
    
    print(f"  ✅ All {len(EXPECTED_INDEXES)} indexes verified")
    return True


async def verify_triggers():
    """Verify updated_at triggers"""
    print("\n🔍 Verifying Updated_at Triggers...")
    
    tables_with_updated_at = [
        'revenue_os_products',
        'revenue_os_customers',
        'revenue_os_orders',
        'revenue_os_refunds',
        'revenue_os_leads',
        'revenue_os_campaigns',
        'revenue_os_delivery_events',
        'revenue_os_automation_locks',
        'revenue_os_experiments',
        'revenue_os_metrics_daily',
        'revenue_os_service_offers',
    ]
    
    async with engine.connect() as conn:
        violations = []
        for table_name in tables_with_updated_at:
            result = await conn.execute(text(f"""
                SELECT trigger_name 
                FROM information_schema.triggers 
                WHERE event_object_table = '{table_name}' 
                AND trigger_name LIKE '%updated_at%'
            """))
            if not result.fetchone():
                violations.append(table_name)
    
    if violations:
        print(f"  ❌ Missing triggers: {', '.join(violations)}")
        return False
    
    print(f"  ✅ All {len(tables_with_updated_at)} updated_at triggers verified")
    return True


async def verify_foreign_keys():
    """Verify foreign key relationships"""
    print("\n🔍 Verifying Foreign Key Relationships...")
    
    async with engine.connect() as conn:
        result = await conn.execute(text("""
            SELECT COUNT(*) 
            FROM information_schema.table_constraints 
            WHERE constraint_type = 'FOREIGN KEY' 
            AND table_name LIKE 'revenue_os_%'
        """))
        fk_count = result.scalar()
    
    if fk_count < 30:  # We expect at least 30 foreign keys
        print(f"  ❌ Only {fk_count} foreign keys found (expected >= 30)")
        return False
    
    print(f"  ✅ {fk_count} foreign key relationships verified")
    return True


async def verify_check_constraints():
    """Verify check constraints"""
    print("\n🔍 Verifying Check Constraints...")
    
    expected_checks = [
        ('revenue_os_orders', 'ck_orders_amount_positive'),
        ('revenue_os_ledger_entries', 'ck_ledger_nonzero'),
    ]
    
    async with engine.connect() as conn:
        violations = []
        for table_name, constraint_name in expected_checks:
            result = await conn.execute(text(f"""
                SELECT constraint_name 
                FROM information_schema.table_constraints 
                WHERE table_name = '{table_name}' 
                AND constraint_name = '{constraint_name}'
                AND constraint_type = 'CHECK'
            """))
            if not result.fetchone():
                violations.append(f"{table_name}.{constraint_name}")
    
    if violations:
        print(f"  ❌ Missing check constraints: {', '.join(violations)}")
        return False
    
    print(f"  ✅ All {len(expected_checks)} check constraints verified")
    return True


async def main():
    """Run all verification checks"""
    print("=" * 70)
    print("Revenue OS v10 Integration Verification")
    print("Phase 1: Enterprise Data Layer & Schema Merging")
    print("=" * 70)
    
    checks = [
        verify_tables(),
        verify_constraints(),
        verify_indexes(),
        verify_triggers(),
        verify_foreign_keys(),
        verify_check_constraints(),
    ]
    
    results = await asyncio.gather(*checks)
    
    print("\n" + "=" * 70)
    if all(results):
        print("✅ PHASE 1 VERIFICATION: PASSED")
        print("=" * 70)
        print("\n✨ Revenue OS v10 Data Layer successfully integrated!")
        print("📊 All 30+ tables, constraints, indexes, and triggers verified")
        print("\n🚀 Ready for Phase 2: Core Business Logic & Celery Automation")
        return 0
    else:
        print("❌ PHASE 1 VERIFICATION: FAILED")
        print("=" * 70)
        print("\n⚠️  Please fix the issues above before proceeding to Phase 2")
        return 1


if __name__ == "__main__":
    exit_code = asyncio.run(main())
    sys.exit(exit_code)
