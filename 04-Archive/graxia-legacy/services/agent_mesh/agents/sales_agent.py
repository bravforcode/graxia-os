import os
import uuid
import requests
import logging
import google.generativeai as genai
from datetime import datetime, timezone
from typing import Any, List, Optional
from pydantic import BaseModel, Field

from graxia.packages.bravos_core.python.agent import BaseBravOSAgent
from graxia.packages.bwcp_protocol.models import BWCPMessage, BWCPMessageType, BWCPPriority
from graxia.packages.outbound.python.email_engine import EmailEngine

logger = logging.getLogger(__name__)

class JobPosting(BaseModel):
    """Strict Pydantic V2 model for JobPosting"""
    job_id: str = Field(..., description="Unique identifier for the job")
    title: str = Field(..., description="Job title")
    platform: str = Field(..., description="Platform where the job was found (e.g., Upwork, Freelancer)")
    budget: str = Field(..., description="Estimated budget or hourly rate")
    description: str = Field(..., description="Job description")

class Proposal(BaseModel):
    """Strict Pydantic V2 model for Proposal"""
    proposal_id: str = Field(default_factory=lambda: str(uuid.uuid4()), description="Unique ID for the proposal")
    job_id: str = Field(..., description="Associated job ID")
    content: str = Field(..., description="Drafted proposal content")
    status: str = Field(default="draft", description="Proposal status")

class SalesAgent(BaseBravOSAgent):
    """
    Sales Agent responsible for finding jobs and drafting personalized proposals.
    Supports LIVE_MODE using SerpApi and Google Gemini.
    """
    def __init__(self):
        super().__init__(agent_id="sales_agent", agent_type="Sales")
        self.email_engine = EmailEngine()
        self.live_mode = os.getenv("LIVE_MODE") == "true"
        
        if self.live_mode:
            gemini_key = os.getenv("GEMINI_API_KEY")
            if gemini_key:
                genai.configure(api_key=gemini_key)
            else:
                logger.error("LIVE_MODE is true but GEMINI_API_KEY is missing.")

    async def _fetch_jobs(self) -> List[JobPosting]:
        """Fetch jobs from SerpApi if LIVE_MODE, otherwise return stub jobs."""
        if not self.live_mode:
            return self._get_stub_jobs()

        serpapi_key = os.getenv("SERPAPI_API_KEY")
        if not serpapi_key:
            logger.warning("SERPAPI_API_KEY missing in LIVE_MODE. Falling back to stub jobs.")
            return self._get_stub_jobs()

        url = "https://serpapi.com/search.json"
        params = {
            "q": "Upwork FastAPI jobs budget 50",
            "api_key": serpapi_key,
            "engine": "google" 
        }

        try:
            # Using requests (blocking) - in a production async app we'd use httpx
            # but following instructions to use 'requests'.
            response = requests.get(url, params=params, timeout=10)
            response.raise_for_status()
            data = response.json()
            
            jobs: List[JobPosting] = []
            results = data.get("organic_results", [])[:5]
            
            for idx, result in enumerate(results):
                jobs.append(JobPosting(
                    job_id=f"live_{idx}_{uuid.uuid4().hex[:4]}",
                    title=result.get("title", "Unknown Job"),
                    platform="SerpApi/Upwork",
                    budget="Check site",
                    description=result.get("snippet", "No description available.")
                ))
            
            if not jobs:
                logger.info("SerpApi returned no results. Using stubs.")
                return self._get_stub_jobs()
                
            return jobs
        except Exception as e:
            logger.error(f"Failed to fetch jobs from SerpApi: {e}")
            return self._get_stub_jobs()

    def _get_stub_jobs(self) -> List[JobPosting]:
        """Hardcoded fallback jobs."""
        return [
            JobPosting(
                job_id="job_001",
                title="Full Stack Next.js Developer",
                platform="Upwork",
                budget="$50-$80/hr",
                description="Looking for an expert to build a scalable dashboard."
            ),
            JobPosting(
                job_id="job_002",
                title="Python FastAPI Backend Engineer",
                platform="Freelancer",
                budget="$4000 fixed",
                description="Need a robust API for a mobile application."
            ),
            JobPosting(
                job_id="job_003",
                title="AI Agent Developer",
                platform="Upwork",
                budget="$60-$100/hr",
                description="Build custom LLM agents using LangChain."
            ),
            JobPosting(
                job_id="job_004",
                title="Database Architect (PostgreSQL)",
                platform="Toptal",
                budget="$3000 fixed",
                description="Optimize and migrate existing database."
            ),
            JobPosting(
                job_id="job_005",
                title="DevOps Engineer for GCP",
                platform="Upwork",
                budget="$70/hr",
                description="Setup CI/CD and Kubernetes on Google Cloud."
            )
        ]

    async def _draft_proposal(self, job: JobPosting) -> str:
        """Draft a proposal using Gemini if LIVE_MODE, otherwise use template."""
        if not self.live_mode or not os.getenv("GEMINI_API_KEY"):
            return f"Hello, I am an expert in this field and can perfectly handle your project '{job.title}'. With my extensive experience, I can deliver high-quality results matching your budget of {job.budget}."

        try:
            model = genai.GenerativeModel('gemini-1.5-flash')
            prompt = f"""
            System: You are an expert freelance Sales Agent for BravOS, a specialized agency for FastAPI and Next.js development.
            
            Task: Write a personalized, persuasive, and professional Upwork proposal for the following job:
            
            Job Title: {job.title}
            Description: {job.description}
            
            Tone: Professional, confident, and value-driven.
            Constraint: Keep it under 200 words. Mention that we specialize in building AI-powered autonomous systems.
            """
            # Using the async generation method
            response = await model.generate_content_async(prompt)
            return response.text.strip()
        except Exception as e:
            logger.error(f"Gemini proposal generation failed: {e}")
            return f"Draft proposal for {job.title} (Fallback: Gemini failed)"

    async def execute_task(self, message: BWCPMessage) -> BWCPMessage:
        """
        Execute the job search and proposal drafting task.
        """
        # 1. Fetch Jobs
        jobs = await self._fetch_jobs()

        # 2. Draft Proposals
        proposals: List[Proposal] = []
        for job in jobs:
            content = await self._draft_proposal(job)
            proposals.append(Proposal(job_id=job.job_id, content=content))

        # 3. Notify via Email
        summary = f"Found {len(jobs)} jobs and drafted {len(proposals)} proposals."
        email_body = f"<h2>Sales Agent Report</h2><p>{summary}</p><ul>"
        for job in jobs:
            email_body += f"<li><strong>{job.title}</strong> at {job.platform}</li>"
        email_body += "</ul>"
        
        # EmailEngine handles stub vs live based on its own LIVE_MODE check
        await self.email_engine.send_email(
            to_address="admin@bravos.ai",
            subject=f"Sales Alert: {len(jobs)} New Opportunities Found",
            body=email_body
        )

        # 4. Return Result
        payload = {
            "jobs_found": [job.model_dump() for job in jobs],
            "proposals_drafted": [prop.model_dump() for prop in proposals],
            "summary": summary
        }

        return BWCPMessage(
            message_id=str(uuid.uuid4()),
            sender_agent=self.agent_id,
            receiver_agent=message.sender_agent,
            mission_id=message.mission_id,
            task_id=message.task_id,
            type=BWCPMessageType.TASK_RESULT,
            priority=BWCPPriority.NORMAL,
            payload=payload
        )
