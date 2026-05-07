"""
Tests for Revenue OS Validators
"""
import pytest
from graxia.packages.revenue_os.core.validators import (
    validate_email,
    validate_amount_cents,
    validate_budget_cents,
    validate_string_length,
    validate_slug,
    validate_url,
    validate_positive_integer,
    validate_non_negative_integer,
    sanitize_html,
    validate_platform,
    validate_currency,
    validate_score,
    ValidationError,
)


class TestEmailValidation:
    """Test email validation"""
    
    def test_valid_emails(self):
        """Test valid email formats"""
        valid_emails = [
            "test@example.com",
            "user.name@example.com",
            "user+tag@example.co.uk",
            "test123@test-domain.com",
        ]
        for email in valid_emails:
            validate_email(email)  # Should not raise
    
    def test_invalid_emails(self):
        """Test invalid email formats"""
        invalid_emails = [
            "invalid",
            "@example.com",
            "test@",
            "test @example.com",
            "",
        ]
        for email in invalid_emails:
            with pytest.raises(ValidationError):
                validate_email(email)


class TestAmountValidation:
    """Test amount validation"""
    
    def test_valid_amounts(self):
        """Test valid amounts"""
        validate_amount_cents(100)
        validate_amount_cents(1)
        validate_amount_cents(999999999)
    
    def test_invalid_amounts(self):
        """Test invalid amounts"""
        with pytest.raises(ValidationError):
            validate_amount_cents(0)
        
        with pytest.raises(ValidationError):
            validate_amount_cents(-100)


class TestBudgetValidation:
    """Test budget validation"""
    
    def test_valid_budgets(self):
        """Test valid budgets"""
        validate_budget_cents(0)  # Zero is valid for budget
        validate_budget_cents(100)
        validate_budget_cents(999999999)
    
    def test_invalid_budgets(self):
        """Test invalid budgets"""
        with pytest.raises(ValidationError):
            validate_budget_cents(-100)


class TestStringLengthValidation:
    """Test string length validation"""
    
    def test_valid_strings(self):
        """Test valid string lengths"""
        validate_string_length("test", "field", max_length=10)
        validate_string_length("a" * 100, "field", max_length=100)
    
    def test_invalid_strings(self):
        """Test invalid string lengths"""
        with pytest.raises(ValidationError):
            validate_string_length("", "field", max_length=10)
        
        with pytest.raises(ValidationError):
            validate_string_length("a" * 101, "field", max_length=100)


class TestSlugValidation:
    """Test slug validation"""
    
    def test_valid_slugs(self):
        """Test valid slug formats"""
        valid_slugs = [
            "test-slug",
            "my-campaign-2024",
            "slug123",
            "a",
        ]
        for slug in valid_slugs:
            validate_slug(slug)
    
    def test_invalid_slugs(self):
        """Test invalid slug formats"""
        invalid_slugs = [
            "Test Slug",  # spaces
            "test_slug",  # underscores
            "test@slug",  # special chars
            "",  # empty
        ]
        for slug in invalid_slugs:
            with pytest.raises(ValidationError):
                validate_slug(slug)


class TestURLValidation:
    """Test URL validation"""
    
    def test_valid_urls(self):
        """Test valid URL formats"""
        valid_urls = [
            "https://example.com",
            "http://test.com/path",
            "https://sub.domain.com/path?query=1",
        ]
        for url in valid_urls:
            validate_url(url)
    
    def test_invalid_urls(self):
        """Test invalid URL formats"""
        invalid_urls = [
            "not-a-url",
            "ftp://example.com",  # not http/https
            "",
        ]
        for url in invalid_urls:
            with pytest.raises(ValidationError):
                validate_url(url)


class TestIntegerValidation:
    """Test integer validation"""
    
    def test_positive_integers(self):
        """Test positive integer validation"""
        validate_positive_integer(1, "field")
        validate_positive_integer(999, "field")
        
        with pytest.raises(ValidationError):
            validate_positive_integer(0, "field")
        
        with pytest.raises(ValidationError):
            validate_positive_integer(-1, "field")
    
    def test_non_negative_integers(self):
        """Test non-negative integer validation"""
        validate_non_negative_integer(0, "field")
        validate_non_negative_integer(1, "field")
        validate_non_negative_integer(999, "field")
        
        with pytest.raises(ValidationError):
            validate_non_negative_integer(-1, "field")


class TestHTMLSanitization:
    """Test HTML sanitization"""
    
    def test_safe_html(self):
        """Test that safe HTML is preserved"""
        safe_html = "<p>Hello <strong>world</strong></p>"
        result = sanitize_html(safe_html)
        assert "<p>" in result
        assert "<strong>" in result
    
    def test_dangerous_html(self):
        """Test that dangerous HTML is removed"""
        dangerous_html = '<script>alert("XSS")</script><p>Safe content</p>'
        result = sanitize_html(dangerous_html)
        assert "<script>" not in result
        assert "alert" not in result
        assert "<p>" in result


class TestPlatformValidation:
    """Test platform validation"""
    
    def test_valid_platforms(self):
        """Test valid platform names"""
        valid_platforms = ["stripe", "gumroad", "manual"]
        for platform in valid_platforms:
            validate_platform(platform)
    
    def test_invalid_platforms(self):
        """Test invalid platform names"""
        with pytest.raises(ValidationError):
            validate_platform("invalid")
        
        with pytest.raises(ValidationError):
            validate_platform("")


class TestCurrencyValidation:
    """Test currency validation"""
    
    def test_valid_currencies(self):
        """Test valid currency codes"""
        valid_currencies = ["USD", "THB", "EUR", "GBP"]
        for currency in valid_currencies:
            validate_currency(currency)
    
    def test_invalid_currencies(self):
        """Test invalid currency codes"""
        with pytest.raises(ValidationError):
            validate_currency("INVALID")
        
        with pytest.raises(ValidationError):
            validate_currency("US")


class TestScoreValidation:
    """Test score validation"""
    
    def test_valid_scores(self):
        """Test valid score values"""
        validate_score(0)
        validate_score(50)
        validate_score(100)
    
    def test_invalid_scores(self):
        """Test invalid score values"""
        with pytest.raises(ValidationError):
            validate_score(-1)
        
        with pytest.raises(ValidationError):
            validate_score(101)
