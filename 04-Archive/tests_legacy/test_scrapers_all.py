"""
Tests for all scrapers
"""
import pytest
from unittest.mock import Mock, patch, AsyncMock


@pytest.mark.asyncio
async def test_linkedin_scraper():
    """Test LinkedIn scraper"""
    from app.scrapers.linkedin import LinkedInScraper
    
    scraper = LinkedInScraper(keywords="python developer", location="remote")
    
    # Mock OpenClaw response
    with patch('app.scrapers.linkedin.openclaw_client') as mock_openclaw:
        mock_openclaw.extract_jobs = AsyncMock(return_value=[
            {
                "title": "Python Developer",
                "company": "Tech Corp",
                "location": "Remote",
                "url": "https://linkedin.com/jobs/123",
            }
        ])
        
        results = await scraper.run()
        
        assert len(results) > 0
        assert results[0]["title"] == "Python Developer"
        assert results[0]["source_platform"] == "linkedin"


@pytest.mark.asyncio
async def test_upwork_scraper():
    """Test Upwork scraper"""
    from app.scrapers.upwork import UpworkScraper
    
    scraper = UpworkScraper(keywords="python fastapi", category="web-mobile-software-dev")
    
    with patch('app.scrapers.upwork.openclaw_client') as mock_openclaw:
        mock_openclaw.extract_jobs = AsyncMock(return_value=[
            {
                "title": "FastAPI Developer Needed",
                "description": "Build REST API",
                "budget": "$500-1000",
                "url": "https://upwork.com/jobs/123",
            }
        ])
        
        results = await scraper.run()
        
        assert len(results) > 0
        assert results[0]["source_platform"] == "upwork"


@pytest.mark.asyncio
async def test_fiverr_scraper():
    """Test Fiverr scraper"""
    from app.scrapers.fiverr import FiverrScraper
    
    scraper = FiverrScraper(keywords="python development", category="programming-tech")
    
    with patch('app.scrapers.fiverr.openclaw_client') as mock_openclaw:
        mock_openclaw.scrape_url = AsyncMock(return_value={
            "data": {
                "gigs": [
                    {
                        "title": "I will develop python application",
                        "seller": "developer123",
                        "price": "$50",
                        "url": "https://fiverr.com/gigs/123",
                    }
                ]
            }
        })
        
        results = await scraper.run()
        
        assert len(results) > 0
        assert results[0]["source_platform"] == "fiverr"


@pytest.mark.asyncio
async def test_fastwork_scraper():
    """Test Fastwork scraper"""
    from app.scrapers.fastwork import FastworkScraper
    
    scraper = FastworkScraper()
    
    with patch('httpx.AsyncClient.get') as mock_get:
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.text = """
        <div class="job-card">
            <h3>Python Developer</h3>
            <div class="company">Tech Company</div>
            <div class="budget">฿30,000-50,000</div>
        </div>
        """
        mock_get.return_value = mock_response
        
        results = await scraper.run()
        
        # Should parse HTML and extract jobs
        assert isinstance(results, list)


@pytest.mark.asyncio
async def test_devpost_scraper():
    """Test DevPost scraper"""
    from app.scrapers.devpost import DevpostScraper
    
    scraper = DevpostScraper()
    
    with patch('httpx.AsyncClient.get') as mock_get:
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.text = """
        <div class="hackathon">
            <h3>AI Hackathon 2024</h3>
            <div class="prize">$10,000</div>
            <div class="deadline">2024-12-31</div>
        </div>
        """
        mock_get.return_value = mock_response
        
        results = await scraper.run()
        
        assert isinstance(results, list)


@pytest.mark.asyncio
async def test_rss_reader_scraper():
    """Test RSS Reader scraper"""
    from app.scrapers.rss_reader import RSSReaderScraper
    
    scraper = RSSReaderScraper(feed_urls=["https://example.com/feed.xml"])
    
    with patch('feedparser.parse') as mock_parse:
        mock_parse.return_value = {
            "entries": [
                {
                    "title": "Job Opening: Python Developer",
                    "link": "https://example.com/job/123",
                    "summary": "We are hiring",
                    "published": "2024-01-15",
                }
            ]
        }
        
        results = await scraper.run()
        
        assert len(results) > 0
        assert results[0]["source_platform"] == "rss"


@pytest.mark.asyncio
async def test_serpapi_search_scraper():
    """Test SerpAPI Search scraper"""
    from app.scrapers.serpapi_search import SerpAPISearchScraper
    
    scraper = SerpAPISearchScraper(query="python developer jobs")
    
    with patch('httpx.AsyncClient.get') as mock_get:
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "organic_results": [
                {
                    "title": "Python Developer - Remote",
                    "link": "https://example.com/job/123",
                    "snippet": "Join our team",
                }
            ]
        }
        mock_get.return_value = mock_response
        
        results = await scraper.run()
        
        assert isinstance(results, list)


@pytest.mark.asyncio
async def test_eventpop_scraper():
    """Test EventPop scraper"""
    from app.scrapers.eventpop import EventPopScraper
    
    scraper = EventPopScraper()
    
    with patch('httpx.AsyncClient.get') as mock_get:
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.text = """
        <div class="event">
            <h3>Tech Conference 2024</h3>
            <div class="date">2024-06-15</div>
            <div class="location">Bangkok</div>
        </div>
        """
        mock_get.return_value = mock_response
        
        results = await scraper.run()
        
        assert isinstance(results, list)


@pytest.mark.asyncio
async def test_scraper_error_handling():
    """Test scraper error handling"""
    from app.scrapers.linkedin import LinkedInScraper
    
    scraper = LinkedInScraper(keywords="test", location="test")
    
    # Mock OpenClaw to raise error
    with patch('app.scrapers.linkedin.openclaw_client') as mock_openclaw:
        mock_openclaw.extract_jobs = AsyncMock(side_effect=Exception("API Error"))
        
        results = await scraper.run()
        
        # Should return empty list on error, not crash
        assert results == []


@pytest.mark.asyncio
async def test_scraper_rate_limiting():
    """Test scraper respects rate limits"""
    from app.scrapers.linkedin import LinkedInScraper
    from app.core.openclaw import OpenClawRateLimitError
    
    scraper = LinkedInScraper(keywords="test", location="test")
    
    with patch('app.scrapers.linkedin.openclaw_client') as mock_openclaw:
        mock_openclaw.extract_jobs = AsyncMock(side_effect=OpenClawRateLimitError("Rate limit"))
        
        results = await scraper.run()
        
        # Should handle rate limit gracefully
        assert results == []


@pytest.mark.asyncio
async def test_scraper_deduplication():
    """Test scraper deduplication logic"""
    from app.scrapers.base import BaseScraper
    
    class TestScraper(BaseScraper):
        source_name = "test"
        
        async def scrape(self):
            return [
                {"title": "Job 1", "url": "https://example.com/1"},
                {"title": "Job 1", "url": "https://example.com/1"},  # Duplicate
                {"title": "Job 2", "url": "https://example.com/2"},
            ]
    
    scraper = TestScraper()
    results = await scraper.run()
    
    # Should deduplicate by URL
    unique_urls = set(r["url"] for r in results)
    assert len(unique_urls) == len(results)
