from fastapi import FastAPI, HTTPException, Depends, Header
from pydantic import BaseModel, Field
from pydantic_settings import BaseSettings
from typing import Optional, List
from datetime import timedelta
import sys
import os

# Ensure shared packages are importable
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '../../')))
from packages.auth.python.jwt_auth import create_access_token, ALGORITHM

class Settings(BaseSettings):
    JWT_SECRET: str = "bravos_fallback_secret_key_change_me_in_prod"
    TOKEN_EXPIRY_MINUTES: int = 60
    
    class Config:
        env_file = ".env"

settings = Settings()
app = FastAPI(title="BravOS Identity Broker", version="1.0.0")

class TokenRequest(BaseModel):
    subject_id: str
    subject_type: str  # AGENT, SERVICE, OPERATOR, TENANT
    tenant_id: Optional[str] = None
    mission_id: Optional[str] = None
    task_id: Optional[str] = None
    scopes: List[str] = []

class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_in_seconds: int

from packages.auth.python.jwt_auth import create_access_token, ALGORITHM
from packages.logging.python.audit import audit_service

class Settings(BaseSettings):
...
@app.post("/v1/auth/token", response_model=TokenResponse)
async def issue_token(req: TokenRequest):
    # In a real enterprise setup, we would validate the requester identity here
    # (e.g., via API Key or internal mTLS verification)

    # For now, we follow the Plan and issue tokens based on validated request structure
    payload = {
        "sub": req.subject_id,
        "sub_type": req.subject_type,
        "tenant_id": req.tenant_id,
        "mission_id": req.mission_id,
        "task_id": req.task_id,
        "scopes": req.scopes
    }

    access_token = create_access_token(
        data=payload, 
        secret_key=settings.JWT_SECRET, 
        expires_delta=timedelta(minutes=settings.TOKEN_EXPIRY_MINUTES)
    )

    # Log the event
    await audit_service.log_event(
        actor_id=req.subject_id,
        actor_type=req.subject_type,
        event_type="TOKEN_ISSUED",
        resource_id=req.subject_id,
        resource_type="IDENTITY",
        action="ISSUE",
        status="SUCCESS",
        tenant_id=req.tenant_id,
        metadata={"scopes": req.scopes, "mission_id": req.mission_id}
    )

    return TokenResponse(
        access_token=access_token,
        expires_in_seconds=settings.TOKEN_EXPIRY_MINUTES * 60
    )

