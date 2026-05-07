import asyncio
import logging
import uuid
from typing import List, Dict, Any, Optional, Callable, Awaitable, Union
from enum import Enum
from pydantic import BaseModel, Field, ConfigDict

from core.logger import setup_logger

logger = setup_logger("state_graph")

class NodeStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    PAUSED = "paused" # Human-in-the-loop wait
    FAILED = "failed"

class WorkflowState(BaseModel):
    """
    Shared memory object for the workflow graph.
    All nodes can read/write to this state.
    """
    execution_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    input: Dict[str, Any] = Field(default_factory=dict)
    output: Dict[str, Any] = Field(default_factory=dict)
    history: List[Dict[str, Any]] = Field(default_factory=list)
    metadata: Dict[str, Any] = Field(default_factory=dict)
    current_node: Optional[str] = None
    next_node: Optional[str] = None
    interrupt: bool = False # Flag for Human-in-the-loop
    
    model_config = ConfigDict(arbitrary_types_allowed=True)

    def add_history(self, node_id: str, data: Any):
        self.history.append({"node": node_id, "timestamp": str(asyncio.get_event_loop().time()), "data": data})

class WorkflowGraph:
    """
    Advanced Agentic State Machine.
    Supports nodes, edges, conditional routing, and Human-in-the-loop.
    """
    
    def __init__(self):
        self.nodes: Dict[str, Callable[[WorkflowState], Awaitable[WorkflowState]]] = {}
        self.edges: Dict[str, Union[str, Callable[[WorkflowState], str]]] = {}
        self.entry_point: Optional[str] = None

    def add_node(self, name: str, func: Callable[[WorkflowState], Awaitable[WorkflowState]]):
        """Adds a processing node to the graph."""
        self.nodes[name] = func
        logger.debug(f"Added node: {name}")

    def set_entry_point(self, name: str):
        """Sets the starting node of the workflow."""
        if name not in self.nodes:
            raise ValueError(f"Node {name} does not exist.")
        self.entry_point = name

    def add_edge(self, from_node: str, to_node: Union[str, Callable[[WorkflowState], str]]):
        """
        Adds a transition edge. 
        'to_node' can be a string (static edge) or a callable (conditional edge).
        """
        if from_node not in self.nodes:
            raise ValueError(f"Source node {from_node} does not exist.")
        self.edges[from_node] = to_node
        logger.debug(f"Added edge from {from_node} to {to_node}")

    async def run(self, initial_state: WorkflowState) -> WorkflowState:
        """Executes the workflow graph."""
        if not self.entry_point:
            raise ValueError("Entry point not set.")
        
        state = initial_state
        
        # FIX: Only set to entry_point if we are starting fresh
        if state.current_node is None:
            state.current_node = self.entry_point
        
        logger.info(f"Starting/Resuming workflow execution: {state.execution_id} at {state.current_node}")
        
        while state.current_node:
            node_name = state.current_node
            node_func = self.nodes[node_name]
            
            logger.info(f"Executing node: {node_name}")
            
            # Execute node logic
            try:
                state = await node_func(state)
                state.add_history(node_name, "completed")
            except Exception as e:
                logger.error(f"Error in node {node_name}: {e}")
                state.add_history(node_name, f"failed: {str(e)}")
                break

            # Human-in-the-Loop Check
            if state.interrupt:
                logger.warning(f"Workflow PAUSED at node {node_name} for human approval.")
                state.current_node = node_name # Will resume from here
                return state

            # Determine next node via edges
            if node_name in self.edges:
                edge = self.edges[node_name]
                if callable(edge):
                    next_node = edge(state)
                else:
                    next_node = edge
                
                if next_node == "__end__":
                    logger.info("Reached end of workflow.")
                    state.current_node = None
                else:
                    state.current_node = next_node
            else:
                logger.info(f"No outgoing edge from {node_name}. Stopping.")
                state.current_node = None

        logger.info(f"Workflow execution complete: {state.execution_id}")
        return state

    async def resume(self, state: WorkflowState) -> WorkflowState:
        """Resumes a paused workflow."""
        logger.info(f"Resuming workflow: {state.execution_id}")
        state.interrupt = False
        return await self.run(state)
