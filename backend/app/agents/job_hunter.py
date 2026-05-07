"""
Job Hunter Agent

Automatically discovers job opportunities from multiple platforms,
scores them based on fit, and emits events for downstream processing.
"""
import logging
from datetime import UTC, datetime
from decimal import Decimal
from uuid import uuid4

from sqlalchemy import select

from app.agents.base import BaseAgent
from app.database import AsyncSessionLocal
from app.models.job_posting import JobPosting
from app.scrapers.devpost import DevpostScraper
from app.scrapers.fastwork import FastworkScraper
from app.scrapers.fiverr import FiverrScraper
from app.scrapers.linkedin import LinkedInScraper
from app.scrapers.upwork import UpworkScraper

logger = logging.getLogger(__name__)


class JobHunterAgent(BaseAgent):
    """
    Job Hunter Agent - discovers and scores job opportunities.
    
    Features:
    - Multi-platform scraping (LinkedIn, Upwork, Fiverr, Fastwork, DevPost)
    - Deduplication via source_hash
    - AI-powered fit scoring (0-10)
    - Skill gap analysis
    - Event emission for downstream agents
    
    Target: 50+ jobs/week (7+ jobs/day)
    """
    
    name = "job_hunter"
    
    def __init__(self):
        super().__init__()
        self.scrapers = []
        self._init_scrapers()
    
    def _init_scrapers(self):
        """Initialize all job scrapers."""
        # LinkedIn - 10 jobs/run
        self.scrapers.append(LinkedInScraper(
            keywords="python developer remote",
            location="remote"
        ))
        
        # Upwork - 10 jobs/run
        self.scrapers.append(UpworkScraper(
            keywords="python fastapi",
            category="web-mobile-software-dev"
        ))
        
        # Fiverr - 5 jobs/run
        self.scrapers.append(FiverrScraper(
            keywords="python development",
            category="programming-tech"
        ))
        
        # Fastwork - 15 jobs/run
        self.scrapers.append(FastworkScraper())
        
        # DevPost - 5 jobs/run
        self.scrapers.append(DevpostScraper())
    
    async def run(self) -> dict:
        """
        Run job discovery across all platforms.
        
        Returns:
            dict with discovered, new, duplicates counts
        """
        logger.info("JobHunterAgent: starting job discovery")
        
        discovered = 0
        new_jobs = 0
        duplicates = 0
        errors = []
        
        for scraper in self.scrapers:
            try:
                logger.info(f"Running scraper: {scraper.source_name}")
                raw_jobs = await scraper.run()
                
                for job_data in raw_jobs:
                    discovered += 1
                    
                    # Check if already exists
                    if await self._job_exists(job_data.get("source_hash")):
                        duplicates += 1
                        continue
                    
                    # Save new job
                    job = await self._save_job(job_data)
                    if job:
                        new_jobs += 1
                        
                        # Score job asynchronously
                        scored_job = await self._score_job(job)
                        
                        # Emit event for downstream agents
                        await self.bus.emit("job.found", {
                            "job_id": str(job.id),
                            "title": job.title,
                            "company": job.company,
                            "source_platform": job.source_platform,
                            "match_score": (
                                float(scored_job.match_score)
                                if scored_job and scored_job.match_score
                                else 0.0
                            ),
                        })
            except Exception as e:
                logger.error(f"Scraper {scraper.source_name} failed: {e}")
                errors.append({"scraper": scraper.source_name, "error": str(e)})
        
        result = {
            "discovered": discovered,
            "new": new_jobs,
            "duplicates": duplicates,
            "errors": errors
        }
        
        await self.log_audit(
            action="job_hunter.run",
            details=result,
            success=len(errors) == 0
        )
        
        logger.info(f"JobHunterAgent: completed - {result}")
        return result
    
    async def _job_exists(self, source_hash: str | None) -> bool:
        """Check if job already exists by source_hash."""
        if not source_hash:
            return False
        
        try:
            async with AsyncSessionLocal() as db:
                query = select(JobPosting).where(JobPosting.source_hash == source_hash)
                result = await db.execute(query)
                return result.scalar_one_or_none() is not None
        except Exception as e:
            logger.warning(f"Job existence check failed: {e}")
            return False
    
    async def _save_job(self, job_data: dict) -> JobPosting | None:
        """Save job to database."""
        try:
            async with AsyncSessionLocal() as db:
                job = JobPosting(
                    id=uuid4(),
                    title=job_data.get("title"),
                    company=job_data.get("company"),
                    source_platform=job_data.get("source_platform"),
                    source_url=job_data.get("source_url"),
                    location=job_data.get("location"),
                    job_type=job_data.get("job_type", "job"),
                    description=job_data.get("description"),
                    required_skills=job_data.get("required_skills", []),
                    source_hash=job_data.get("source_hash"),
                    raw_data=job_data.get("raw_data", {}),
                    status="discovered",
                    created_at=datetime.now(UTC),
                    updated_at=datetime.now(UTC)
                )
                
                db.add(job)
                await db.commit()
                await db.refresh(job)
                
                logger.info(f"Saved job: {job.title} from {job.source_platform}")
                return job
        except Exception as e:
            logger.error(f"Failed to save job: {e}")
            return None
    
    async def _score_job(self, job: JobPosting) -> JobPosting:
        """
        Score job based on fit with user profile.
        
        Scoring factors:
        - Skill match (40%)
        - Job type preference (20%)
        - Location preference (15%)
        - Company reputation (15%)
        - Compensation (10%)
        """
        try:
            # Get user skills from identity
            user_context = self.agent_context
            
            # Build scoring prompt
            system = """You are a job fit analyzer. Score jobs 0-10 based on:
- Skill match (40%): How well do required skills match user skills?
- Job type (20%): Does it match user preferences (remote, freelance, etc.)?
- Location (15%): Is location suitable?
- Company (15%): Is company reputable/interesting?
- Compensation (10%): Is pay reasonable?

Return JSON: {"score": 8.5, "summary": "Great fit because...", "matched_skills": ["python", "fastapi"], "skill_gaps": ["kubernetes"]}"""
            
            user = f"""User Profile:
{user_context}

Job:
Title: {job.title}
Company: {job.company}
Location: {job.location}
Type: {job.job_type}
Required Skills: {', '.join(job.required_skills or [])}
Description: {(job.description or '')[:500]}

Score this job."""
            
            result = await self.llm.complete_json(
                system=system,
                user=user,
                task_class="classification",
                complexity=3
            )
            
            # Update job with score
            async with AsyncSessionLocal() as db:
                query = select(JobPosting).where(JobPosting.id == job.id)
                result_obj = await db.execute(query)
                job_obj = result_obj.scalar_one_or_none()
                
                if job_obj:
                    job_obj.match_score = Decimal(str(result.get("score", 5.0)))
                    job_obj.fit_summary = result.get("summary")
                    job_obj.matched_skills = result.get("matched_skills", [])
                    job_obj.skill_gap_list = result.get("skill_gaps", [])
                    job_obj.last_scored_at = datetime.now(UTC)
                    
                    await db.commit()
                    await db.refresh(job_obj)
                    
                    logger.info(f"Scored job {job.title}: {job_obj.match_score}/10")
                    return job_obj
        except Exception as e:
            logger.error(f"Job scoring failed: {e}")
        return job
    
    async def get_top_jobs(self, limit: int = 10, min_score: float = 7.0) -> list[JobPosting]:
        """Get top-scored jobs."""
        try:
            async with AsyncSessionLocal() as db:
                query = (
                    select(JobPosting)
                    .where(JobPosting.match_score >= Decimal(str(min_score)))
                    .where(JobPosting.status == "discovered")
                    .order_by(JobPosting.match_score.desc())
                    .limit(limit)
                )
                result = await db.execute(query)
                return list(result.scalars().all())
        except Exception as e:
            logger.error(f"Failed to get top jobs: {e}")
            return []
    
    async def get_stats(self) -> dict:
        """Get job hunter statistics."""
        try:
            async with AsyncSessionLocal() as db:
                from sqlalchemy import func
                
                # Total jobs
                total_query = select(func.count(JobPosting.id))
                total_result = await db.execute(total_query)
                total = total_result.scalar() or 0
                
                # By status
                status_query = select(
                    JobPosting.status,
                    func.count(JobPosting.id)
                ).group_by(JobPosting.status)
                status_result = await db.execute(status_query)
                by_status = {row[0]: row[1] for row in status_result}
                
                # By platform
                platform_query = select(
                    JobPosting.source_platform,
                    func.count(JobPosting.id)
                ).group_by(JobPosting.source_platform)
                platform_result = await db.execute(platform_query)
                by_platform = {row[0]: row[1] for row in platform_result}
                
                # Average score
                avg_query = select(func.avg(JobPosting.match_score))
                avg_result = await db.execute(avg_query)
                avg_score = float(avg_result.scalar() or 0)
                
                return {
                    "total_jobs": total,
                    "by_status": by_status,
                    "by_platform": by_platform,
                    "average_score": round(avg_score, 2)
                }
        except Exception as e:
            logger.error(f"Failed to get stats: {e}")
            return {}


# Global instance
job_hunter_agent = JobHunterAgent()
