"""
Revenue OS Validators
Input validation utilities for data integrity and security
"""
import re
from typing import Optional
from decimal import Decimal
import structlog

logger = structlog.get_logger()


# Email validation regex (RFC 5322 simplified)
EMAIL_REGEX = re.compile(
    r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
)


class ValidationError(Exception):
    """Custom validation error"""
    pass


def validate_email(email: str) -> bool:
    """
    Validate email format.
    
    Args:
        email: Email address to validate
    
    Returns:
        bool: True if valid
    
    Raises:
        ValidationError: If email is invalid
    """
    if not email:
        raise ValidationError("Email is required")
    
    if len(email) > 320:  # RFC 5321
        raise ValidationError("Email is too long (max 320 characters)")
    
    if not EMAIL_REGEX.match(email):
        raise ValidationError(f"Invalid email format: {email}")
    
    return True


def validate_amount_cents(amount_cents: int, allow_zero: bool = False) -> bool:
    """
    Validate amount in cents.
    
    Args:
        amount_cents: Amount in cents
        allow_zero: Whether to allow zero amount
    
    Returns:
        bool: True if valid
    
    Raises:
        ValidationError: If amount is invalid
    """
    if not isinstance(amount_cents, int):
        raise ValidationError(f"Amount must be an integer, got {type(amount_cents)}")
    
    if allow_zero:
        if amount_cents < 0:
            raise ValidationError(f"Amount must be non-negative, got {amount_cents}")
    else:
        if amount_cents <= 0:
            raise ValidationError(f"Amount must be positive, got {amount_cents}")
    
    # Check for reasonable maximum (1 billion THB = 100 billion cents)
    if amount_cents > 100_000_000_000:
        raise ValidationError(f"Amount is too large: {amount_cents}")
    
    return True


def validate_budget_cents(budget_cents: int) -> bool:
    """
    Validate budget in cents.
    
    Args:
        budget_cents: Budget in cents
    
    Returns:
        bool: True if valid
    
    Raises:
        ValidationError: If budget is invalid
    """
    if not isinstance(budget_cents, int):
        raise ValidationError(f"Budget must be an integer, got {type(budget_cents)}")
    
    if budget_cents < 0:
        raise ValidationError(f"Budget must be non-negative, got {budget_cents}")
    
    # Check for reasonable maximum
    if budget_cents > 1_000_000_000_000:  # 10 billion THB
        raise ValidationError(f"Budget is too large: {budget_cents}")
    
    return True


def validate_string_length(
    value: str,
    field_name: str,
    min_length: int = 0,
    max_length: Optional[int] = None
) -> bool:
    """
    Validate string length.
    
    Args:
        value: String to validate
        field_name: Field name for error messages
        min_length: Minimum length
        max_length: Maximum length
    
    Returns:
        bool: True if valid
    
    Raises:
        ValidationError: If string length is invalid
    """
    if not isinstance(value, str):
        raise ValidationError(f"{field_name} must be a string, got {type(value)}")
    
    length = len(value)
    
    if length < min_length:
        raise ValidationError(
            f"{field_name} is too short (min {min_length} characters, got {length})"
        )
    
    if max_length and length > max_length:
        raise ValidationError(
            f"{field_name} is too long (max {max_length} characters, got {length})"
        )
    
    return True


def validate_slug(slug: str) -> bool:
    """
    Validate slug format (lowercase, alphanumeric, hyphens only).
    
    Args:
        slug: Slug to validate
    
    Returns:
        bool: True if valid
    
    Raises:
        ValidationError: If slug is invalid
    """
    if not slug:
        raise ValidationError("Slug is required")
    
    if not re.match(r'^[a-z0-9-]+$', slug):
        raise ValidationError(
            f"Slug must contain only lowercase letters, numbers, and hyphens: {slug}"
        )
    
    if slug.startswith('-') or slug.endswith('-'):
        raise ValidationError(f"Slug cannot start or end with hyphen: {slug}")
    
    if '--' in slug:
        raise ValidationError(f"Slug cannot contain consecutive hyphens: {slug}")
    
    validate_string_length(slug, "Slug", min_length=1, max_length=255)
    
    return True


