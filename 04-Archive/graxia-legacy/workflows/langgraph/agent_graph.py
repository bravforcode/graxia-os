from typing import Annotated, TypedDict, List, Union
from langgraph.graph import StateGraph, END
from packages.bwcp_protocol.python.envelope import MessageEnvelope

class AgentMeshState(TypedDict):
    mission_id: str
    messages: List[MessageEnvelope]
    current_plan: List[dict]
    blockers: List[str]
    status: str

def chief_of_staff_node(state: AgentMeshState):
    # Logic for CoS to analyze mission and coordinate
    return {"status": "PLANNING"}

def planner_node(state: AgentMeshState):
    # Logic for decomposition
    return {"status": "DECOMPOSING"}

def create_agent_mesh_graph():
    workflow = StateGraph(AgentMeshState)
    
    workflow.add_node("cos", chief_of_staff_node)
    workflow.add_node("planner", planner_node)
    
    workflow.set_entry_point("cos")
    workflow.add_edge("cos", "planner")
    workflow.add_edge("planner", END)
    
    return workflow.compile()
