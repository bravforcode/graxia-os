"""
Unit tests for WorkflowService
"""

from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest
from app.models.workflow import Workflow, WorkflowStatus, ExecutionStatus
from app.services.workflow_service import WorkflowService
from sqlalchemy.ext.asyncio import AsyncSession


@pytest.fixture
def mock_db():
    return AsyncMock(spec=AsyncSession)


@pytest.fixture
def workflow_service(mock_db):
    return WorkflowService(mock_db)


@pytest.mark.asyncio
async def test_create_workflow(workflow_service, mock_db):
    org_id = uuid4()
    workflow_key = "test_wf"
    name = "Test Workflow"

    # Mock db.refresh
    async def mock_refresh(obj):
        obj.id = uuid4()
    mock_db.refresh.side_effect = mock_refresh

    wf = await workflow_service.create_workflow(
        organization_id=org_id,
        workflow_key=workflow_key,
        name=name,
    )

    assert wf.workflow_key == workflow_key
    assert wf.status == WorkflowStatus.DRAFT.value
    mock_db.add.assert_called_once()
    mock_db.commit.assert_called_once()


@pytest.mark.asyncio
async def test_execute_workflow_active(workflow_service, mock_db):
    workflow_id = uuid4()
    mock_wf = Workflow(
        id=workflow_id, 
        workflow_key="test", 
        status=WorkflowStatus.ACTIVE.value, 
        flow_definition={"nodes": []},
        execution_count=0
    )
    
    # Mock get_workflow
    workflow_service.get_workflow = AsyncMock(return_value=mock_wf)
    
    # Mock refresh
    async def mock_refresh(obj):
        obj.id = uuid4()
    mock_db.refresh.side_effect = mock_refresh

    execution = await workflow_service.execute_workflow(workflow_id, input_data={"foo": "bar"})

    assert execution.workflow_id == workflow_id
    assert execution.status == ExecutionStatus.PENDING.value
    assert execution.input_data == {"foo": "bar"}
    assert mock_wf.execution_count == 1
    mock_db.commit.assert_called_once()


@pytest.mark.asyncio
async def test_execute_workflow_not_active(workflow_service, mock_db):
    workflow_id = uuid4()
    mock_wf = Workflow(id=workflow_id, status=WorkflowStatus.DRAFT.value)
    
    workflow_service.get_workflow = AsyncMock(return_value=mock_wf)

    with pytest.raises(ValueError, match="is not active"):
        await workflow_service.execute_workflow(workflow_id)


@pytest.mark.asyncio
async def test_process_event_trigger_matches(workflow_service, mock_db):
    workflow_id = uuid4()
    
    # Use a real WorkflowTrigger object or mock it correctly
    mock_trigger = MagicMock()
    mock_trigger.workflow_id = workflow_id
    mock_trigger.is_active = True
    mock_trigger.event_pattern = {"event_type": "test_event"}
    mock_trigger.input_mapping = {}
    mock_trigger.trigger_count = 0
    
    # Mock db execute to return the trigger
    mock_result = MagicMock()
    mock_result.scalars.return_value.all.return_value = [mock_trigger]
    mock_db.execute.return_value = mock_result
    
    # Mock _trigger_matches and _map_trigger_input
    workflow_service._trigger_matches = AsyncMock(return_value=True)
    workflow_service._map_trigger_input = AsyncMock(return_value={"mapped": "data"})
    
    # Mock execute_workflow
    mock_execution = MagicMock()
    workflow_service.execute_workflow = AsyncMock(return_value=mock_execution)

    executions = await workflow_service.process_event_trigger("test_event", {"some": "data"})

    assert len(executions) == 1
    assert executions[0] == mock_execution
    workflow_service.execute_workflow.assert_called_once()
    assert mock_trigger.trigger_count == 1
