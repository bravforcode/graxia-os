import pytest
from sqlalchemy import text

from app.database import AsyncSessionLocal
from app.tasks.async_runner import run_async


async def _select_one() -> int:
    async with AsyncSessionLocal() as session:
        result = await session.execute(text("SELECT 1"))
        return result.scalar_one()


async def _fail() -> None:
    raise ValueError("boom")


def test_run_async_returns_db_result():
    assert run_async(_select_one()) == 1


def test_run_async_propagates_errors():
    with pytest.raises(ValueError, match="boom"):
        run_async(_fail())
