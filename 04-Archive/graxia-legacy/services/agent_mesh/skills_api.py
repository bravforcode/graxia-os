from fastapi import FastAPI, HTTPException, Depends
from pydantic import BaseModel, HttpUrl
from typing import List, Optional, Dict, Any
import uuid

app = FastAPI(title="BravOS Skill Registry API", version="1.0.0")

# --- Models ---
class SkillMetadata(BaseModel):
    author: str
    version: str
    license: str
    requires_network: bool = False
    max_memory_mb: int = 128

class SkillManifest(BaseModel):
    id: Optional[str] = None
    name: str
    description: str
    repository_url: HttpUrl
    entrypoint: str
    metadata: SkillMetadata
    status: str = "pending_review" # pending_review, active, deprecated, revoked

class SkillApprovalRequest(BaseModel):
    skill_id: str
    approved: bool
    reason: Optional[str] = None

# --- Mock DB ---
SKILLS_DB: Dict[str, SkillManifest] = {}

# --- Endpoints ---
@app.post("/v1/skills/register", response_model=SkillManifest)
async def register_skill(manifest: SkillManifest):
    """
    Submit a new skill for review and inclusion in the registry.
    """
    skill_id = str(uuid.uuid4())
    manifest.id = skill_id
    manifest.status = "pending_review"
    
    # In production, we'd trigger a background scan of the repository
    # to check for malicious patterns before allowing approval.
    SKILLS_DB[skill_id] = manifest
    
    return manifest

@app.get("/v1/skills", response_model=List[SkillManifest])
async def list_skills(status: Optional[str] = "active"):
    """
    List all skills available in the registry, filtered by status.
    """
    return [skill for skill in SKILLS_DB.values() if skill.status == status]

@app.get("/v1/skills/{skill_id}", response_model=SkillManifest)
async def get_skill(skill_id: str):
    """
    Get detailed information about a specific skill.
    """
    if skill_id not in SKILLS_DB:
        raise HTTPException(status_code=404, detail="Skill not found")
    return SKILLS_DB[skill_id]

@app.post("/v1/skills/review")
async def review_skill(req: SkillApprovalRequest):
    """
    (Admin/CEO Only) Approve or reject a pending skill.
    """
    if req.skill_id not in SKILLS_DB:
        raise HTTPException(status_code=404, detail="Skill not found")
    
    skill = SKILLS_DB[req.skill_id]
    if req.approved:
        skill.status = "active"
    else:
        skill.status = "revoked"
        
    return {"status": "success", "skill_id": req.skill_id, "new_status": skill.status}

@app.get("/health")
async def health_check():
    return {"status": "healthy", "service": "skill-registry"}
