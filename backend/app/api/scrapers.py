import logging
from datetime import UTC, datetime, timedelta

from fastapi import APIRouter
from sqlalchemy import select

from app.database import AsyncSessionLocal
from app.models.scraper_health import ScraperHealth

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/scrapers", tags=["scrapers"])


def _as_utc(dt: datetime | None) -> datetime | None:
    if dt is None:
        return None
    if dt.tzinfo is None:
        return dt.replace(tzinfo=UTC)
    return dt.astimezone(UTC)


def _derive_scraper_status(record: ScraperHealth) -> str:
    now = datetime.now(UTC)
    muted_until = _as_utc(record.muted_until)
    if record.is_muted and (muted_until is None or muted_until > now):
        return "muted"
    if (record.consecutive_failures or 0) > 0:
        return "error"
    if record.last_success_at is not None:
        return "success"
    return "unknown"


@router.get("/health")
async def get_scrapers_health():
    async with AsyncSessionLocal() as db:
        result = await db.execute(select(ScraperHealth).order_by(ScraperHealth.source_name))
        health_records = list(result.scalars().all())

        scrapers = []
        now = datetime.now(UTC)
        for record in health_records:
            last_run_at = _as_utc(record.last_attempted_at) or _as_utc(record.last_success_at)
            time_since_run = None
            if last_run_at:
                time_since_run = int((now - last_run_at).total_seconds())
            status = _derive_scraper_status(record)
            scrapers.append(
                {
                    "name": record.source_name,
                    "status": status,
                    "last_run_at": last_run_at.isoformat() if last_run_at else None,
                    "time_since_run_seconds": time_since_run,
                    "results_count": int(record.avg_items_per_run or 0),
                    "error_message": record.last_error,
                    "is_healthy": status == "success" and (time_since_run is None or time_since_run < 86400),
                }
            )

        return {
            "total_scrapers": len(scrapers),
            "healthy": sum(1 for s in scrapers if s["is_healthy"]),
            "unhealthy": sum(1 for s in scrapers if not s["is_healthy"]),
            "scrapers": scrapers,
        }


@router.get("/health/{scraper_name}")
async def get_scraper_health(scraper_name: str):
    async with AsyncSessionLocal() as db:
        record = (
            await db.execute(select(ScraperHealth).where(ScraperHealth.source_name == scraper_name))
        ).scalar_one_or_none()

        if not record:
            return {
                "scraper_name": scraper_name,
                "found": False,
                "message": "No health records found",
            }

        return {
            "scraper_name": scraper_name,
            "found": True,
            "statistics": {
                "total_runs": int(record.total_runs or 0),
                "successful_runs": int(record.total_successes or 0),
                "failed_runs": max(int(record.total_runs or 0) - int(record.total_successes or 0), 0),
                "success_rate": float(record.success_rate or 0),
                "avg_results_per_run": float(record.avg_items_per_run or 0),
            },
            "latest_status": _derive_scraper_status(record),
            "latest_run": (_as_utc(record.last_attempted_at) or _as_utc(record.last_success_at)).isoformat()
            if (_as_utc(record.last_attempted_at) or _as_utc(record.last_success_at))
            else None,
            "latest_error": record.last_error,
        }


@router.get("/stats")
async def get_scraper_stats():
    async with AsyncSessionLocal() as db:
        since = datetime.now(UTC) - timedelta(days=7)
        result = await db.execute(select(ScraperHealth))
        records = list(result.scalars().all())

        total_runs = 0
        successful_runs = 0
        total_results = 0
        by_scraper = {}

        for record in records:
            last_attempted_at = _as_utc(record.last_attempted_at)
            if last_attempted_at and last_attempted_at < since:
                continue
            runs = int(record.total_runs or 0)
            successes = int(record.total_successes or 0)
            failures = max(runs - successes, 0)
            results = int(record.avg_items_per_run or 0)
            total_runs += runs
            successful_runs += successes
            total_results += results
            by_scraper[record.source_name] = {
                "runs": runs,
                "successes": successes,
                "failures": failures,
                "results": results,
            }

        failed_runs = max(total_runs - successful_runs, 0)
        return {
            "period_days": 7,
            "total_runs": total_runs,
            "successful_runs": successful_runs,
            "failed_runs": failed_runs,
            "success_rate": round((successful_runs / total_runs * 100) if total_runs > 0 else 0, 2),
            "total_results": total_results,
            "by_scraper": by_scraper,
        }
