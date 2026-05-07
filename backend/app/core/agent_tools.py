import inspect
import logging
from collections.abc import Callable
from typing import Any

logger = logging.getLogger(__name__)


class ToolRegistry:
    """Registry for tools that agents can use."""

    def __init__(self):
        self._tools: dict[str, dict[str, Any]] = {}

    def register_tool(self, name: str, func: Callable, description: str):
        """Register a function as a tool."""
        sig = inspect.signature(func)
        params = {
            k: {
                "type": str(v.annotation),
                "default": v.default if v.default is not inspect.Parameter.empty else None,
            }
            for k, v in sig.parameters.items()
        }

        self._tools[name] = {"func": func, "description": description, "parameters": params}
        logger.info(f"Tool registered: {name}")

    def get_tool_definitions(self) -> list[dict[str, Any]]:
        """Return tool definitions for LLM prompting."""
        defs = []
        for name, info in self._tools.items():
            defs.append(
                {"name": name, "description": info["description"], "parameters": info["parameters"]}
            )
        return defs

    async def call_tool(self, name: str, **kwargs) -> Any:
        """Call a registered tool."""
        if name not in self._tools:
            raise ValueError(f"Tool {name} not found")

        func = self._tools[name]["func"]
        if inspect.iscoroutinefunction(func):
            return await func(**kwargs)
        return func(**kwargs)


# Global registry instance
agent_tool_registry = ToolRegistry()

# --- Pre-register some core tools ---


def search_knowledge_base(query: str):
    """Search the internal knowledge base / RAG."""
    # This will be called from within the agent context where we have DB session
    # For now, placeholder or dynamic import
    pass


async def get_obsidian_note(path: str):
    """Read a specific note from the Obsidian vault."""
    from app.integrations.obsidian import get_obsidian_client

    client = get_obsidian_client()
    return await client.read_note(path)


# Add more tools as needed...
