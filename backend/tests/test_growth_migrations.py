import importlib.util
from pathlib import Path

import pytest
from alembic.migration import MigrationContext
from alembic.operations import Operations
from sqlalchemy import (
    CheckConstraint,
    Column,
    ForeignKey,
    Integer,
    MetaData,
    String,
    Table,
    create_engine,
    insert,
    select,
)
from sqlalchemy.exc import IntegrityError


VERSIONS = Path(__file__).parents[1] / "alembic" / "versions"


def _load_migration(filename: str):
    spec = importlib.util.spec_from_file_location(filename, VERSIONS / filename)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _run_migration(connection, migration, operation: str) -> None:
    context = MigrationContext.configure(connection)
    with Operations.context(context):
        getattr(migration, operation)()


def test_030_downgrade_normalizes_active_rows_before_restoring_constraint():
    migration = _load_migration("030_lead_magnet_active_status.py")
    metadata = MetaData()
    magnets = Table(
        "funnel_lead_magnets",
        metadata,
        Column("id", String, primary_key=True),
        Column("organization_id", String, nullable=False),
        Column("name", String, nullable=False),
        Column("slug", String, nullable=False),
        Column("target_product_id", String),
        Column("promise", String),
        Column("file_url", String),
        Column("landing_page_url", String),
        Column("status", String, nullable=False),
        Column("opt_in_count", Integer, nullable=False, server_default="0"),
        CheckConstraint(
            "status IN ('draft', 'active', 'published', 'archived')",
            name="ck_lead_magnet_status",
        ),
    )
    engine = create_engine("sqlite:///:memory:")
    metadata.create_all(engine)

    with engine.begin() as connection:
        connection.execute(
            insert(magnets),
            {
                "id": "mag-1",
                "organization_id": "org-1",
                "name": "Active magnet",
                "slug": "active-magnet",
                "status": "active",
            },
        )
        _run_migration(connection, migration, "downgrade")
        assert connection.scalar(select(magnets.c.status)) == "published"
        with pytest.raises(IntegrityError):
            connection.execute(
                insert(magnets),
                {
                    "id": "mag-2",
                    "organization_id": "org-1",
                    "name": "No active status",
                    "slug": "no-active-status",
                    "status": "active",
                },
            )


def test_031_downgrade_maps_published_runtime_magnet_and_fk():
    migration = _load_migration("031_align_lead_capture_runtime_fk.py")
    metadata = MetaData()
    organizations = Table("organizations", metadata, Column("id", String, primary_key=True))
    runtime = Table(
        "funnel_lead_magnets",
        metadata,
        Column("id", String, primary_key=True),
        Column("organization_id", String, ForeignKey("organizations.id")),
        Column("name", String, nullable=False),
        Column("slug", String, nullable=False),
        Column("promise", String),
        Column("status", String, nullable=False),
    )
    legacy = Table(
        "lead_magnets",
        metadata,
        Column("id", String, primary_key=True),
        Column("organization_id", String, ForeignKey("organizations.id")),
        Column("title", String, nullable=False),
        Column("slug", String, nullable=False),
        Column("description", String),
        Column("status", String, nullable=False),
        CheckConstraint(
            "status IN ('draft', 'active', 'archived')",
            name="ck_legacy_lead_magnet_status",
        ),
    )
    captures = Table(
        "lead_captures",
        metadata,
        Column("id", String, primary_key=True),
        Column("lead_magnet_id", String, ForeignKey("funnel_lead_magnets.id")),
    )
    engine = create_engine("sqlite:///:memory:")
    metadata.create_all(engine)

    with engine.begin() as connection:
        connection.execute(insert(organizations), {"id": "org-1"})
        connection.execute(
            insert(runtime),
            {
                "id": "mag-1",
                "organization_id": "org-1",
                "name": "Published magnet",
                "slug": "published-magnet",
                "promise": "Safe rollback",
                "status": "published",
            },
        )
        connection.execute(
            insert(captures), {"id": "capture-1", "lead_magnet_id": "mag-1"}
        )
        _run_migration(connection, migration, "downgrade")

        assert connection.scalar(select(legacy.c.status)) == "active"
        foreign_keys = connection.exec_driver_sql(
            "PRAGMA foreign_key_list(lead_captures)"
        ).fetchall()
        assert any(row[2] == "lead_magnets" for row in foreign_keys)
