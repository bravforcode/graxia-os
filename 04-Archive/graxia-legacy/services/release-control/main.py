from fastapi import FastAPI, HTTPException, Request
from pydantic import BaseModel
from typing import List, Optional, Any, Dict
from enum import Enum
import sys
import os

# Ensure shared packages are importable
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '../../')))
from packages.logging.python.audit import audit_service

# App Initialization
app = FastAPI(title="BravOS Release Control API", version="1.0.0")

# --- Models ---
class FlagType(str, Enum):
    RELEASE = "release"
    OPS = "ops"
    EXPERIMENT = "experiment"
    PERMISSION = "permission"
    SAFETY = "safety"

class FlagState(str, Enum):
    ENABLED = "enabled"
    DISABLED = "disabled"
    CANARY = "canary"

class EvaluationRequest(BaseModel):
    flag_key: str
    tenant_id: Optional[str] = None
    agent_code: Optional[str] = None
    context: Dict[str, Any] = {}

class EvaluationResponse(BaseModel):
    enabled: bool
    variant: Optional[str] = "control"
    reason: str

# --- Mock Data (Simulating DB for P1 Phase) ---
# In actual production, this queries the PostgreSQL 'feature_flags' table
MOCK_FLAGS = {
    "agent_sales_outbound_v2": {
        "type": FlagType.RELEASE,
        "state": FlagState.CANARY,
        "global_override": None,
        "tenant_allowlist": ["tenant_bravos_corp"],
        "default_enabled": False
    },
    "disable_live_trading": {
        "type": FlagType.OPS,
        "state": FlagState.ENABLED, # Meaning the 'disable' flag is active
        "global_override": True,
        "default_enabled": False
    },
    "block_sensitive_prompt_expansion": {
        "type": FlagType.SAFETY,
        "state": FlagState.ENABLED,
        "global_override": True,
        "default_enabled": True
    }
}

# --- Core Logic ---
@app.get("/health")
async def health_check():
    return {"status": "healthy", "service": "release-control"}

@app.post("/v1/flags/evaluate", response_model=EvaluationResponse)
async def evaluate_flag(req: EvaluationRequest):
    flag = MOCK_FLAGS.get(req.flag_key)
    
    if not flag:
        return EvaluationResponse(enabled=False, reason="Flag not found, defaulting to safe-off.")

    # 1. Global Emergency Override (Highest Priority)
    if flag.get("global_override") is not None:
        return EvaluationResponse(
            enabled=flag["global_override"], 
            reason="Global override active."
        )

    # 2. Tenant-Level Override
    if req.tenant_id and req.tenant_id in flag.get("tenant_allowlist", []):
        return EvaluationResponse(
            enabled=True, 
            reason=f"Tenant '{req.tenant_id}' is in allowlist."
        )

    # 3. Default State
    return EvaluationResponse(
        enabled=flag.get("default_enabled", False), 
        reason="No overrides matched, using default state."
    )

# --- Admin API (Placeholder) ---
@app.patch("/v1/flags/{flag_key}/toggle")
async def toggle_flag(flag_key: str, enabled: bool):
    if flag_key in MOCK_FLAGS:
        MOCK_FLAGS[flag_key]["global_override"] = enabled
        
        # Log the flag change
        await audit_service.log_event(
            actor_id="operator_root",
            actor_type="OPERATOR",
            event_type="FLAG_TOGGLED",
            resource_id=flag_key,
            resource_type="FEATURE_FLAG",
            action="TOGGLE",
            status="SUCCESS",
            metadata={"new_state": enabled}
        )
        
        return {"status": "updated", "flag": flag_key, "enabled": enabled}
    raise HTTPException(status_code=404, detail="Flag not found")
