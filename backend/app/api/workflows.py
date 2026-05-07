"""
Workflow & Automation API — Features 56-70
Endpoints for workflows, triggers, pipelines, and orchestration
"""

import logging
from typing import Any
from uuid import UUID

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query, Request
from pydantic import BaseModel, Field, ConfigDict
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.middleware.tenant import get_org
from app.models.organization import Organization
from app.services.workflow_service import WorkflowService

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/workflows", tags=["Workflow & Automation"])


# ═══════════════════════════════════════════════════════════════════════════════
# SCHEMAS
# ═══════════════════════════════════════════════════════════════════════════════


class WorkflowCreate(BaseModel):
    workflow_key: str
    name: str
    description: str | None = None
    workflow_type: str = "automation"
    flow_definition: dict[str, Any] = Field(default_factory=lambda: {"nodes": [], "edges": []})
    input_schema: dict[str, Any] = Field(default_factory=dict)
    output_schema: dict[str, Any] = Field(default_factory=dict)
    auto_assign_agents: bool = True
    required_skills: list[UUID] = Field(default_factory=list)


class WorkflowUpdate(BaseModel):
    name: str | None = None
    description: str | None = None
    status: str | None = None
    flow_definition: dict[str, Any] | None = None
    input_schema: dict[str, Any] | None = None
    output_schema: dict[str, Any] | None = None


class WorkflowOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    workflow_key: str
    name: str
    description: str | None
    workflow_type: str
    status: str
    version: int
    created_at: Any


class ExecutionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    execution_key: str
    workflow_id: UUID
    status: str
    started_at: Any | None
    completed_at: Any | None


# ═══════════════════════════════════════════════════════════════════════════════
# DEPENDENCIES
# ═══════════════════════════════════════════════════════════════════════════════


async def get_workflow_service(db: AsyncSession = Depends(get_db)) -> WorkflowService:
    return WorkflowService(db)


# ═══════════════════════════════════════════════════════════════════════════════
# WORKFLOW ENDPOINTS
# ═══════════════════════════════════════════════════════════════════════════════


@router.post("", response_model=WorkflowOut)
async def create_workflow(
    data: WorkflowCreate,
    org: Organization = Depends(get_org),
    service: WorkflowService = Depends(get_workflow_service),
):
    """Create a new workflow definition."""
    try:
        workflow = await service.create_workflow(
            organization_id=org.id,
            workflow_key=data.workflow_key,
            name=data.name,
            description=data.description,
            workflow_type=data.workflow_type,
            flow_definition=data.flow_definition,
            input_schema=data.input_schema,
            output_schema=data.output_schema,
            auto_assign_agents=data.auto_assign_agents,
            required_skills=data.required_skills,
        )
        logger.info(f"Tenant {org.id} created workflow {workflow.id}")
        return workflow
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("", response_model=dict)
async def list_workflows(
    workflow_type: str | None = None,
    status: str | None = None,
    limit: int = Query(50, ge=1, le=100),
    offset: int = Query(0, ge=0),
    org: Organization = Depends(get_org),
    service: WorkflowService = Depends(get_workflow_service),
):
    """List all workflows for the organization."""
    workflows, total = await service.list_workflows(
        organization_id=org.id,
        workflow_type=workflow_type,
        status=status,
        limit=limit,
        offset=offset,
    )
    return {
        "items": workflows,
        "total": total,
    }


@router.get("/{workflow_id}", response_model=WorkflowOut)
async def get_workflow(
    workflow_id: UUID,
    org: Organization = Depends(get_org),
    service: WorkflowService = Depends(get_workflow_service),
):
    """Get workflow details."""
    workflow = await service.get_workflow(workflow_id, org.id)
    if not workflow:
        raise HTTPException(status_code=404, detail="Workflow not found")
    return workflow


@router.post("/{workflow_id}/execute", response_model=ExecutionOut)
async def execute_workflow(
    workflow_id: UUID,
    input_data: dict[str, Any] = Field(default_factory=dict),
    background_tasks: BackgroundTasks = None,
    org: Organization = Depends(get_org),
    service: WorkflowService = Depends(get_workflow_service),
):
    """Execute a workflow instance."""
    # Verify workflow belongs to org
    workflow = await service.get_workflow(workflow_id, org.id)
    if not workflow:
        raise HTTPException(status_code=404, detail="Workflow not found")

    execution = await service.create_execution(
        workflow_id=workflow_id,
        organization_id=org.id,
        input_data=input_data,
        trigger_type="api",
    )
    
    # In a real implementation, we would queue the task
    # await service.run_execution(execution.id)
    
    logger.info(f"Tenant {org.id} started execution {execution.id} of workflow {workflow_id}")
    return execution
