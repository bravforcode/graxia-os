from __future__ import annotations

from app.context_engine.multi_agent_registry import AgentContextRegistration, MultiAgentContextRegistry


def test_multi_agent_registry_reports_consistency() -> None:
    registry = MultiAgentContextRegistry()
    registry.register(
        AgentContextRegistration(
            agent_id="agent-a",
            task_id="task-1",
            context_pack_id="ctx-a",
            cache_key="cache-1",
            file_hashes={"a.py": "hash-1"},
            compression_mode="compact",
        )
    )
    registry.register(
        AgentContextRegistration(
            agent_id="agent-b",
            task_id="task-1",
            context_pack_id="ctx-b",
            cache_key="cache-1",
            file_hashes={"a.py": "hash-1"},
            compression_mode="compact",
        )
    )
    result = registry.validate_consistency("task-1")
    assert result["consistent"] is True


def test_multi_agent_registry_detects_mismatch() -> None:
    registry = MultiAgentContextRegistry()
    registry.register(
        AgentContextRegistration(
            agent_id="agent-a",
            task_id="task-1",
            context_pack_id="ctx-a",
            cache_key="cache-1",
            file_hashes={"a.py": "hash-1"},
            compression_mode="compact",
        )
    )
    registry.register(
        AgentContextRegistration(
            agent_id="agent-b",
            task_id="task-1",
            context_pack_id="ctx-b",
            cache_key="cache-2",
            file_hashes={"a.py": "hash-2"},
            compression_mode="summary",
        )
    )
    result = registry.validate_consistency("task-1")
    assert result["consistent"] is False
    assert result["mismatched_agents"] == ["agent-b"]
