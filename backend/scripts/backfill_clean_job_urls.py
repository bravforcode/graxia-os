"""
Backfill script to normalize job_postings source URLs and hashes.
Strips query parameters (e.g., refId, position, pageNum from LinkedIn)
and deletes duplicate copies created by prior runs.

Usage:
  python scripts/backfill_clean_job_urls.py --dry-run
  python scripts/backfill_clean_job_urls.py --execute
"""
import argparse
import asyncio
import hashlib
import logging
import sys
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sqlalchemy import delete, select

from app.database import AsyncSessionLocal
from app.models.job_posting import JobPosting

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("backfill_clean_job_urls")


def compute_source_hash(url: str, title: str) -> str:
    raw = url + title[:100]
    return hashlib.sha256(raw.encode()).hexdigest()


async def run_backfill(execute: bool = False) -> dict:
    mode_str = "EXECUTE" if execute else "DRY-RUN"
    logger.info("Starting job_postings URL backfill [%s]...", mode_str)

    async with AsyncSessionLocal() as session:
        result = await session.execute(
            select(JobPosting).order_by(JobPosting.created_at.asc(), JobPosting.id.asc())
        )
        all_jobs = list(result.scalars().all())

        total_rows = len(all_jobs)
        logger.info("Found %d total job postings in database.", total_rows)

        # Group by clean URL
        grouped: dict[str, list[JobPosting]] = defaultdict(list)
        for job in all_jobs:
            if not job.source_url:
                continue
            clean_url = job.source_url.split("?", 1)[0]
            grouped[clean_url].append(job)

        rows_to_keep: list[JobPosting] = []
        rows_to_update: list[tuple[JobPosting, str, str]] = []  # (job, clean_url, clean_hash)
        ids_to_delete: list = []

        for clean_url, jobs in grouped.items():
            # Find if there is already a perfectly clean row
            canonical = next((j for j in jobs if j.source_url == clean_url), None)
            if not canonical:
                # Pick the earliest created row as canonical
                canonical = jobs[0]
                new_hash = compute_source_hash(clean_url, canonical.title)
                rows_to_update.append((canonical, clean_url, new_hash))

            rows_to_keep.append(canonical)

            # All other rows in this group are redundant duplicates
            for duplicate in jobs:
                if duplicate.id != canonical.id:
                    ids_to_delete.append(duplicate.id)

        stats = {
            "total_rows": total_rows,
            "unique_clean_jobs": len(grouped),
            "rows_kept": len(rows_to_keep),
            "rows_updated": len(rows_to_update),
            "duplicates_to_delete": len(ids_to_delete),
        }

        logger.info(
            "Analysis complete: %d total rows -> %d unique jobs (%d to keep, %d to update, %d to delete).",
            stats["total_rows"],
            stats["unique_clean_jobs"],
            stats["rows_kept"],
            stats["rows_updated"],
            stats["duplicates_to_delete"],
        )

        if execute:
            # 1. Delete duplicates first to avoid unique constraint violations on (source_hash)
            if ids_to_delete:
                logger.info("Deleting %d duplicate rows in chunks...", len(ids_to_delete))
                chunk_size = 500
                for i in range(0, len(ids_to_delete), chunk_size):
                    chunk = ids_to_delete[i : i + chunk_size]
                    await session.execute(
                        delete(JobPosting).where(JobPosting.id.in_(chunk))
                    )

            # 2. Update canonical rows that had query parameters
            if rows_to_update:
                logger.info("Updating %d canonical rows with clean URL & hash...", len(rows_to_update))
                for job, clean_url, new_hash in rows_to_update:
                    job.source_url = clean_url
                    job.source_hash = new_hash

            await session.commit()
            logger.info("SUCCESS: Backfill committed successfully.")
        else:
            logger.info("DRY-RUN completed: No database changes were made.")

        return stats


def main() -> None:
    parser = argparse.ArgumentParser(description="Backfill clean URLs for job postings")
    parser.add_argument(
        "--execute",
        action="store_true",
        help="Actually apply changes to database (default is dry-run)",
    )
    args = parser.parse_args()

    asyncio.run(run_backfill(execute=args.execute))


if __name__ == "__main__":
    main()
