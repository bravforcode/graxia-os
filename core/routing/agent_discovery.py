import os
import glob
from typing import List, Dict, Any
from pydantic import BaseModel

AGENT_PATH = "C:\\Users\\menum\\.gemini\\agents\\*.md"

class DiscoveryResult(BaseModel):
    name: str
    description: str
    path: str

class AgentDiscovery:
    """
    Dynamically discovers sub-agents from Markdown definitions.
    Enables 'Infinite Flexibility' by just adding a .md file.
    """
    
    @staticmethod
    def discover_agents() -> List[DiscoveryResult]:
        agents = []
        files = glob.glob(AGENT_PATH)
        
        for file_path in files:
            name = os.path.basename(file_path).replace(".md", "")
            with open(file_path, 'r', encoding='utf-8') as f:
                content = f.read()
                # Extract first paragraph or specific metadata if exists
                # For now, we take the first line as description (simple version)
                lines = [line.strip() for line in content.split('\n') if line.strip()]
                description = lines[0] if lines else "No description available."
                
                agents.append(DiscoveryResult(
                    name=name,
                    description=description,
                    path=file_path
                ))
        return agents

    @staticmethod
    def get_agent_prompt(name: str) -> str:
        """Loads the full agent definition prompt."""
        path = os.path.join(os.path.dirname(AGENT_PATH), f"{name}.md")
        if os.path.exists(path):
            with open(path, 'r', encoding='utf-8') as f:
                return f.read()
        return f"System: Act as {name}."
