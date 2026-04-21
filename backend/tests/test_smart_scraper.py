"""
Tests for Smart Scraper with Weighted Failure Scoring
TDD approach for resilient scraper implementation
"""
import pytest
from datetime import datetime, timedelta, timezone
from unittest.mock import Mock, AsyncMock, patch, MagicMock

from app.scrapers.smart_base import SmartBaseScraper, ErrorType, ERROR_WEIGHTS


class TestScraper(SmartBaseScraper):
    """Concrete test implementation."""
    source_name = "test_scraper"

    def _get_url(self):
        return "http://test.com"

    async def fetch(self, url):
        return None

    async def parse(self, response):
        return []

    async def normalize(self, raw_item):
        return raw_item


@pytest.fixture
def scraper():
    return TestScraper()


class TestErrorTypeClassification:
    """Test error classification logic."""

    @pytest.mark.asyncio
    async def test_classify_timeout_error(self, scraper):
        error = Exception("Connection timeout after 15s")
        result = await scraper._classify_error(error)
        assert result == ErrorType.NETWORK_TIMEOUT

    @pytest.mark.asyncio
    async def test_classify_rate_limit_error(self, scraper):
        error = Exception("429 Too Many Requests - rate limit exceeded")
        result = await scraper._classify_error(error)
        assert result == ErrorType.RATE_LIMIT

    @pytest.mark.asyncio
    async def test_classify_parsing_error(self, scraper):
        error = Exception("Could not find element with selector .job-card")
        result = await scraper._classify_error(error)
        assert result == ErrorType.PARSING_ERROR

    @pytest.mark.asyncio
    async def test_classify_site_changed_error(self, scraper):
        error = Exception("404 Not Found - page structure changed")
        result = await scraper._classify_error(error)
        assert result == ErrorType.SITE_CHANGED

    @pytest.mark.asyncio
    async def test_classify_auth_error(self, scraper):
        error = Exception("403 Forbidden - authentication required")
        result = await scraper._classify_error(error)
        assert result == ErrorType.AUTHENTICATION

    @pytest.mark.asyncio
    async def test_classify_unknown_error(self, scraper):
        error = Exception("Something went wrong")
        result = await scraper._classify_error(error)
        assert result == ErrorType.UNKNOWN


class TestErrorWeights:
    """Test error weight values."""

    def test_network_timeout_weight(self):
        assert ERROR_WEIGHTS[ErrorType.NETWORK_TIMEOUT] == 0.5

    def test_rate_limit_weight(self):
        assert ERROR_WEIGHTS[ErrorType.RATE_LIMIT] == 0.3

    def test_parsing_error_weight(self):
        assert ERROR_WEIGHTS[ErrorType.PARSING_ERROR] == 0.8

    def test_site_changed_weight(self):
        assert ERROR_WEIGHTS[ErrorType.SITE_CHANGED] == 1.0

    def test_authentication_weight(self):
        assert ERROR_WEIGHTS[ErrorType.AUTHENTICATION] == 1.0

    def test_unknown_weight(self):
        assert ERROR_WEIGHTS[ErrorType.UNKNOWN] == 0.7


class TestWeightedFailureRecording:
    """Test weighted failure scoring in database."""

    @pytest.mark.asyncio
    async def test_failure_recorded_with_weight(self, scraper):

        mock_health = Mock()
        mock_health.consecutive_failures = 0
        mock_health.is_muted = False

        with patch('app.scrapers.smart_base.AsyncSessionLocal') as mock_session:
            mock_db = AsyncMock()
            mock_result = Mock()
            mock_result.scalar_one_or_none.return_value = mock_health
            mock_db.execute.return_value = mock_result
            mock_session.return_value.__aenter__.return_value = mock_db

            error = Exception("429 rate limit")
            await scraper._record_weighted_failure(error)

            assert mock_health.consecutive_failures == int(0.3)

    @pytest.mark.asyncio
    async def test_mute_triggered_at_threshold(self, scraper):

        mock_health = Mock()
        mock_health.consecutive_failures = 2.5
        mock_health.is_muted = False

        with patch('app.scrapers.smart_base.AsyncSessionLocal') as mock_session, \
             patch.object(scraper, '_notify_muted') as mock_notify:

            mock_db = AsyncMock()
            mock_result = Mock()
            mock_result.scalar_one_or_none.return_value = mock_health
            mock_db.execute.return_value = mock_result
            mock_session.return_value.__aenter__.return_value = mock_db

            error = Exception("404 page changed")
            await scraper._record_weighted_failure(error)

            assert mock_health.is_muted is True
            assert mock_health.muted_until is not None


class TestSuccessResetsFailures:
    """Test that success decays failure count."""

    @pytest.mark.asyncio
    async def test_success_decays_weighted_score(self, scraper):

        mock_health = Mock()
        mock_health.consecutive_failures = 5

        with patch('app.scrapers.smart_base.AsyncSessionLocal') as mock_session:
            mock_db = AsyncMock()
            mock_result = Mock()
            mock_result.scalar_one_or_none.return_value = mock_health
            mock_db.execute.return_value = mock_result
            mock_session.return_value.__aenter__.return_value = mock_db

            await scraper._record_weighted_success()

            assert mock_health.consecutive_failures == int(5 * 0.3)


class TestRunWithRetries:
    """Test the run method with exponential backoff."""

    @pytest.mark.asyncio
    async def test_success_on_first_try(self, scraper):
        scraper._is_muted = AsyncMock(return_value=False)
        scraper._record_attempt = AsyncMock()
        scraper.fetch = AsyncMock(return_value=Mock())
        scraper.parse = AsyncMock(return_value=[{"title": "Test"}])
        scraper.normalize = AsyncMock(return_value={"title": "Test"})
        scraper._dedup = Mock(return_value=[{"title": "Test"}])
        scraper._record_weighted_success = AsyncMock()
        scraper._record_result = AsyncMock()

        results = await scraper.run()

        assert len(results) == 1
        scraper._record_weighted_success.assert_called_once()

    @pytest.mark.asyncio
    async def test_all_retries_exhausted_records_failure(self, scraper):
        scraper._is_muted = AsyncMock(return_value=False)
        scraper._record_attempt = AsyncMock()
        scraper.fetch = AsyncMock(side_effect=Exception("always fails"))
        scraper._record_weighted_failure = AsyncMock()
        scraper._record_result = AsyncMock()

        with patch('asyncio.sleep', AsyncMock()):
            results = await scraper.run()

        assert scraper.fetch.call_count == 3
        assert len(results) == 0
        scraper._record_weighted_failure.assert_called_once()


class TestSmartScraperThresholds:
    """Test threshold configurations."""

    def test_weighted_failure_threshold(self, scraper):
        assert scraper.WEIGHTED_FAILURE_THRESHOLD == 3.0

    def test_mute_duration_hours(self, scraper):
        assert scraper.MUTE_DURATION_HOURS == 6

    def test_early_warning_threshold(self, scraper):
        assert scraper.EARLY_WARNING_THRESHOLD == 2.0
