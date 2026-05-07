import os
import glob
import json
import asyncio
import re
from typing import List, Dict, Any, Optional
from pydantic import BaseModel, Field
from core.providers.llm_client import llm_client
from core.execution.message_bus import message_bus, AgentMessage, AgentMessageBus

class SubTask(BaseModel):
    id: str
    description: str
    assigned_agent: str
    dependencies: List[str] = Field(default_factory=list)

class ChiefOrchestrator:
    def __init__(self, bus: AgentMessageBus = message_bus, agents_dir: str = r"C:\Users\menum\.gemini\agents"):
        self.bus = bus
        self.agents_dir = agents_dir
        self._available_agents_cache = None
        
        # Priority 4: Agent Specialization Matrix
        # Deterministic mapping of task keywords to specific agent personas.
        self.agent_matrix = {
            "database": "Database_Expert",
            "sql": "Database_Expert",
            "postgres": "Database_Expert",
            "react": "Frontend_Dev",
            "frontend": "Frontend_Dev",
            "ui": "Frontend_Dev",
            "api": "Backend_Dev",
            "fastapi": "Backend_Dev",
            "backend": "Backend_Dev",
            "security": "Security_Expert",
            "auth": "Security_Expert",
            "docker": "DevOps_Engineer",
            "k8s": "DevOps_Engineer",
            "deployment": "DevOps_Engineer"
        }
        
        self.routing_table = self._build_deterministic_routing_table()
        
    def _build_deterministic_routing_table(self) -> Dict[str, callable]:
        """Table of regex patterns to pre-defined task breakdowns (Project Template System)"""
        return {
            r"(?i)^create api endpoint.*": self._template_api_endpoint,
            r"(?i)^create react component.*": self._template_react_component,
            r"(?i).*(frontend|react|ui|web|component|interface).*": self._route_frontend_project,
            r"(?i).*(backend|api|database|microservice|endpoint).*": self._route_backend_project,
            r"(?i).*(data pipeline|analytics|etl|scraping|scraper).*": self._route_data_project,
            r"(?i).*(security|auth|login|oauth|encryption).*": self._route_security_project,
        }
        
    def _template_api_endpoint(self, desc: str) -> List[SubTask]:
        return [
            SubTask(id="api_route", description=f"Implement FastAPI route for: {desc}", assigned_agent="Backend_Dev"),
            SubTask(id="api_test", description="Write Pytest for API route", assigned_agent="Backend_Dev", dependencies=["api_route"]),
            SubTask(id="api_doc", description="Update OpenAPI/Swagger documentation", assigned_agent="Architect", dependencies=["api_route"])
        ]

    def _template_react_component(self, desc: str) -> List[SubTask]:
        return [
            SubTask(id="react_comp", description=f"Implement React component: {desc}", assigned_agent="Frontend_Dev"),
            SubTask(id="react_story", description="Create Storybook entry for component", assigned_agent="Frontend_Dev", dependencies=["react_comp"]),
            SubTask(id="react_test", description="Write React Testing Library test", assigned_agent="Frontend_Dev", dependencies=["react_comp"])
        ]
        
    def _route_frontend_project(self, desc: str) -> List[SubTask]:
        return [
            SubTask(id="ui_1", description=f"Design UI/UX components for: {desc}", assigned_agent="Architect"),
            SubTask(id="ui_2", description="Implement React/Next.js frontend", assigned_agent="Frontend_Dev", dependencies=["ui_1"])
        ]
        
    def _route_backend_project(self, desc: str) -> List[SubTask]:
        return [
            SubTask(id="api_1", description=f"Design database schema and API routes for: {desc}", assigned_agent="Architect"),
            SubTask(id="api_2", description="Implement backend FastAPI service", assigned_agent="Backend_Dev", dependencies=["api_1"]),
            SubTask(id="api_3", description="Review security of endpoints", assigned_agent="Security_Expert", dependencies=["api_2"])
        ]

    def _route_data_project(self, desc: str) -> List[SubTask]:
        return [
            SubTask(id="data_1", description=f"Design data model and pipeline for: {desc}", assigned_agent="Data_Engineer"),
            SubTask(id="data_2", description="Implement ETL processes and data ingestion", assigned_agent="Backend_Dev", dependencies=["data_1"])
        ]
        
    def _route_security_project(self, desc: str) -> List[SubTask]:
        return [
            SubTask(id="sec_1", description=f"Threat modeling and auth design for: {desc}", assigned_agent="Security_Expert"),
            SubTask(id="sec_2", description="Implement secure authentication/authorization", assigned_agent="Backend_Dev", dependencies=["sec_1"])
        ]

    async def get_available_agents(self) -> Dict[str, str]:
        if self._available_agents_cache is not None:
            return self._available_agents_cache
            
        def _read():
            agents = {}
            if not isinstance(self.agents_dir, str):
                self.agents_dir = r"C:\Users\menum\.gemini\agents"

            if os.path.exists(self.agents_dir):
                for filepath in glob.glob(os.path.join(self.agents_dir, "*.md")):
                    agent_name = os.path.basename(filepath).replace(".md", "")
                    with open(filepath, "r", encoding="utf-8") as f:
                        agents[agent_name] = f.read()
            return agents
            
        agents = await asyncio.to_thread(_read)
        if not agents:
            agents = {
                "Architect": "You are the Principal Systems Architect. Design robust, distributed architectures.",
                "Security_Expert": "You are the Chief Security Officer. Focus on zero-trust, encryption, and threat modeling.",
                "Data_Engineer": "You are the Lead Data Engineer. Optimize for high-throughput streaming and data lakes.",
                "Backend_Dev": "You are the Senior Backend Engineer. Implement clean, maintainable, and highly tested code.",
                "Frontend_Dev": "You are the Senior Frontend Engineer. Build responsive, accessible, and performant user interfaces.",
                "Database_Expert": "You are the Database Expert. Optimize queries, design schemas, and manage migrations.",
                "DevOps_Engineer": "You are the DevOps Engineer. Automate deployments, manage infrastructure, and ensure high availability."
            }
        self._available_agents_cache = agents
        return agents

    async def breakdown_project(self, project_description: str) -> List[SubTask]:
        # Priority 4: 1. Check Agent Specialization Matrix for exact keyword hits
        desc_lower = project_description.lower()
        matched_persona = None
        for keyword, persona in self.agent_matrix.items():
            if keyword in desc_lower:
                matched_persona = persona
                print(f"Agent Matrix matched keyword '{keyword}' -> routing to {persona}")
                break
                
        if matched_persona:
            return [
                SubTask(id=f"task_{matched_persona}", description=project_description, assigned_agent=matched_persona)
            ]

        # 2. Try Deterministic Routing Table for broader project patterns
        for pattern, handler in self.routing_table.items():
            if re.match(pattern, project_description):
                print(f"Deterministic routing matched pattern: {pattern}")
                return handler(project_description)
                
        # 3. Fallback to LLM breakdown
        print("No deterministic route matched. Falling back to LLM breakdown.")
        available_agents = await self.get_available_agents()
        system_prompt = f"""
        You are the Chief Orchestrator. Break down the following project into discrete sub-tasks.
        Assign each task to one of the following available agents: {list(available_agents.keys())}.
        Respond STRICTLY with a JSON array of objects, where each object has:
        - "id": string (unique task id like "task_1")
        - "description": string (detailed task description)
        - "assigned_agent": string (must be one of the available agents)
        - "dependencies": array of strings (ids of tasks that must be completed first)
        """
        
        try:
            response = await llm_client.generate_completion(
                system_prompt=system_prompt,
                user_prompt=project_description,
                response_format={"type": "json_object"}
            )
            
            try:
                data = json.loads(response)
                if isinstance(data, dict):
                    if "tasks" in data:
                        tasks_data = data["tasks"]
                    elif "subtasks" in data:
                        tasks_data = data["subtasks"]
                    else:
                        for val in data.values():
                            if isinstance(val, list):
                                tasks_data = val
                                break
                        else:
                            tasks_data = [data]
                else:
                    tasks_data = data
                    
                subtasks = [SubTask(**task) for task in tasks_data]
                return subtasks
            except json.JSONDecodeError:
                print("Failed to parse JSON directly.")
                return []
                
        except Exception as e:
            print(f"Delegation Error: {e}")
            return [
                SubTask(id="task_1", description=f"Initial planning for: {project_description}", assigned_agent="Architect"),
                SubTask(id="task_2", description="Security assessment", assigned_agent="Security_Expert", dependencies=["task_1"])
            ]

    async def execute_project(self, project_description: str):
        await self.bus.publish("system_events", AgentMessage(
            sender="ChiefOrchestrator",
            topic="system_events",
            content=f"Starting project breakdown for: {project_description}"
        ))
        
        subtasks = await self.breakdown_project(project_description)
        
        await self.bus.publish("system_events", AgentMessage(
            sender="ChiefOrchestrator",
            topic="system_events",
            content=f"Project broken down into {len(subtasks)} tasks. Initiating swarm..."
        ))
        
        for task in subtasks:
            msg = AgentMessage(
                sender="ChiefOrchestrator",
                receiver=task.assigned_agent,
                topic="TaskAssigned",
                content=task.model_dump()
            )
            await self.bus.publish("tasks", msg)
            await asyncio.sleep(0.1)
            
        return subtasks
