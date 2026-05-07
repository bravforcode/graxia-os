from typing import Any, Dict, Optional

class BravOSException(Exception):
    """Base exception for all Brav OS specific errors."""
    def __init__(self, message: str, status_code: int = 500, detail: Optional[Any] = None):
        self.message = message
        self.status_code = status_code
        self.detail = detail
        super().__init__(self.message)

class RetrievalError(BravOSException):
    """Exception raised when retrieval from vector storage fails."""
    def __init__(self, message: str = "Retrieval layer failure.", detail: Optional[Any] = None):
        super().__init__(message, status_code=502, detail=detail)

class LLMProviderError(BravOSException):
    """Exception raised when an LLM provider call fails."""
    def __init__(self, message: str = "LLM provider integration failure.", detail: Optional[Any] = None):
        super().__init__(message, status_code=502, detail=detail)

class BudgetExceededError(BravOSException):
    """Exception raised when token usage exceeds the defined budget."""
    def __init__(self, message: str = "Token budget exceeded for this request.", detail: Optional[Any] = None):
        super().__init__(message, status_code=429, detail=detail)

class ConfigurationError(BravOSException):
    """Exception raised for invalid system configuration."""
    def __init__(self, message: str = "Invalid system configuration.", detail: Optional[Any] = None):
        super().__init__(message, status_code=500, detail=detail)

class UnauthorizedError(BravOSException):
    """Exception raised for failed API key validation."""
    def __init__(self, message: str = "Unauthorized: Invalid or missing API Key."):
        super().__init__(message, status_code=401)
