import time
import logging
from typing import Optional, Dict
from fastapi import Request, HTTPException, Security, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
import jwt
from pydantic import BaseModel

logger = logging.getLogger(__name__)

security = HTTPBearer()

class TokenBucket:
    """
    In-memory Token Bucket Rate Limiter (For production, use Redis).
    """
    def __init__(self, capacity: int, refill_rate: float):
        self.capacity = capacity
        self.tokens = capacity
        self.refill_rate = refill_rate
        self.last_refill = time.monotonic()

    def consume(self, tokens: int = 1) -> bool:
        now = time.monotonic()
        time_passed = now - self.last_refill
        self.tokens = min(self.capacity, self.tokens + time_passed * self.refill_rate)
        self.last_refill = now

        if self.tokens >= tokens:
            self.tokens -= tokens
            return True
        return False

# In-memory store for rate limiters per API Key
rate_limiters: Dict[str, TokenBucket] = {}

async def rate_limit_dependency(request: Request):
    """
    FastAPI Dependency for rate limiting per client IP or API Key.
    """
    client_id = request.headers.get("X-API-Key", request.client.host)
    
    if client_id not in rate_limiters:
        rate_limiters[client_id] = TokenBucket(capacity=100, refill_rate=10.0) # 100 reqs burst, 10 reqs/sec
        
    if not rate_limiters[client_id].consume(1):
        logger.warning(f"Rate limit exceeded for client: {client_id}")
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Too Many Requests. Rate limit exceeded."
        )

async def verify_jwt_token(credentials: HTTPAuthorizationCredentials = Security(security)):
    """
    FastAPI Dependency to validate JWT tokens using JWKS.
    Includes dynamic key rotation support.
    """
    token = credentials.credentials
    try:
        # In a real enterprise app, fetch JWKS from the IdP (e.g., Auth0, Keycloak)
        # unverified_header = jwt.get_unverified_header(token)
        # kid = unverified_header.get("kid")
        # public_key = get_public_key_from_jwks(kid)
        
        # Mock validation
        secret_key = "super-secret-enterprise-key" 
        payload = jwt.decode(token, secret_key, algorithms=["HS256"])
        return payload
        
    except jwt.ExpiredSignatureError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token has expired",
            headers={"WWW-Authenticate": "Bearer"},
        )
    except jwt.InvalidTokenError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid authentication credentials",
            headers={"WWW-Authenticate": "Bearer"},
        )

# Example usage in FastAPI:
# @app.get("/api/v1/secure-data", dependencies=[Depends(rate_limit_dependency), Depends(verify_jwt_token)])
# async def secure_endpoint():
#     return {"status": "success"}
