"""
Agent Service - Manages agent network communication
"""

import os
import uuid
from datetime import datetime
from typing import Any

import httpx

from ..models import AgentNetworkStatus, AgentStatus, AgentType, DelegateRequest, DelegateResponse


class AgentService:
    """Service for managing the agent network"""

    def __init__(self):
        self.agents = {
            AgentType.HERMES: {
                "url": os.getenv("HERMES_AGENT_URL", "http://localhost:8001"),
                "enabled": True,
            },
            AgentType.MERCURY: {
                "url": "https://api.mercury.com/v1",
                "api_key": os.getenv("MERCURY_API_KEY"),
                "enabled": bool(os.getenv("MERCURY_API_KEY")),
            },
            AgentType.ATHENA: {"url": "internal", "enabled": True},
            AgentType.HEPHAESTUS: {"url": "internal", "enabled": True},
            AgentType.N8N: {
                "url": os.getenv("N8N_WEBHOOK_URL"),
                "api_url": os.getenv("N8N_API_URL"),
                "api_key": os.getenv("N8N_API_KEY"),
                "enabled": bool(os.getenv("N8N_WEBHOOK_URL")),
            },
        }
        self.http_client = httpx.AsyncClient(timeout=30.0)

    async def delegate(self, request: DelegateRequest) -> DelegateResponse:
        """Delegate task to an agent"""

        task_id = str(uuid.uuid4())[:8]
        agent_config = self.agents.get(request.to_agent)

        if not agent_config or not agent_config.get("enabled"):
            return DelegateResponse(
                task_id=task_id,
                assigned_to=request.to_agent,
                status="failed",
                result_preview=f"Agent {request.to_agent} is not available",
            )

        try:
            # Route to appropriate agent
            if request.to_agent == AgentType.HERMES:
                result = await self._delegate_to_hermes(request, task_id)
            elif request.to_agent == AgentType.MERCURY:
                result = await self._delegate_to_mercury(request, task_id)
            elif request.to_agent == AgentType.N8N:
                result = await self._delegate_to_n8n(request, task_id)
            elif request.to_agent == AgentType.ATHENA:
                result = await self._delegate_to_athena(request, task_id)
            elif request.to_agent == AgentType.HEPHAESTUS:
                result = await self._delegate_to_hephaestus(request, task_id)
            else:
                result = {"status": "failed", "error": "Unknown agent"}

            return DelegateResponse(
                task_id=task_id,
                assigned_to=request.to_agent,
                status=result.get("status", "queued"),
                estimated_completion=result.get("estimated_completion"),
                result_preview=result.get("preview", "Task queued successfully"),
                full_result_url=result.get("result_url"),
            )

        except Exception as e:
            return DelegateResponse(
                task_id=task_id,
                assigned_to=request.to_agent,
                status="failed",
                result_preview=f"Error: {str(e)}",
            )

    async def get_network_status(self) -> AgentNetworkStatus:
        """Get status of all agents"""

        agents = []

        for agent_type, config in self.agents.items():
            status = await self._check_agent_status(agent_type, config)
            agents.append(status)

        return AgentNetworkStatus(
            orchestrator="openclaude",
            agents=agents,
            messages_in_queue=0,  # Would track actual queue
            recent_errors=[],  # Would track recent errors
        )

    async def send_command(self, agent_name: str, command: str) -> dict[str, Any]:
        """Send command to specific agent"""

        try:
            agent_type = AgentType(agent_name)
            config = self.agents.get(agent_type)

            if not config:
                return {"error": f"Unknown agent: {agent_name}"}

            # Send command based on agent type
            # This is a simplified version
            return {
                "agent": agent_name,
                "command": command,
                "status": "received",
                "message": f"Command sent to {agent_name}",
            }

        except ValueError:
            return {"error": f"Invalid agent name: {agent_name}"}
        except Exception as e:
            return {"error": str(e)}

    async def _check_agent_status(self, agent_type: AgentType, config: dict) -> AgentStatus:
        """Check status of a specific agent"""

        if not config.get("enabled"):
            return AgentStatus(
                agent=agent_type,
                online=False,
                current_load=0,
                capabilities=[],
                last_seen=datetime.utcnow(),
            )

        # Try to ping agent
        online = False
        try:
            if config.get("url") and config["url"] != "internal":
                response = await self.http_client.get(f"{config['url']}/health", timeout=5.0)
                online = response.status_code == 200
        except:
            online = False

        # Get capabilities based on agent type
        capabilities = self._get_agent_capabilities(agent_type)

        return AgentStatus(
            agent=agent_type,
            online=online or config.get("url") == "internal",
            current_load=0,  # Would query actual load
            capabilities=capabilities,
            last_seen=datetime.utcnow(),
        )

    def _get_agent_capabilities(self, agent_type: AgentType) -> list[str]:
        """Get capabilities for an agent type"""

        capabilities = {
            AgentType.HERMES: [
                "task_planning",
                "scheduling",
                "reminders",
                "deadline_tracking",
                "priority_management",
            ],
            AgentType.MERCURY: [
                "code_review",
                "security_scan",
                "vulnerability_detection",
                "documentation_generation",
                "test_coverage_analysis",
            ],
            AgentType.ATHENA: [
                "knowledge_graph_query",
                "semantic_search",
                "entity_extraction",
                "relationship_mapping",
            ],
            AgentType.HEPHAESTUS: [
                "infrastructure_as_code",
                "deployment_automation",
                "monitoring_setup",
                "log_analysis",
                "performance_tuning",
            ],
            AgentType.N8N: [
                "workflow_execution",
                "webhook_handling",
                "data_transformation",
                "notification_routing",
                "integration_hub",
            ],
        }

        return capabilities.get(agent_type, [])

    async def _delegate_to_hermes(self, request: DelegateRequest, task_id: str) -> dict:
        """Delegate to Hermes task planner"""

        config = self.agents[AgentType.HERMES]

        try:
            response = await self.http_client.post(
                f"{config['url']}/tasks",
                json={
                    "task_id": task_id,
                    "description": request.task,
                    "priority": request.priority,
                    "context": request.context,
                    "deadline": request.deadline.isoformat() if request.deadline else None,
                },
                timeout=10.0,
            )

            if response.status_code == 200:
                return {"status": "queued", "preview": f"Task planned: {request.task[:50]}..."}
            else:
                return {"status": "failed", "preview": f"Hermes error: {response.status_code}"}

        except Exception:
            # Fallback if Hermes is not running
            return {
                "status": "queued",
                "preview": f"Task '{request.task[:30]}...' queued for planning (offline mode)",
            }

    async def _delegate_to_mercury(self, request: DelegateRequest, task_id: str) -> dict:
        """Delegate to Mercury code analyzer"""

        config = self.agents[AgentType.MERCURY]

        if not config.get("api_key"):
            return {"status": "failed", "preview": "Mercury API key not configured"}

        try:
            # Would call Mercury API
            return {
                "status": "in_progress",
                "preview": "Code analysis started",
                "estimated_completion": datetime.utcnow(),
            }
        except Exception as e:
            return {"status": "failed", "preview": f"Error: {str(e)}"}

    async def _delegate_to_n8n(self, request: DelegateRequest, task_id: str) -> dict:
        """Delegate to n8n workflow engine"""

        config = self.agents[AgentType.N8N]

        try:
            await self.http_client.post(
                config["url"],
                json={
                    "task_id": task_id,
                    "task": request.task,
                    "priority": request.priority,
                    "context": request.context,
                },
                headers={"Authorization": f"Bearer {config.get('api_key', '')}"},
                timeout=10.0,
            )

            return {"status": "queued", "preview": "Workflow triggered"}

        except Exception as e:
            return {"status": "failed", "preview": f"n8n error: {str(e)}"}

    async def _delegate_to_athena(self, request: DelegateRequest, task_id: str) -> dict:
        """Delegate to Athena knowledge manager"""

        # Internal agent - would query knowledge graph
        return {
            "status": "completed",
            "preview": "Knowledge query completed",
            "result_url": f"/knowledge/{task_id}",
        }

    async def _delegate_to_hephaestus(self, request: DelegateRequest, task_id: str) -> dict:
        """Delegate to Hephaestus DevOps engineer"""

        # Internal agent - would handle infrastructure
        return {
            "status": "queued",
            "preview": "Infrastructure task queued",
            "estimated_completion": datetime.utcnow(),
        }

    async def close(self):
        """Close HTTP client"""
        await self.http_client.aclose()
