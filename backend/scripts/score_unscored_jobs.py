"""
Script to batch-score all unscored job_postings using JobHunterAgent.
Scores jobs against the mounted profile.yaml via the configured LLM.
"""
import asyncio
import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sqlalchemy import select

from app.agents.job_hunter import JobHunterAgent
from app.database import AsyncSessionLocal
from app.models.job_posting import JobPosting

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("score_unscored_jobs")


async def main() -> None:
    logger.info("Initializing JobHunterAgent for batch scoring...")
    hunter = JobHunterAgent()

    async with AsyncSessionLocal() as session:
        query = (
            select(JobPosting)
            .where(JobPosting.match_score.is_(None))
            .order_by(JobPosting.created_at.desc())
        )
        result = await session.execute(query)
        unscored_jobs = list(result.scalars().all())

    logger.info("Found %d unscored job postings.", len(unscored_jobs))
    if not unscored_jobs:
        logger.info("No unscored jobs found. All jobs have scores!")
        return

    scored_count = 0
    for idx, job in enumerate(unscored_jobs, 1):
        logger.info("[%d/%d] Scoring: %s at %s...", idx, len(unscored_jobs), job.title, job.company)
        try:
            scored_job = await hunter._score_job(job)
            if scored_job and scored_job.match_score is not None:
                scored_count += 1
                logger.info(
                    " -> Score: %s/10 | Summary: %s",
                    scored_job.match_score,
                    (scored_job.fit_summary or "")[:80],
                )
            else:
                logger.warning(" -> Scored job returned None or score is NULL")
        except Exception as e:
            logger.error(" -> Failed to score %s: %e", job.title, e)

    logger.info("Batch scoring complete: %d/%d jobs scored successfully.", scored_count, len(unscored_jobs))


if __name__ == "__main__":
    asyncio.run(main())
