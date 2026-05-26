"""Registry for cross-agent context pack consistency."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime


@dataclass
class AgentContextRegistration:
    agent_id: str
    task_id: str
    context_pack_id: str
    cache_key: str
    file_hashes: dict[str, str]
    compression_mode: str
    registered_at: str = field(default_factory=lambda: datetime.now(UTC).isoformat())


class MultiAgentContextRegistry:
    def __init__(self) -> None:
        self._registrations: dict[str, list[AgentContextRegistration]] = {}

    def register(self, registration: AgentContextRegistration) -> None:
        self._registrations.setdefault(registration.task_id, []).append(registration)

    def get_registrations(self, task_id: str) -> list[AgentContextRegistration]:
        return list(self._registrations.get(task_id, []))

    def validate_consistency(self, task_id: str) -> dict[str, object]:
        registrations = self._registrations.get(task_id, [])
        if not registrations:
            return {"consistent": True, "mismatched_agents": [], "baseline_agent": None}

        baseline = registrations[0]
        mismatched_agents: list[str] = []
        for registration in registrations[1:]:
            if (
                registration.cache_key != baseline.cache_key
                or registration.file_hashes != baseline.file_hashes
                or registration.compression_mode != baseline.compression_mode
            ):
                mismatched_agents.append(registration.agent_id)

        return {
            "consistent": not mismatched_agents,
            "mismatched_agents": mismatched_agents,
            "baseline_agent": baseline.agent_id,
        }
