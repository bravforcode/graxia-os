from __future__ import annotations

import warnings
from datetime import UTC, datetime, timedelta

import pytest
from app.core.auth import create_access_token, decode_access_token
from app.models.scraper_run import ScraperRun


def test_auth_token_round_trip_emits_no_deprecation_warning():
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        token = create_access_token({"sub": "00000000-0000-0000-0000-000000000001"})
        payload = decode_access_token(token)

    assert payload["sub"] == "00000000-0000-0000-0000-000000000001"
    assert not [warning for warning in caught if issubclass(warning.category, DeprecationWarning)]


def test_scraper_run_markers_use_timezone_aware_datetimes():
    run = ScraperRun(scraper_name="linkedin")

    run.mark_started()
    run.mark_completed()

    assert run.started_at is not None
    assert run.completed_at is not None
    assert run.started_at.tzinfo is not None
    assert run.completed_at.tzinfo is not None


@pytest.mark.asyncio
async def test_scraper_run_success_rate_query_works_with_case_expression(db_session):
    now = datetime.now(UTC)
    db_session.add_all(
        [
            ScraperRun(
                scraper_name="upwork",
                status="success",
                started_at=now - timedelta(days=1),
                completed_at=now - timedelta(days=1) + timedelta(minutes=3),
                items_found=10,
                items_new=6,
                items_updated=2,
            ),
            ScraperRun(
                scraper_name="upwork",
                status="failed",
                started_at=now - timedelta(hours=12),
                completed_at=now - timedelta(hours=12) + timedelta(minutes=1),
                error_message="timeout",
                items_found=0,
                items_new=0,
                items_updated=0,
            ),
            ScraperRun(
                scraper_name="linkedin",
                status="success",
                started_at=now - timedelta(days=1),
                completed_at=now - timedelta(days=1) + timedelta(minutes=2),
                items_found=5,
                items_new=4,
                items_updated=1,
            ),
        ]
    )
    await db_session.commit()

    success_rate = await ScraperRun.get_success_rate(db_session, "upwork", days=7)

    assert success_rate == 0.5
