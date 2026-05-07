"""
Tests for migration 018: Add composite query indexes.

This test verifies that the migration file is valid and can be imported.
"""

import importlib.util
import sys
from pathlib import Path


def test_migration_018_can_be_imported():
    """Test that migration 018 can be imported without errors."""
    migration_path = Path(__file__).parent.parent / "alembic" / "versions" / "018_add_composite_query_indexes.py"
    
    assert migration_path.exists(), f"Migration file not found: {migration_path}"
    
    # Load the migration module
    spec = importlib.util.spec_from_file_location("migration_018", migration_path)
    assert spec is not None, "Failed to create module spec"
    
    module = importlib.util.module_from_spec(spec)
    sys.modules["migration_018"] = module
    
    # Execute the module (this will fail if there are syntax errors)
    spec.loader.exec_module(module)
    
    # Verify required attributes exist
    assert hasattr(module, "revision"), "Migration missing 'revision' attribute"
    assert hasattr(module, "down_revision"), "Migration missing 'down_revision' attribute"
    assert hasattr(module, "upgrade"), "Migration missing 'upgrade' function"
    assert hasattr(module, "downgrade"), "Migration missing 'downgrade' function"
    
    # Verify revision ID
    assert module.revision == "018_add_composite_query_indexes"
    assert module.down_revision == "017_add_gin_fulltext_indexes"


def test_migration_018_has_correct_structure():
    """Test that migration 018 has the correct structure."""
    migration_path = Path(__file__).parent.parent / "alembic" / "versions" / "018_add_composite_query_indexes.py"
    
    content = migration_path.read_text()
    
    # Check for CONCURRENT index creation
    assert "CREATE INDEX CONCURRENTLY" in content, "Migration should use CONCURRENT index creation"
    assert "DROP INDEX CONCURRENTLY" in content, "Migration should use CONCURRENT index drop"
    
    # Check for expected index names
    expected_indexes = [
        "idx_opportunities_user_status",
        "idx_opportunities_status_score",
        "idx_opportunities_user_created",
        "idx_opportunities_user_decision",
        "idx_contacts_user_company",
        "idx_contacts_user_active",
        "idx_contacts_email_active",
        "idx_contacts_user_type",
        "idx_email_threads_status_last_msg",
        "idx_email_threads_category_priority",
        "idx_email_threads_urgent_unread",
        "idx_assistant_tasks_user_status",
        "idx_assistant_tasks_status_priority",
        "idx_assistant_tasks_user_due",
        "idx_assistant_tasks_overdue",
        "idx_assistant_tasks_user_pending_priority",
    ]
    
    for index_name in expected_indexes:
        assert index_name in content, f"Migration missing index: {index_name}"
    
    # Check for partial indexes (WHERE clauses)
    assert "WHERE is_deleted = false" in content, "Migration should include partial indexes"
    assert "WHERE status = 'unread'" in content, "Migration should include status-based partial indexes"
    assert "WHERE status = 'pending'" in content, "Migration should include pending status partial indexes"


def test_migration_018_index_count():
    """Test that migration 018 creates the expected number of indexes."""
    migration_path = Path(__file__).parent.parent / "alembic" / "versions" / "018_add_composite_query_indexes.py"
    
    content = migration_path.read_text()
    
    # Count CREATE INDEX statements in upgrade()
    create_count = content.count("CREATE INDEX CONCURRENTLY")
    assert create_count == 17, f"Expected 17 indexes, found {create_count}"
    
    # Count DROP INDEX statements in downgrade()
    drop_count = content.count("DROP INDEX CONCURRENTLY")
    assert drop_count == 17, f"Expected 17 DROP statements, found {drop_count}"


def test_migration_018_documentation():
    """Test that migration 018 has proper documentation."""
    migration_path = Path(__file__).parent.parent / "alembic" / "versions" / "018_add_composite_query_indexes.py"
    
    content = migration_path.read_text()
    
    # Check for docstring
    assert '"""' in content, "Migration should have a docstring"
    
    # Check for key documentation elements
    assert "composite indexes" in content.lower(), "Migration should document composite indexes"
    assert "concurrent" in content.lower(), "Migration should document CONCURRENT creation"
    assert "opportunities" in content.lower(), "Migration should document opportunities table"
    assert "contacts" in content.lower(), "Migration should document contacts table"
    assert "email_threads" in content.lower(), "Migration should document email_threads table"
    assert "assistant_tasks" in content.lower(), "Migration should document assistant_tasks table"
