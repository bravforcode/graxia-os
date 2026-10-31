"""LinkedIn job URLs carry per-run tracking params; one job must hash to one source_hash."""

import pytest
from app.scrapers.linkedin import LinkedInScraper

JOB_URL = "https://in.linkedin.com/jobs/view/senior-software-engineer-python-at-ottimate-4474141586"
TITLE = "Senior Software Engineer - Python"


@pytest.mark.asyncio
async def test_same_job_with_different_tracking_params_gets_same_source_hash():
    scraper = LinkedInScraper()

    first = await scraper.normalize({"title": TITLE, "url": JOB_URL + "?position=4&pageNum=0&refId=aaa"})
    second = await scraper.normalize({"title": TITLE, "url": JOB_URL + "?position=6&pageNum=0&refId=bbb"})

    assert first["source_hash"] == second["source_hash"]


@pytest.mark.asyncio
async def test_stored_source_url_drops_tracking_query():
    scraper = LinkedInScraper()

    item = await scraper.normalize({"title": TITLE, "url": JOB_URL + "?position=4&refId=aaa"})

    assert item["source_url"] == JOB_URL