def validate_url(url: str, field_name: str = "URL") -> bool:
    """
    Validate URL format.
    
    Args:
        url: URL to validate
        field_name: Field name for error messages
    
    Returns:
        bool: True if valid
    
    Raises:
        ValidationError: If URL is invalid
    """
    if not url:
        raise ValidationError(f"{field_name} is required")
    
    # Simple URL validation
    if not url.startswith(('http://', 'https://')):
        raise ValidationError(f"{field_name} must start with http:// or https://")
    
    if len(url) > 2000:
        raise ValidationError(f"{field_name} is too long (max 2000 characters)")
    
    return True


def validate_positive_integer(value: int, field_name: str) -> bool:
    """
    Validate positive integer.
    
    Args:
        value: Value to validate
        field_name: Field name for error messages
    
    Returns:
        bool: True if valid
    
    Raises:
        ValidationError: If value is invalid
    """
    if not isinstance(value, int):
        raise ValidationError(f"{field_name} must be an integer, got {type(value)}")
    
    if value <= 0:
        raise ValidationError(f"{field_name} must be positive, got {value}")
    
    return True


def validate_non_negative_integer(value: int, field_name: str) -> bool:
    """
    Validate non-negative integer.
    
    Args:
        value: Value to validate
        field_name: Field name for error messages
    
    Returns:
        bool: True if valid
    
    Raises:
        ValidationError: If value is invalid
    """
    if not isinstance(value, int):
        raise ValidationError(f"{field_name} must be an integer, got {type(value)}")
    
    if value < 0:
        raise ValidationError(f"{field_name} must be non-negative, got {value}")
    
    return True


def sanitize_html(html: str) -> str:
    """
    Sanitize HTML to prevent XSS attacks.
    
    Args:
        html: HTML string to sanitize
    
    Returns:
        str: Sanitized HTML
    
    Note:
        This is a basic implementation. For production, use a library like bleach.
    """
    if not html:
        return ""
    
    # Remove script tags
    html = re.sub(r'<script[^>]*>.*?</script>', '', html, flags=re.DOTALL | re.IGNORECASE)
    
    # Remove event handlers
    html = re.sub(r'\s*on\w+\s*=\s*["\'][^"\']*["\']', '', html, flags=re.IGNORECASE)
    html = re.sub(r'\s*on\w+\s*=\s*\S+', '', html, flags=re.IGNORECASE)
    
    # Remove javascript: URLs
    html = re.sub(r'javascript:', '', html, flags=re.IGNORECASE)
    
    return html


def validate_platform(platform: str) -> bool:
    """
    Validate platform name.
    
    Args:
        platform: Platform name
    
    Returns:
        bool: True if valid
    
    Raises:
        ValidationError: If platform is invalid
    """
    valid_platforms = {'stripe', 'gumroad', 'manual', 'paypal', 'bank_transfer'}
    
    if platform not in valid_platforms:
        raise ValidationError(
            f"Invalid platform: {platform}. Must be one of {valid_platforms}"
        )
    
    return True


def validate_currency(currency: str) -> bool:
    """
    Validate currency code (ISO 4217).
    
    Args:
        currency: Currency code
    
    Returns:
        bool: True if valid
    
    Raises:
        ValidationError: If currency is invalid
    """
    # Common currencies
    valid_currencies = {'THB', 'USD', 'EUR', 'GBP', 'JPY', 'CNY', 'SGD'}
    
    if currency not in valid_currencies:
        raise ValidationError(
            f"Invalid currency: {currency}. Must be one of {valid_currencies}"
        )
    
    return True


def validate_score(score: float) -> bool:
    """
    Validate score (0-100).
    
    Args:
        score: Score value
    
    Returns:
        bool: True if valid
    
    Raises:
        ValidationError: If score is invalid
    """
    if not isinstance(score, (int, float)):
        raise ValidationError(f"Score must be a number, got {type(score)}")
    
    if score < 0 or score > 100:
        raise ValidationError(f"Score must be between 0 and 100, got {score}")
    
    return True


# Export all validators
__all__ = [
    'ValidationError',
    'validate_email',
    'validate_amount_cents',
    'validate_budget_cents',
    'validate_string_length',
    'validate_slug',
    'validate_url',
    'validate_positive_integer',
    'validate_non_negative_integer',
    'sanitize_html',
    'validate_platform',
    'validate_currency',
    'validate_score',
]
