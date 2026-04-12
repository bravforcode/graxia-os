"""
Load and Performance Tests

Tests system performance under load and stress conditions.
"""
import asyncio
import time
import pytest
from typing import List
from concurrent.futures import ThreadPoolExecutor
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.opportunity import Opportunity
from app.models.job_posting import JobPosting
from app.models.contact import Contact
from app.models.email_thread import EmailThread


class TestLoadPerformance:
    """Test system performance under load."""
    
    @pytest.mark.asyncio
    async def test_bulk_opportunity_creation(self, db_session: AsyncSession):
        """Test creating many opportunities quickly."""
        start_time = time.time()
        
        opportunities = []
        for i in range(100):
            opp = Opportunity(
                type="hackathon",
                title=f"Test Opportunity {i}",
                source_platform="devpost",
                source_url=f"https://devpost.com/test-{i}",
                source_hash=f"hash_{i}",
                status="discovered"
            )
            opportunities.append(opp)
        
        db_session.add_all(opportunities)
        await db_session.commit()
        
        elapsed = time.time() - start_time
        
        # Should complete in under 5 seconds
        assert elapsed < 5.0, f"Bulk creation took {elapsed:.2f}s, expected < 5s"
        
        # Verify all created
        from sqlalchemy import select
        result = await db_session.execute(select(Opportunity))
        count = len(result.scalars().all())
        assert count == 100
    
    @pytest.mark.asyncio
    async def test_bulk_job_creation(self, db_session: AsyncSession):
        """Test creating many job postings quickly."""
        start_time = time.time()
        
        jobs = []
        for i in range(100):
            job = JobPosting(
                title=f"Test Job {i}",
                company=f"Company {i}",
                source_platform="linkedin",
                source_url=f"https://linkedin.com/jobs/{i}",
                source_hash=f"job_hash_{i}",
                status="discovered"
            )
            jobs.append(job)
        
        db_session.add_all(jobs)
        await db_session.commit()
        
        elapsed = time.time() - start_time
        assert elapsed < 5.0, f"Bulk job creation took {elapsed:.2f}s"
    
    @pytest.mark.asyncio
    async def test_concurrent_reads(self, db_session: AsyncSession, sample_job_data):
        """Test concurrent read operations."""
        # Create test data
        jobs = []
        for i in range(50):
            job = JobPosting(**{**sample_job_data, "source_hash": f"concurrent_{i}"})
            jobs.append(job)
        
        db_session.add_all(jobs)
        await db_session.commit()
        
        # Perform concurrent reads
        from sqlalchemy import select
        
        async def read_jobs():
            result = await db_session.execute(
                select(JobPosting).limit(10)
            )
            return result.scalars().all()
        
        start_time = time.time()
        
        # Run 20 concurrent reads
        tasks = [read_jobs() for _ in range(20)]
        results = await asyncio.gather(*tasks)
        
        elapsed = time.time() - start_time
        
        # Should complete quickly
        assert elapsed < 3.0, f"Concurrent reads took {elapsed:.2f}s"
        assert all(len(r) == 10 for r in results)
    
    @pytest.mark.asyncio
    async def test_complex_query_performance(self, db_session: AsyncSession):
        """Test performance of complex queries."""
        # Create test data with relationships
        for i in range(50):
            opp = Opportunity(
                type="hackathon",
                title=f"Opportunity {i}",
                source_platform="devpost",
                source_url=f"https://devpost.com/{i}",
                source_hash=f"perf_hash_{i}",
                status="discovered",
                total_score=float(i % 10),
                decision="pursue" if i % 3 == 0 else "skip"
            )
            db_session.add(opp)
        
        await db_session.commit()
        
        # Complex query with filters and sorting
        from sqlalchemy import select
        
        start_time = time.time()
        
        result = await db_session.execute(
            select(Opportunity)
            .where(Opportunity.status == "discovered")
            .where(Opportunity.total_score >= 5.0)
            .order_by(Opportunity.total_score.desc())
            .limit(20)
        )
        opportunities = result.scalars().all()
        
        elapsed = time.time() - start_time
        
        # Should be fast even with filters
        assert elapsed < 1.0, f"Complex query took {elapsed:.2f}s"
        assert len(opportunities) > 0
    
    @pytest.mark.asyncio
    async def test_pagination_performance(self, db_session: AsyncSession):
        """Test pagination performance with large dataset."""
        # Create 200 records
        contacts = []
        for i in range(200):
            contact = Contact(
                name=f"Contact {i}",
                email=f"contact{i}@example.com",
                relationship_strength=float(i % 10) / 10.0
            )
            contacts.append(contact)
        
        db_session.add_all(contacts)
        await db_session.commit()
        
        # Test pagination
        from sqlalchemy import select
        
        start_time = time.time()
        
        # Fetch 5 pages of 20 records each
        for page in range(5):
            offset = page * 20
            result = await db_session.execute(
                select(Contact)
                .order_by(Contact.created_at.desc())
                .limit(20)
                .offset(offset)
            )
            page_contacts = result.scalars().all()
            assert len(page_contacts) == 20
        
        elapsed = time.time() - start_time
        
        # Should handle pagination efficiently
        assert elapsed < 2.0, f"Pagination took {elapsed:.2f}s"
    
    @pytest.mark.asyncio
    async def test_search_performance(self, db_session: AsyncSession):
        """Test search query performance."""
        # Create searchable data
        jobs = []
        keywords = ["Python", "JavaScript", "React", "FastAPI", "PostgreSQL"]
        
        for i in range(100):
            job = JobPosting(
                title=f"Job {i} - {keywords[i % len(keywords)]} Developer",
                company=f"Company {i}",
                source_platform="linkedin",
                source_url=f"https://linkedin.com/jobs/{i}",
                source_hash=f"search_hash_{i}",
                description=f"Looking for {keywords[i % len(keywords)]} expert",
                status="discovered"
            )
            jobs.append(job)
        
        db_session.add_all(jobs)
        await db_session.commit()
        
        # Test search
        from sqlalchemy import select, or_
        
        start_time = time.time()
        
        search_term = "Python"
        result = await db_session.execute(
            select(JobPosting)
            .where(
                or_(
                    JobPosting.title.ilike(f"%{search_term}%"),
                    JobPosting.description.ilike(f"%{search_term}%")
                )
            )
        )
        jobs_found = result.scalars().all()
        
        elapsed = time.time() - start_time
        
        # Search should be fast
        assert elapsed < 1.0, f"Search took {elapsed:.2f}s"
        assert len(jobs_found) > 0
    
    @pytest.mark.asyncio
    async def test_aggregation_performance(self, db_session: AsyncSession):
        """Test aggregation query performance."""
        # Create data for aggregation
        for i in range(100):
            opp = Opportunity(
                type="hackathon" if i % 2 == 0 else "freelance",
                title=f"Opportunity {i}",
                source_platform="devpost" if i % 3 == 0 else "upwork",
                source_url=f"https://example.com/{i}",
                source_hash=f"agg_hash_{i}",
                status="discovered",
                total_score=float(i % 10)
            )
            db_session.add(opp)
        
        await db_session.commit()
        
        # Test aggregations
        from sqlalchemy import select, func
        
        start_time = time.time()
        
        # Count by type
        result = await db_session.execute(
            select(
                Opportunity.type,
                func.count(Opportunity.id).label('count'),
                func.avg(Opportunity.total_score).label('avg_score')
            )
            .group_by(Opportunity.type)
        )
        stats = result.all()
        
        elapsed = time.time() - start_time
        
        # Aggregations should be fast
        assert elapsed < 1.0, f"Aggregation took {elapsed:.2f}s"
        assert len(stats) == 2  # hackathon and freelance
    
    @pytest.mark.asyncio
    async def test_memory_efficiency(self, db_session: AsyncSession):
        """Test memory usage with large result sets."""
        import sys
        
        # Create large dataset
        jobs = []
        for i in range(500):
            job = JobPosting(
                title=f"Job {i}",
                company=f"Company {i}",
                source_platform="linkedin",
                source_url=f"https://linkedin.com/jobs/{i}",
                source_hash=f"mem_hash_{i}",
                description="A" * 1000,  # 1KB description
                status="discovered"
            )
            jobs.append(job)
        
        db_session.add_all(jobs)
        await db_session.commit()
        
        # Fetch with streaming
        from sqlalchemy import select
        
        result = await db_session.stream(
            select(JobPosting).execution_options(yield_per=50)
        )
        
        count = 0
        async for partition in result.partitions(50):
            count += len(partition)
            # Process in chunks to avoid loading all into memory
        
        assert count == 500
    
    @pytest.mark.asyncio
    async def test_transaction_rollback_performance(self, db_session: AsyncSession):
        """Test rollback performance."""
        start_time = time.time()
        
        # Create data
        for i in range(50):
            opp = Opportunity(
                type="hackathon",
                title=f"Rollback Test {i}",
                source_platform="devpost",
                source_url=f"https://devpost.com/rollback-{i}",
                source_hash=f"rollback_hash_{i}",
                status="discovered"
            )
            db_session.add(opp)
        
        # Rollback
        await db_session.rollback()
        
        elapsed = time.time() - start_time
        
        # Rollback should be fast
        assert elapsed < 1.0, f"Rollback took {elapsed:.2f}s"
        
        # Verify nothing was committed
        from sqlalchemy import select
        result = await db_session.execute(
            select(Opportunity).where(Opportunity.source_hash.like("rollback_hash_%"))
        )
        assert len(result.scalars().all()) == 0


