"""
Enterprise Exception Hierarchy

Clean, typed exceptions for better error handling and debugging.
"""
from typing import Any


class PersonalOSException(Exception):
    """Base exception for all Personal OS errors."""
    
    def __init__(
        self,
        message: str,
        code: str,
        details: dict[str, Any] | None = None,
        cause: Exception | None = None
    ):
        self.message = message
        self.code = code
        self.details = details or {}
        self.cause = cause
        super().__init__(message)
    
    def to_dict(self) -> dict[str, Any]:
        """Convert exception to dictionary for API responses."""
        return {
            "error": {
                "message": self.message,
                "code": self.code,
                "details": self.details,
                "type": self.__class__.__name__
            }
        }


# Database Exceptions
class DatabaseException(PersonalOSException):
    """Database operation failed."""
    pass


class RecordNotFoundException(DatabaseException):
    """Requested record not found."""
    
    def __init__(self, resource: str, identifier: str):
        super().__init__(
            message=f"{resource} not found: {identifier}",
            code="RECORD_NOT_FOUND",
            details={"resource": resource, "identifier": identifier}
        )


class DuplicateRecordException(DatabaseException):
    """Record already exists."""
    
    def __init__(self, resource: str, field: str, value: str):
        super().__init__(
            message=f"{resource} already exists with {field}={value}",
            code="DUPLICATE_RECORD",
            details={"resource": resource, "field": field, "value": value}
        )


# API Exceptions
class APIException(PersonalOSException):
    """External API call failed."""
    pass


class RateLimitException(APIException):
    """API rate limit exceeded."""
    
    def __init__(self, service: str, retry_after: int | None = None):
        super().__init__(
            message=f"Rate limit exceeded for {service}",
            code="RATE_LIMIT_EXCEEDED",
            details={"service": service, "retry_after": retry_after}
        )


class BudgetExceededException(APIException):
    """Budget limit exceeded."""
    
    def __init__(self, current: float, limit: float, period: str):
        super().__init__(
            message=f"Budget exceeded: ${current:.2f} / ${limit:.2f} ({period})",
            code="BUDGET_EXCEEDED",
            details={"current": current, "limit": limit, "period": period}
        )


# Authentication Exceptions
class AuthenticationException(PersonalOSException):
    """Authentication failed."""
    
    def __init__(self, reason: str = "Invalid credentials"):
        super().__init__(
            message=reason,
            code="AUTHENTICATION_FAILED"
        )


class AuthorizationException(PersonalOSException):
    """Authorization failed."""
    
    def __init__(self, resource: str, action: str):
        super().__init__(
            message=f"Not authorized to {action} {resource}",
            code="AUTHORIZATION_FAILED",
            details={"resource": resource, "action": action}
        )


# Validation Exceptions
class ValidationException(PersonalOSException):
    """Input validation failed."""
    
    def __init__(self, field: str, reason: str):
        super().__init__(
            message=f"Validation failed for {field}: {reason}",
            code="VALIDATION_FAILED",
            details={"field": field, "reason": reason}
        )


# Integration Exceptions
class IntegrationException(PersonalOSException):
    """External integration failed."""
    pass


class ObsidianException(IntegrationException):
    """Obsidian integration failed."""
    
    def __init__(self, operation: str, reason: str):
        super().__init__(
            message=f"Obsidian {operation} failed: {reason}",
            code="OBSIDIAN_ERROR",
            details={"operation": operation, "reason": reason}
        )


class TelegramException(IntegrationException):
    """Telegram integration failed."""
    
    def __init__(self, operation: str, reason: str):
        super().__init__(
            message=f"Telegram {operation} failed: {reason}",
            code="TELEGRAM_ERROR",
            details={"operation": operation, "reason": reason}
        )


# Business Logic Exceptions
class BusinessLogicException(PersonalOSException):
    """Business logic validation failed."""
    pass


class ApprovalRequiredException(BusinessLogicException):
    """Action requires approval."""
    
    def __init__(self, action: str, approval_id: str):
        super().__init__(
            message=f"Action '{action}' requires approval",
            code="APPROVAL_REQUIRED",
            details={"action": action, "approval_id": approval_id}
        )


class ScraperMutedException(BusinessLogicException):
    """Scraper is muted due to failures."""
    
    def __init__(self, scraper: str, until: str):
        super().__init__(
            message=f"Scraper '{scraper}' is muted until {until}",
            code="SCRAPER_MUTED",
            details={"scraper": scraper, "muted_until": until}
        )
