import logging
from typing import Dict, Type, Any
from app.agents.base import BaseAgent

logger = logging.getLogger(__name__)

class AgentRegistry:
    _agents: Dict[str, Any] = {}

    @classmethod
    def register(cls, name: str, agent_instance: Any):
        cls._agents[name] = agent_instance
        logger.info(f"Registered agent: {name}")

    @classmethod
    def get_agent(cls, name: str) -> Any:
        if name in cls._agents:
            return cls._agents[name]
        
        # Fallback to dynamic import
        try:
            module_name = f"app.agents.{name}"
            # Some names might need mapping, e.g. "researcher" -> "research_collector"
            if name == "researcher":
                module_name = "app.agents.research_collector"
                
            module = __import__(module_name, fromlist=[f"{name}_agent"])
            agent = getattr(module, f"{name}_agent")
            cls.register(name, agent)
            return agent
        except Exception as e:
            logger.error(f"Failed to resolve agent {name}: {e}")
            return None

agent_registry = AgentRegistry()
