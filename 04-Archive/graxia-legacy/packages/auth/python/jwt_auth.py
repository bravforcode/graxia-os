import jwt
import os
from datetime import datetime, timedelta, timezone
from typing import Optional, List, Dict, Any
from pydantic import BaseModel, Field

# Constants for JWT
ALGORITHM = "HS256"

class TokenPayload(BaseModel):
    sub: str  # subject_id
    sub_type: str  # AGENT, SERVICE, OPERATOR, TENANT
    tenant_id: Optional[str] = None
    mission_id: Optional[str] = None
    task_id: Optional[str] = None
    scopes: List[str] = []
    exp: datetime
    iat: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

def create_access_token(
    data: Dict[str, Any], 
    secret_key: str, 
    expires_delta: Optional[timedelta] = None
) -> str:
    to_encode = data.copy()
    if expires_delta:
        expire = datetime.now(timezone.utc) + expires_delta
    else:
        expire = datetime.now(timezone.utc) + timedelta(minutes=60)
    
    to_encode.update({"exp": expire})
    encoded_jwt = jwt.encode(to_encode, secret_key, algorithm=ALGORITHM)
    return encoded_jwt

def decode_access_token(token: str, secret_key: str) -> Dict[str, Any]:
    try:
        payload = jwt.decode(token, secret_key, algorithms=[ALGORITHM])
        return payload
    except jwt.ExpiredSignatureError:
        raise ValueError("Token has expired")
    except jwt.InvalidTokenError:
        raise ValueError("Invalid token")
