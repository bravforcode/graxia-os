from abc import ABC, abstractmethod
from typing import List, Optional, Any, Dict
from pydantic import BaseModel, Field

class MemoryEntry(BaseModel):
    """Base schema for a memory unit."""
    content: str
    timestamp: float
    metadata: Dict[str, Any] = Field(default_factory=dict)

class L1Memory(ABC):
    """
    Working Memory: Fast-access, short-term context.
    Typically holds the last 2-3 exchanges in full.
    """
    @abstractmethod
    def add(self, content: str, metadata: Optional[Dict] = None):
        ...
    
    @abstractmethod
    def get_context(self) -> str:
        ...

class L2Memory(ABC):
    """
    Episodic Memory: Conversation history log with rolling summary.
    Summary logic: Compress history every 10 turns.
    """
    @abstractmethod
    def log_turn(self, role: str, message: str):
        ...
    
    @abstractmethod
    def get_history(self, limit: int = 10) -> List[MemoryEntry]:
        ...
    
    @abstractmethod
    def update_summary(self, summary: str):
        """Update the compressed rolling summary of the conversation."""
        ...

class L3Memory(ABC):
    """
    Semantic Knowledge Base: Long-term storage of facts and concepts.
    Typically stored in a vector database for semantic search.
    """
    @abstractmethod
    def upsert_knowledge(self, key: str, value: Any, embedding: List[float]):
        ...
    
    @abstractmethod
    def search(self, query_embedding: List[float], top_k: int = 5) -> List[MemoryEntry]:
        ...

class L4Memory(ABC):
    """
    Procedural Memory: Stores 'How-to' instructions, code snippets, and workflows.
    Used for tool-use and complex task execution instructions.
    """
    @abstractmethod
    def store_procedure(self, name: str, steps: List[str], constraints: List[str]):
        ...
    
    @abstractmethod
    def fetch_procedure(self, name: str) -> Optional[Dict]:
        ...

class IntelligenceArchitecture:
    """
    Orchestrator for multi-level memory systems.
    """
    def __init__(self, l1: L1Memory, l2: L2Memory, l3: L3Memory, l4: L4Memory):
        self.working = l1
        self.episodic = l2
        self.semantic = l3
        self.procedural = l4
