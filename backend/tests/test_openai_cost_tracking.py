import importlib.util
from decimal import Decimal
from pathlib import Path
from unittest.mock import AsyncMock

from alembic.migration import MigrationContext
from alembic.operations import Operations
import pytest
from sqlalchemy import create_engine, inspect, text

from app.core.cost_tracker import CostTracker


class FakeCostQueryResult:
    def __init__(self, total):
        self.total = total

    def scalar(self):
        return self.total


class FakeCostSession:
    rows = []

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, traceback):
        return None

    def add(self, row):
        self.rows.append(row)

    async def commit(self):
        return None

    async def execute(self, _query):
        return FakeCostQueryResult(sum((row.cost_usd for row in self.rows), Decimal("0")))


@pytest.mark.asyncio
async def test_openai_usage_is_persisted_and_included_in_existing_cost_totals(monkeypatch):
    FakeCostSession.rows = []
    tracker = CostTracker()
    tracker._check_budget_alerts = AsyncMock()
    monkeypatch.setattr("app.core.cost_tracker.AsyncSessionLocal", FakeCostSession)

    tracked = True
    for _ in range(2):
        tracked = await tracker.track_openai_cost(
            model="account-model-test",
            input_tokens=1,
            output_tokens=1,
            cost_usd=0.00000028,
        ) and tracked
    daily_cost = await tracker.get_daily_cost()
    monthly_cost = await tracker.get_monthly_cost()

    assert tracked is True
    assert len(FakeCostSession.rows) == 2
    assert all(row.platform == "openai/account-model-test" for row in FakeCostSession.rows)
    assert all(row.action == "generate" for row in FakeCostSession.rows)
    assert all(row.cost_usd == Decimal("0.00000028") for row in FakeCostSession.rows)
    assert daily_cost == pytest.approx(0.00000056)
    assert monthly_cost == pytest.approx(0.00000056)


@pytest.mark.asyncio
async def test_openai_tiny_cost_rows_aggregate_in_sqlite_database(db_session):
    tracker = CostTracker()
    tracker._check_budget_alerts = AsyncMock()

    for _ in range(2):
        assert await tracker.track_openai_cost(
            model="account-model-test",
            input_tokens=1,
            output_tokens=1,
            cost_usd=0.00000028,
        ) is True

    assert await tracker.get_daily_cost() == pytest.approx(0.00000056, abs=1e-12)


@pytest.mark.asyncio
async def test_openai_cost_tracking_rejects_invalid_values():
    tracker = CostTracker()

    assert await tracker.track_openai_cost("", 1, 1, 0.1) is False
    assert await tracker.track_openai_cost("model", -1, 1, 0.1) is False
    assert await tracker.track_openai_cost("model", 1, 1, float("nan")) is False


def test_cost_precision_migration_preserves_existing_data_and_tiny_row_sums():
    migration_path = (
        Path(__file__).parents[1]
        / "alembic"
        / "versions"
        / "036_openclaw_cost_precision.py"
    )
    spec = importlib.util.spec_from_file_location(
        "migration_036_openclaw_cost_precision", migration_path
    )
    assert spec is not None and spec.loader is not None
    migration = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(migration)

    engine = create_engine("sqlite:///:memory:")
    with engine.begin() as connection:
        connection.execute(
            text(
                "CREATE TABLE openclaw_usage "
                "(id INTEGER PRIMARY KEY, cost_usd NUMERIC(10, 4) NOT NULL, marker TEXT NOT NULL)"
            )
        )
        connection.execute(
            text("INSERT INTO openclaw_usage(cost_usd, marker) VALUES (0.1234, 'existing')")
        )
        migration.op = Operations(MigrationContext.configure(connection))

        migration.upgrade()

        cost_column = next(
            column
            for column in inspect(connection).get_columns("openclaw_usage")
            if column["name"] == "cost_usd"
        )
        assert cost_column["type"].precision == 20
        assert cost_column["type"].scale == 12
        connection.execute(
            text(
                "INSERT INTO openclaw_usage(cost_usd, marker) "
                "VALUES (0.00000028, 'tiny-1'), (0.00000028, 'tiny-2')"
            )
        )
        total = connection.execute(
            text("SELECT SUM(cost_usd) FROM openclaw_usage")
        ).scalar_one()

        assert float(total) == pytest.approx(0.12340056, abs=1e-10)

    engine.dispose()
