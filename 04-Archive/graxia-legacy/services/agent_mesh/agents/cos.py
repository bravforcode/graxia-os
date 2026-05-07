import logging
from typing import TypedDict, List, Dict, Any, Optional
from langgraph.graph import StateGraph, END
from pydantic import BaseModel

# Try importing from the expected package path, provide stubs if not available in this environment yet
try:
    from bravos_core.python.agent import BaseBravOSAgent, BWCPMessage
except ImportError:
    # Fallback/stub if not found in path for local type checking
    class BWCPMessage(BaseModel):
        id: str
        content: str
        sender: str
        receiver: str

    class BaseBravOSAgent:
        def process_message(self, message: BWCPMessage):
            pass

from .planner import PlannerAgent
from .reviewer import ReviewerAgent

logger = logging.getLogger(__name__)

class AgentState(TypedDict):
    """State for the CoS Agent Graph."""
    mission: str
    tasks: List[Dict[str, Any]]
    current_task_index: int
    results: List[Any]
    reviews: List[Dict[str, Any]]
    status: str # 'planning', 'executing', 'reviewing', 'complete', 'failed'
    error: Optional[str]

class ChiefOfStaffAgent(BaseBravOSAgent):
    """
    Chief of Staff (CoS) Agent.
    The primary orchestrator that receives a mission, plans it, allocates/executes it, and reviews it.
    """
    
    def __init__(self, name: str = "CoS_Agent"):
        self.logger = logging.getLogger(self.__class__.__name__)
        self.name = name
        self.planner = PlannerAgent()
        self.reviewer = ReviewerAgent()
        self.graph = self._build_graph()
        
    def _build_graph(self):
        """Build the LangGraph state machine for the CoS agent."""
        workflow = StateGraph(AgentState)
        
        # Add nodes
        workflow.add_node("planning", self._node_plan)
        workflow.add_node("executing", self._node_execute)
        workflow.add_node("reviewing", self._node_review)
        workflow.add_node("complete", self._node_complete)
        workflow.add_node("failed", self._node_fail)
        
        # Define edges
        workflow.set_entry_point("planning")
        
        workflow.add_edge("planning", "executing")
        
        # Conditional edge from executing
        workflow.add_conditional_edges(
            "executing",
            self._should_review,
            {
                "reviewing": "reviewing",
                "failed": "failed"
            }
        )
        
        # Conditional edge from reviewing
        workflow.add_conditional_edges(
            "reviewing",
            self._next_step,
            {
                "executing": "executing",
                "complete": "complete",
                "failed": "failed"
            }
        )
        
        workflow.add_edge("complete", END)
        workflow.add_edge("failed", END)
        
        return workflow.compile()
        
    # --- Node Functions ---
    
    def _node_plan(self, state: AgentState) -> AgentState:
        self.logger.info(f"Node: Planning mission '{state['mission']}'")
        try:
            tasks = self.planner.plan(state['mission'])
            state['tasks'] = tasks
            state['current_task_index'] = 0
            state['status'] = 'executing'
            return state
        except Exception as e:
            self.logger.error(f"Planning failed: {str(e)}")
            state['status'] = 'failed'
            state['error'] = str(e)
            return state

    def _node_execute(self, state: AgentState) -> AgentState:
        current_idx = state.get('current_task_index', 0)
        tasks = state.get('tasks', [])
        
        if current_idx >= len(tasks):
            self.logger.info("Node: Execute - No more tasks to execute.")
            state['status'] = 'complete'
            return state
            
        task = tasks[current_idx]
        self.logger.info(f"Node: Executing task {current_idx + 1}/{len(tasks)}: {task.get('description')}")
        
        try:
            # Stub: Allocate to another agent or execute directly
            # In a real implementation, this would send a message to an Allocator or specific Agent
            result = f"Successfully executed: {task.get('description')}"
            
            if 'results' not in state:
                state['results'] = []
            state['results'].append(result)
            
            state['status'] = 'reviewing'
            return state
        except Exception as e:
            self.logger.error(f"Execution failed: {str(e)}")
            state['status'] = 'failed'
            state['error'] = str(e)
            return state
            
    def _node_review(self, state: AgentState) -> AgentState:
        current_idx = state.get('current_task_index', 0)
        tasks = state.get('tasks', [])
        results = state.get('results', [])
        
        if current_idx >= len(tasks) or current_idx >= len(results):
            state['status'] = 'failed'
            state['error'] = "Review attempted on invalid task index."
            return state
            
        task = tasks[current_idx]
        result = results[current_idx]
        
        self.logger.info(f"Node: Reviewing task {current_idx + 1}/{len(tasks)}")
        
        try:
            review_result = self.reviewer.review(task, result)
            
            if 'reviews' not in state:
                state['reviews'] = []
            state['reviews'].append(review_result.model_dump())
            
            if review_result.passed:
                self.logger.info("Task passed review.")
                state['current_task_index'] += 1
            else:
                self.logger.warning(f"Task failed review: {review_result.feedback}")
                # For this stub, we fail the whole mission. Could implement retry logic.
                state['status'] = 'failed'
                state['error'] = f"Task review failed: {review_result.feedback}"
                
            return state
        except Exception as e:
            self.logger.error(f"Review failed: {str(e)}")
            state['status'] = 'failed'
            state['error'] = str(e)
            return state

    def _node_complete(self, state: AgentState) -> AgentState:
        self.logger.info("Node: Mission Complete!")
        state['status'] = 'complete'
        return state
        
    def _node_fail(self, state: AgentState) -> AgentState:
        self.logger.error(f"Node: Mission Failed. Error: {state.get('error')}")
        state['status'] = 'failed'
        return state
        
    # --- Edge Condition Functions ---
    
    def _should_review(self, state: AgentState) -> str:
        if state['status'] == 'failed':
            return 'failed'
        return 'reviewing'
        
    def _next_step(self, state: AgentState) -> str:
        if state['status'] == 'failed':
            return 'failed'
        
        current_idx = state.get('current_task_index', 0)
        tasks = state.get('tasks', [])
        
        if current_idx >= len(tasks):
            return 'complete'
        return 'executing'
        
    # --- BaseBravOSAgent Implementation ---
    
    def process_message(self, message: BWCPMessage) -> Any:
        """
        Process an incoming BWCPMessage that triggers a mission.
        """
        self.logger.info(f"CoS Agent '{self.name}' received message: {message.id}")
        
        initial_state: AgentState = {
            "mission": message.content,
            "tasks": [],
            "current_task_index": 0,
            "results": [],
            "reviews": [],
            "status": "planning",
            "error": None
        }
        
        # Run the graph
        self.logger.info(f"Starting mission workflow for: {message.content}")
        final_state = self.graph.invoke(initial_state)
        self.logger.info(f"Workflow finished with status: {final_state['status']}")
        
        return final_state
