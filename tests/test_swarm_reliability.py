import pytest
import asyncio
import os
import json
import shutil
from pathlib import Path
from unittest.mock import AsyncMock, patch, MagicMock

from core.execution.real_swarm import AutonomousAgent, DeadLetterQueue, RealSwarmOrchestrator, AGENT_RUNS_DIR, DLQ_FILE
from core.execution.message_bus import AgentMessageBus, AgentMessage
from core.providers.llm_client import LLMResponse

@pytest.fixture
def clean_state():
    if os.path.exists(".state"):
        shutil.rmtree(".state")
    yield
    if os.path.exists(".state"):
        shutil.rmtree(".state")

@pytest.fixture
def mock_bus():
    bus = MagicMock(spec=AgentMessageBus)
    bus.publish = AsyncMock()
    return bus

@pytest.mark.asyncio
async def test_agent_checkpointing(clean_state, mock_bus):
    agent = AutonomousAgent("TestAgent", "You are a test agent.", mock_bus)
    task_id = "test_task_123"
    
    # Save state
    agent.message_history.append({"role": "assistant", "content": "Thinking..."})
    await agent._save_state(task_id, 2)
    
    # Check if file exists
    state_file = AGENT_RUNS_DIR / f"{task_id}.json"
    assert state_file.exists()
    
    # Load state in a new agent instance
    new_agent = AutonomousAgent("TestAgent", "You are a test agent.", mock_bus)
    loaded_iter = await new_agent._load_state(task_id)
    
    assert loaded_iter == 2
    assert len(new_agent.message_history) == 2
    assert new_agent.message_history[1]["content"] == "Thinking..."

@pytest.mark.asyncio
async def test_dead_letter_queue(clean_state):
    await DeadLetterQueue.add("fail_task", "TestAgent", "Do something", "Critical Error")
    
    assert DLQ_FILE.exists()
    with open(DLQ_FILE, "r") as f:
        data = json.load(f)
        assert len(data) == 1
        assert data[0]["task_id"] == "fail_task"
        assert data[0]["error"] == "Critical Error"

@pytest.mark.asyncio
async def test_dead_letter_queue_concurrency(clean_state):
    tasks = [
        DeadLetterQueue.add(f"fail_task_{i}", "TestAgent", f"Task {i}", f"Error {i}")
        for i in range(100)
    ]
    await asyncio.gather(*tasks)
    
    assert DLQ_FILE.exists()
    with open(DLQ_FILE, "r") as f:
        data = json.load(f)
        assert len(data) == 100
        task_ids = {d["task_id"] for d in data}
        assert len(task_ids) == 100
        for i in range(100):
            assert f"fail_task_{i}" in task_ids

@pytest.mark.asyncio
async def test_structured_workflow_logic(clean_state, mock_bus):
    orchestrator = RealSwarmOrchestrator(bus=mock_bus)
    task_id = "wf_task"
    description = "Create a simple script"
    
    # Mock LLM Client responses for the workflow
    # 1. Draft
    # 2. Review
    # 3. Validation (pass)
    
    mock_responses = [
        LLMResponse(content="Draft content", raw_response={}), # Draft
        LLMResponse(content="Looks okay", raw_response={}),    # Review
    ]
    
    with patch("core.execution.real_swarm.llm_client.chat", new_callable=AsyncMock) as mock_chat, \
         patch("core.execution.real_swarm.llm_client.generate_completion", new_callable=AsyncMock) as mock_gen, \
         patch("core.telemetry.TaskCostTracker.log_cost", new_callable=AsyncMock) as mock_log:
        
        mock_chat.side_effect = mock_responses
        # Mock validation result (Chief)
        mock_gen.return_value = json.dumps({
            "score": 85,
            "strengths": ["Clear code"],
            "weaknesses": [],
            "pass": True
        })
        
        result = await orchestrator._run_structured_workflow(task_id, description, "Developer")
        
        assert result == "Draft content"
        assert mock_chat.call_count == 2 # Draft + Review
        assert mock_gen.call_count == 1  # Validation
        assert mock_log.call_count == 1  # Telemetry log
