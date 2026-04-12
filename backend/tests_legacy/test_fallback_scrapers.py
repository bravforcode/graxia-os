"""
Fallback Scraper Tests

Tests for fallback scrapers that work without OpenClaw.
"""
import pytest

from app.scrapers.fallback import (
    LinkedInFallbackScraper,
    UpworkFallbackScraper,
    FiverrFallbackScraper,
)


class TestLinkedInFallbackScraper:
    """Test LinkedIn fallback scraper."""
    
    @pytest.mark.asyncio
    async def test_run(self):
        """Test LinkedIn fallback scraper run."""
        scraper = LinkedInFallbackScraper()
        
        jobs = await scraper.run(keywords="python developer")
        
        # Should return list (may be empty if no jobs found)
        assert isinstance(jobs, list)
        
        # If jobs found, check structure
        if jobs:
            job = jobs[0]
            assert "title" in job
            assert "company" in job
            assert "source_platform" in job
            assert job["source_platform"] == "linkedin"
            assert "source_url" in job
            assert "source_hash" in job
    
    @pytest.mark.asyncio
    async def test_hash_calculation(self):
        """Test hash calculation for deduplication."""
        scraper = LinkedInFallbackScraper()
        
        hash1 = scraper._calculate_hash("linkedin", "job123")
        hash2 = scraper._calculate_hash("linkedin", "job123")
        hash3 = scraper._calculate_hash("linkedin", "job456")
        
        # Same input should produce same hash
        assert hash1 == hash2
        
        # Different input should produce different hash
        assert hash1 != hash3
        
        # Hash should be 64 characters (SHA256)
        assert len(hash1) == 64


class TestUpworkFallbackScraper:
    """Test Upwork fallback scraper."""
    
    @pytest.mark.asyncio
    async def test_run(self):
        """Test Upwork fallback scraper run."""
        scraper = UpworkFallbackScraper()
        
        jobs = await scraper.run(keywords="python")
        
        assert isinstance(jobs, list)
        
        if jobs:
            job = jobs[0]
            assert "title" in job
            assert "source_platform" in job
            assert job["source_platform"] == "upwork"
            assert job["job_type"] == "freelance"


class TestFiverrFallbackScraper:
    """Test Fiverr fallback scraper."""
    
    @pytest.mark.asyncio
    async def test_run(self):
        """Test Fiverr fallback scraper run."""
        scraper = FiverrFallbackScraper()
        
        jobs = await scraper.run(keywords="python development")
        
        assert isinstance(jobs, list)
        
        if jobs:
            job = jobs[0]
            assert "title" in job
            assert "source_platform" in job
            assert job["source_platform"] == "fiverr"
            assert job["job_type"] == "gig"
    
    @pytest.mark.asyncio
    async def test_error_handling(self):
        """Test error handling in fallback scrapers."""
        scraper = FiverrFallbackScraper()
        
        # Should not raise exception even with invalid input
        jobs = await scraper.run(keywords="")
        
        assert isinstance(jobs, list)
