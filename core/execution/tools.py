import os
import subprocess
import logging
from typing import Dict, Any, List, Callable, Optional
from pathlib import Path
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)

class Tool(BaseModel):
    name: str
    description: str
    func: Callable
    parameters: Dict[str, Any]

class ToolRegistry:
    """
    Registry for managing and discovering autonomous tools.
    """
    def __init__(self):
        self.tools: Dict[str, Tool] = {}

    def register(self, name: str, description: str, parameters: Dict[str, Any]):
        def decorator(func: Callable):
            self.tools[name] = Tool(
                name=name,
                description=description,
                func=func,
                parameters=parameters
            )
            return func
        return decorator

    def get_tool(self, name: str) -> Optional[Tool]:
        return self.tools.get(name)

    def list_tools(self) -> List[Dict[str, Any]]:
        return [
            {
                "name": t.name,
                "description": t.description,
                "parameters": t.parameters
            }
            for t in self.tools.values()
        ]

    def to_openai_format(self) -> List[Dict[str, Any]]:
        """
        Converts registered tools to OpenAI function calling format.
        """
        return [
            {
                "type": "function",
                "function": {
                    "name": t.name,
                    "description": t.description,
                    "parameters": t.parameters
                }
            }
            for t in self.tools.values()
        ]

# Global Registry
registry = ToolRegistry()

class AutonomousTools:
    """
    Implementation of the core autonomous tools for Brav OS.
    """
    
    @staticmethod
    @registry.register(
        name="run_command",
        description="Executes a shell command safely and returns the output.",
        parameters={
            "type": "object",
            "properties": {
                "command": {"type": "string", "description": "The shell command to execute."}
            },
            "required": ["command"]
        }
    )
    def run_command(command: str) -> Dict[str, Any]:
        logger.info(f"Executing command: {command}")
        try:
            # Using a list for command is safer, but for complex shell commands, 
            # shell=True might be needed. We'll use shell=True for flexibility here.
            result = subprocess.run(
                command,
                shell=True,
                capture_output=True,
                text=True,
                timeout=30  # Safety timeout
            )
            return {
                "stdout": result.stdout,
                "stderr": result.stderr,
                "exit_code": result.returncode,
                "success": result.returncode == 0
            }
        except subprocess.TimeoutExpired:
            return {"error": "Command timed out", "success": False}
        except Exception as e:
            return {"error": str(e), "success": False}

    @staticmethod
    @registry.register(
        name="manage_file",
        description="Manages files (read, write, append).",
        parameters={
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "The absolute path to the file."},
                "action": {
                    "type": "string", 
                    "enum": ["read", "write", "append"],
                    "description": "The action to perform."
                },
                "content": {"type": "string", "description": "The content for write/append actions."}
            },
            "required": ["path", "action"]
        }
    )
    def manage_file(path: str, action: str, content: Optional[str] = None) -> Dict[str, Any]:
        logger.info(f"File management: {action} on {path}")
        file_path = Path(path)
        try:
            if action == "read":
                if not file_path.exists():
                    return {"error": f"File {path} does not exist", "success": False}
                return {"content": file_path.read_text(encoding="utf-8"), "success": True}
            
            elif action == "write":
                file_path.parent.mkdir(parents=True, exist_ok=True)
                file_path.write_text(content or "", encoding="utf-8")
                return {"message": f"Successfully wrote to {path}", "success": True}
            
            elif action == "append":
                file_path.parent.mkdir(parents=True, exist_ok=True)
                with open(file_path, "a", encoding="utf-8") as f:
                    f.write(content or "")
                return {"message": f"Successfully appended to {path}", "success": True}
            
            return {"error": f"Invalid action: {action}", "success": False}
        except Exception as e:
            return {"error": str(e), "success": False}

    @staticmethod
    @registry.register(
        name="search_knowledge",
        description="Searches the RAG system for relevant knowledge.",
        parameters={
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "The search query."}
            },
            "required": ["query"]
        }
    )
    def search_knowledge(query: str) -> Dict[str, Any]:
        logger.info(f"Searching knowledge for: {query}")
        # Placeholder for real RAG/Qdrant logic
        # In a real implementation, this would call core.retrieval.hybrid_search
        return {
            "results": [
                {"id": "mock_1", "text": f"Found some knowledge about {query} in the RAG system.", "score": 0.95}
            ],
            "success": True
        }

async def execute_tool(name: str, args: Dict[str, Any]) -> Any:
    """
    Executes a tool by name with provided arguments.
    """
    tool = registry.get_tool(name)
    if not tool:
        return {"error": f"Tool {name} not found", "success": False}
    
    # Check if it's a coroutine or regular function
    if os.path.iscoroutinefunction(tool.func):
        return await tool.func(**args)
    else:
        return tool.func(**args)
