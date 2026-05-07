import hashlib
import json
import time
from typing import List, Dict, Any, Optional, Callable, Set
from pydantic import BaseModel, Field

class CachedToolOutput(BaseModel):
    output: Any
    timestamp: float
    ttl: int

class ToolCache:
    """
    Implements hashing-based caching for tool outputs to prevent 
    redundant computations and API calls.
    """
    def __init__(self):
        self._cache: Dict[str, CachedToolOutput] = {}

    def _generate_hash(self, tool_name: str, inputs: Dict[str, Any]) -> str:
        """Generates a unique deterministic hash for tool inputs."""
        serialized = json.dumps({"name": tool_name, "inputs": inputs}, sort_keys=True)
        return hashlib.sha256(serialized.encode()).hexdigest()

    def get(self, tool_name: str, inputs: Dict[str, Any]) -> Optional[Any]:
        """Retrieves cached output if available and not expired."""
        cache_key = self._generate_hash(tool_name, inputs)
        cached = self._cache.get(cache_key)
        
        if cached:
            if time.time() - cached.timestamp < cached.ttl:
                return cached.output
            else:
                del self._cache[cache_key]
        return None

    def set(self, tool_name: str, inputs: Dict[str, Any], output: Any, ttl: int = 3600):
        """Caches tool output with a specified TTL."""
        cache_key = self._generate_hash(tool_name, inputs)
        self._cache[cache_key] = CachedToolOutput(
            output=output,
            timestamp=time.time(),
            ttl=ttl
        )

class ToolExecutionPlanner:
    """
    Identifies and organizes independent tools for parallel execution 
    to optimize total turnaround time.
    """
    def plan(self, tool_calls: List[Dict[str, Any]], tool_definitions: Dict[str, Any]) -> List[List[Dict[str, Any]]]:
        """
        Groups tool calls into batches that can be executed in parallel.
        
        Args:
            tool_calls: List of requested tool calls.
            tool_definitions: Schema definitions identifying side-effects.
            
        Returns:
            List of batches, where each batch is a list of independent tool calls.
        """
        # Basic logic: Tools with side effects (write/delete) are sequential
        # Read-only tools can be parallelized.
        parallel_batch = []
        sequential_batches = []

        for call in tool_calls:
            name = call.get("name")
            definition = tool_definitions.get(name, {})
            is_readonly = definition.get("readonly", True)

            if is_readonly:
                parallel_batch.append(call)
            else:
                sequential_batches.append([call])

        batches = []
        if parallel_batch:
            batches.append(parallel_batch)
        batches.extend(sequential_batches)
        
        return batches