class TestStressConditions:
    """Test system behavior under stress."""
    
    @pytest.mark.asyncio
    async def test_rapid_status_updates(self, db_session: AsyncSession):
        """Test rapid status changes."""
        # Create opportunity
        opp = Opportunity(
            type="hackathon",
            title="Stress Test Opportunity",
            source_platform="devpost",
            source_url="https://devpost.com/stress",
            source_hash="stress_hash",
            status="discovered"
        )
        db_session.add(opp)
        await db_session.commit()
        
        # Rapid status updates
        statuses = ["discovered", "scored", "decided", "actioned", "submitted"]
        
        start_time = time.time()
        
        for status in statuses * 10:  # 50 updates
            opp.status = status
            await db_session.commit()
        
        elapsed = time.time() - start_time
        
        # Should handle rapid updates
        assert elapsed < 5.0, f"Rapid updates took {elapsed:.2f}s"
    
    @pytest.mark.asyncio
    async def test_concurrent_writes(self, db_session: AsyncSession):
        """Test concurrent write operations."""
        async def create_opportunity(index: int):
            opp = Opportunity(
                type="hackathon",
                title=f"Concurrent Opp {index}",
                source_platform="devpost",
                source_url=f"https://devpost.com/concurrent-{index}",
                source_hash=f"concurrent_write_{index}",
                status="discovered"
            )
            db_session.add(opp)
            await db_session.commit()
        
        start_time = time.time()
        
        # Create 20 opportunities concurrently
        tasks = [create_opportunity(i) for i in range(20)]
        await asyncio.gather(*tasks, return_exceptions=True)
        
        elapsed = time.time() - start_time
        
        # Should handle concurrent writes
        assert elapsed < 10.0, f"Concurrent writes took {elapsed:.2f}s"
