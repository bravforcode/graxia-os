import logging

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Security
from fastapi.security import APIKeyHeader
from pydantic import BaseModel, Field

from app.core.swarm_bootstrap import GRAXIA_ENABLED, AgentMessage, chief, message_bus
from app.middleware.auth import verify_api_key

logger = logging.getLogger(__name__)
router = APIRouter()

API_KEY_HEADER = APIKeyHeader(name="X-API-Key")

async def api_key_security(api_key: str = Security(API_KEY_HEADER)):
    if not await verify_api_key(api_key):
        raise HTTPException(status_code=403, detail="Could not validate credentials")
    return api_key

class SwarmTaskRequest(BaseModel):
    project_description: str = Field(min_length=1, max_length=50000, strict=True)

async def safe_execute_project(description: str):
    """Safely triggers the swarm execution."""
    try:
        await chief.execute_project(description)
    except Exception as e:
        logger.error(f"Graxia Swarm task failed: {e}", exc_info=True)

@router.post("/v1/graxia/execute", dependencies=[Depends(api_key_security)])
async def execute_graxia_task(request: SwarmTaskRequest, background_tasks: BackgroundTasks):
    """Activates the Graxia Swarm for a specific project goal."""
    if not GRAXIA_ENABLED or chief is None:
        raise HTTPException(
            status_code=503,
            detail="Graxia OS is not enabled or not available. Set GRAXIA_ENABLED=true in environment.",
        )

    # Validate request
    if len(request.project_description) > 50000:
        raise HTTPException(
            status_code=400, detail="Project description too long (max 50000 characters)"
        )

    logger.info("graxia_task_requested", description_length=len(request.project_description))

    background_tasks.add_task(safe_execute_project, request.project_description)
    return {
        "status": "success",
        "message": "Graxia Swarm activated. Watch progress via /v1/graxia/stream WebSocket.",
    }

class ApprovalResponse(BaseModel):
    status: str  # "approved" or "rejected"

@router.post("/v1/graxia/approve/{task_id}", dependencies=[Depends(api_key_security)])
async def approve_graxia_task(task_id: str, request: ApprovalResponse):
    """Provides manual approval for a high-risk swarm task."""
    if not GRAXIA_ENABLED or message_bus is None or AgentMessage is None:
        raise HTTPException(status_code=503, detail="Graxia OS is not enabled or not available")

    # Validate task_id format
    if not task_id or len(task_id) > 100:
        raise HTTPException(status_code=400, detail="Invalid task_id")

    # Validate approval status
    if request.status not in ["approved", "rejected"]:
        raise HTTPException(status_code=400, detail="Status must be 'approved' or 'rejected'")

    logger.info("graxia_approval", task_id=task_id, status=request.status)

    msg = AgentMessage(
        sender="UserAPI",
        receiver="System",
        topic=f"approvals/{task_id}",
        content={"status": request.status},
    )
    await message_bus.publish(f"approvals/{task_id}", msg)
    return {"status": "success", "message": f"Approval {request.status} sent for task {task_id}"}
