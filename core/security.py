import secrets
from fastapi import Security, HTTPException, status
from fastapi.security.api_key import APIKeyHeader
from .config import settings
from .exceptions import UnauthorizedError

# Header for API Key authentication
api_key_header = APIKeyHeader(name=settings.API_KEY_NAME, auto_error=False)

async def validate_api_key(api_key: str = Security(api_key_header)):
    """
    Validates the incoming request's API Key against system configuration.
    """
    if not api_key:
        raise UnauthorizedError()
        
    # Constant-time comparison to prevent timing attacks
    if not secrets.compare_digest(api_key, settings.API_KEY):
        raise UnauthorizedError()
        
    return api_key
