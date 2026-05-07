from fastapi import FastAPI, HTTPException, Depends, Header, Request
from pydantic import BaseModel
from typing import List, Optional, Dict, Any
import sys
import os

# Ensure shared packages are importable
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '../../')))
from packages.auth.python.jwt_auth import decode_access_token, Settings as AuthSettings

# Initialize settings and app
auth_settings = AuthSettings()
app = FastAPI(title="BravOS Capability Grant Service", version="1.0.0")

# --- Models ---
class CapabilityCheckRequest(BaseModel):
    subject_id: str
    tool_id: str
    tenant_id: str
    mission_id: Optional[str] = None
    task_id: Optional[str] = None

class CapabilityResponse(BaseModel):
    allowed: bool
    reason: Optional[str] = None
    scope_granted: List[str] = []

# --- HR-10 Enforcement Middleware ---
@app.middleware("http")
async def enforce_hr10_security(request: Request, call_next):
    # Exempt health check
    if request.url.path == "/health":
        return await call_next(request)
        
    auth_header = request.headers.get("Authorization")
    if not auth_header or not auth_header.startswith("Bearer "):
        # Hard Rule 10: Reject unauthenticated internal requests
        return JSONResponse(
            status_code=401,
            content={"detail": "HR-10 Violation: Internal service requests must be authenticated via Identity Broker."}
        )
    
    try:
        # Validate token
        token = auth_header.split(" ")[1]
        payload = decode_access_token(token, auth_settings.JWT_SECRET)
        request.state.user = payload
    except Exception as e:
        return JSONResponse(status_code=401, content={"detail": f"HR-10 Violation: {str(e)}"})
        
    return await call_next(request)

from fastapi.responses import JSONResponse

# --- Core Logic ---
@app.get("/health")
async def health_check():
    return {"status": "healthy", "service": "capability-grant"}

@app.post("/v1/capabilities/check", response_model=CapabilityResponse)
async def check_capability(req: CapabilityCheckRequest, request: Request):
    # 1. Verify caller has the right to check capabilities (usually SERVICE or COS)
    caller = request.state.user
    if caller.get("sub_type") not in ["SERVICE", "AGENT", "OPERATOR"]:
        raise HTTPException(status_code=403, detail="Caller not authorized to check capabilities")

    # 2. Logic to resolve grants (In v3, this queries the 'capability_grants' table)
    # Placeholder Logic based on Master Plan Section 3.1 (Risk Classes)
    
    # Example: Class 5 tools (dangerous) always require CEO one-time auth
    DANGEROUS_TOOLS = ["rm_rf", "bulk_delete", "transfer_funds_unlimited"]
    if req.tool_id in DANGEROUS_TOOLS:
        return CapabilityResponse(
            allowed=False, 
            reason="CLASS_5: Forbidden without explicit one-time CEO authorization."
        )

    # Example: Class 0-1 tools (internal) auto-allow if token has basic scopes
    if "AGENT" in caller.get("sub_type", ""):
        # Check if the agent is asking for a tool it was assigned in its token scopes
        token_scopes = caller.get("scopes", [])
        if req.tool_id in token_scopes or "*" in token_scopes:
            return CapabilityResponse(allowed=True, scope_granted=[req.tool_id])
            
    return CapabilityResponse(allowed=False, reason="Scope not found in active task grant.")
