import asyncio
from typing import List, Dict, Any, Optional, Callable
from core.execution.state_graph import WorkflowGraph, WorkflowState
from core.logger import logger, memory_handler
from core.providers.base import BaseLLMProvider

class SelfHealingWrapper:
    """
    Self-Healing Wrapper for WorkflowGraph.
    Monitors node execution, catches failures, and uses a 'bug-hunter' 
    agent to propose fixes before retrying.
    """
    
    def __init__(self, graph: WorkflowGraph, llm: BaseLLMProvider, max_retries: int = 2):
        self.graph = graph
        self.llm = llm
        self.max_retries = max_retries

    async def run(self, initial_state: WorkflowState) -> WorkflowState:
        """
        Executes the workflow with self-healing capabilities.
        """
        if not self.graph.entry_point:
            raise ValueError("Entry point not set in the graph.")
        
        state = initial_state
        if state.current_node is None:
            state.current_node = self.graph.entry_point
            
        logger.info(f"Starting self-healing workflow execution: {state.execution_id}")
        
        while state.current_node:
            node_name = state.current_node
            node_func = self.graph.nodes[node_name]
            
            retry_count = 0
            success = False
            
            while retry_count <= self.max_retries and not success:
                try:
                    logger.info(f"Executing node: {node_name} (Attempt {retry_count + 1})")
                    state = await node_func(state)
                    state.add_history(node_name, "completed")
                    success = True
                except Exception as e:
                    retry_count += 1
                    logger.error(f"Error in node {node_name} (Attempt {retry_count}): {str(e)}")
                    
                    if retry_count > self.max_retries:
                        logger.critical(f"Node {node_name} failed after {self.max_retries} retries. Self-healing exhausted.")
                        state.add_history(node_name, f"failed_after_retries: {str(e)}")
                        state.current_node = None # Stop execution
                        break
                    
                    # Self-Healing Logic: Call the bug-hunter agent
                    logger.info(f"Initiating self-healing for node {node_name}...")
                    logs = memory_handler.get_logs(50)
                    logs_text = "\n".join(logs)
                    
                    healing_prompt = f"""
                    SYSTEM: You are the 'bug-hunter' agent persona for Brav OS.
                    Your task is to analyze a node failure and propose a fix or a workaround.
                    
                    NODE: {node_name}
                    EXCEPTION: {str(e)}
                    
                    LAST 50 LOG LINES:
                    {logs_text}
                    
                    INSTRUCTION: Based on the error and logs, provide a concise explanation and a JSON workaround/fix that can be applied to the state to allow the next retry to succeed.
                    """
                    
                    try:
                        healing_response = await self.llm.generate_response(healing_prompt)
                        # In a real system, we'd parse the patch and apply it to state.metadata or state.input
                        logger.info(f"Bug-hunter proposed fix: {healing_response['content'][:200]}...")
                        # Mock applying the patch
                        state.metadata["last_fix"] = healing_response["content"]
                        await asyncio.sleep(1) # Cooling period
                    except Exception as healing_err:
                        logger.error(f"Self-healing agent failed: {str(healing_err)}")

            if not success:
                break

            # Determine next node (duplicated from state_graph.py but needed here to wrap)
            if node_name in self.graph.edges:
                edge = self.graph.edges[node_name]
                next_node = edge(state) if callable(edge) else edge
                if next_node == "__end__":
                    state.current_node = None
                else:
                    state.current_node = next_node
            else:
                state.current_node = None

        logger.info(f"Self-healing workflow execution complete: {state.execution_id}")
        return state
