import asyncio
import json
import logging
import os
import time
from typing import Dict, Any, List, Optional
from pathlib import Path

from core.execution.message_bus import message_bus, AgentMessage, AgentMessageBus
from core.providers.llm_client import llm_client, LLMResponse
from core.execution.tools import registry, execute_tool
from core.routing.task_delegator import ChiefOrchestrator
from core.telemetry import TaskCostTracker

logger = logging.getLogger(__name__)

STATE_DIR = Path(".state")
AGENT_RUNS_DIR = STATE_DIR / "agent_runs"
DLQ_FILE = STATE_DIR / "dlq.json"

from core.monitoring import DLQ_DEPTH, AGENT_ITERATIONS

class DeadLetterQueue:
    """Manages failed tasks that have exhausted all retries."""
    
    _lock = asyncio.Lock()

    @staticmethod
    async def add(task_id: str, agent_name: str, task: str, error: str):
        """Safely appends a failed task to the DLQ using async file I/O."""
        DLQ_DEPTH.inc() # Increment Prometheus metric
        
        async with DeadLetterQueue._lock:
            def _write():
                DLQ_FILE.parent.mkdir(parents=True, exist_ok=True)
                dlq_data = []
                if DLQ_FILE.exists():
                    try:
                        with open(DLQ_FILE, "r") as f:
                            dlq_data = json.load(f)
                    except json.JSONDecodeError:
                        pass
                dlq_data.append({
                    "task_id": task_id,
                    "agent_name": agent_name,
                    "task": task,
                    "error": error,
                    "timestamp": time.time()
                })
                with open(DLQ_FILE, "w") as f:
                    json.dump(dlq_data, f, indent=2)
                    
            await asyncio.to_thread(_write)
            logger.warning(f"Task {task_id} appended to Dead Letter Queue.")


class AutonomousAgent:
    """
    A truly autonomous agent that can reason, act (use tools), and observe.
    Now includes access to Shared Memory Space.
    """
    def __init__(self, name: str, system_prompt: str, bus: AgentMessageBus):
        self.name = name
        self.system_prompt = system_prompt
        self.bus = bus
        self.message_history: List[Dict[str, Any]] = [
            {"role": "system", "content": system_prompt}
        ]
        # Priority 4: Shared Memory Space
        self.shared_memory: Dict[str, Any] = {}

    async def _save_state(self, task_id: str, current_iteration: int):
        """Persists agent state safely to a local JSON file."""
        def _write():
            AGENT_RUNS_DIR.mkdir(parents=True, exist_ok=True)
            state_file = AGENT_RUNS_DIR / f"{task_id}.json"
            state = {
                "message_history": self.message_history,
                "current_iteration": current_iteration
            }
            with open(state_file, "w") as f:
                json.dump(state, f, indent=2)
                
        await asyncio.to_thread(_write)

    async def _load_state(self, task_id: str) -> Optional[int]:
        """Loads agent state if it exists. Returns the last iteration count."""
        state_file = AGENT_RUNS_DIR / f"{task_id}.json"
        
        def _read() -> Optional[int]:
            if not state_file.exists():
                return None
            try:
                with open(state_file, "r") as f:
                    state = json.load(f)
                    self.message_history = state.get("message_history", self.message_history)
                    return state.get("current_iteration", 0)
            except Exception as e:
                logger.error(f"[{self.name}] Failed to load state for {task_id}: {e}")
                return None
                
        return await asyncio.to_thread(_read)

    async def run_to_completion(self, task_id: str, task: str, max_iterations: int = 10) -> str:
        """
        Runs the agent in an autonomous loop until the task is finished or max iterations reached.
        Includes a retry policy and DLQ routing.
        """
        max_retries = 3
        for attempt in range(max_retries + 1):
            try:
                return await self._run_loop(task_id, task, max_iterations)
            except Exception as e:
                logger.error(f"[{self.name}] Critical error during task {task_id}: {e}", exc_info=True)
                if attempt < max_retries:
                    backoff = 2 ** attempt
                    logger.info(f"[{self.name}] Retrying task {task_id} in {backoff} seconds (Attempt {attempt + 1}/{max_retries})...")
                    await asyncio.sleep(backoff)
                else:
                    logger.error(f"[{self.name}] Task {task_id} failed after {max_retries} retries. Routing to DLQ.")
                    await DeadLetterQueue.add(task_id, self.name, task, str(e))
                    return "Execution failed. Task sent to Dead Letter Queue."
                    
        return "Execution failed."

    async def _run_loop(self, task_id: str, task: str, max_iterations: int) -> str:
        start_iteration = 0
        loaded_iteration = await self._load_state(task_id)
        
        if loaded_iteration is not None:
            logger.info(f"[{self.name}] Recovered state for task {task_id}. Resuming from iteration {loaded_iteration}.")
            start_iteration = loaded_iteration
        else:
            self.message_history.append({"role": "user", "content": task})
            await self._save_state(task_id, start_iteration)
            
        await self.bus.publish("system_events", AgentMessage(
            sender=self.name,
            topic="system_events",
            content=f"[{self.name}] Initiating/Resuming execution for: {task[:100]}..."
        ))

        for i in range(start_iteration, max_iterations):
            logger.info(f"[{self.name}] Iteration {i+1}/{max_iterations}")
            AGENT_ITERATIONS.labels(agent_name=self.name).inc()
            
            # 1. Reason and decide on next action (potentially tool calls)
            response: LLMResponse = await llm_client.chat(
                messages=self.message_history,
                tools=registry.to_openai_format()
            )
            
            # Add assistant's response to history
            assistant_msg = {"role": "assistant", "content": response.content}
            if response.tool_calls:
                assistant_msg["tool_calls"] = response.tool_calls
            self.message_history.append(assistant_msg)
            
            # Checkpoint after reasoning
            await self._save_state(task_id, i)

            # 2. If no tool calls, we are likely done
            if not response.tool_calls:
                if response.content:
                    await self.bus.publish("system_events", AgentMessage(
                        sender=self.name,
                        topic="system_events",
                        content=f"[{self.name}] Task completed autonomously."
                    ))
                    return response.content
                continue

            # 3. Execute Tool Calls
            for tool_call in response.tool_calls:
                tool_name = tool_call["function"]["name"]
                tool_args = json.loads(tool_call["function"]["arguments"])
                tool_id = tool_call["id"]

                await self.bus.publish("system_events", AgentMessage(
                    sender=self.name,
                    topic="system_events",
                    content=f"[{self.name}] Executing tool: {tool_name}({tool_args})"
                ))

                tool_result = await execute_tool(tool_name, tool_args)
                
                # Feed tool result back to the model
                self.message_history.append({
                    "role": "tool",
                    "tool_call_id": tool_id,
                    "name": tool_name,
                    "content": json.dumps(tool_result)
                })
                
            # Checkpoint after all tool executions in this iteration
            await self._save_state(task_id, i + 1)

        return "Max iterations reached without explicit completion."

class RealSwarmOrchestrator:
    """
    Heart of Brav OS. Orchestrates multiple AutonomousAgents.
    """
    def __init__(self, bus: AgentMessageBus = message_bus):
        self.bus = bus
        self.chief_logic = ChiefOrchestrator(bus=bus)
        self.agents: Dict[str, AutonomousAgent] = {}
        # Priority 4: Shared Memory Space
        self.shared_memory: Dict[str, Any] = {}
        
    def _get_agent(self, name: str, system_prompt: str) -> AutonomousAgent:
        if name not in self.agents:
            agent = AutonomousAgent(name, system_prompt, self.bus)
            agent.shared_memory = self.shared_memory # Inject shared memory
            self.agents[name] = agent
        return self.agents[name]

    async def listen_and_execute(self):
        """Main loop to listen for tasks and system events."""
        task_queue = await self.bus.subscribe("tasks")
        logger.info("RealSwarmOrchestrator listening for tasks...")
        
        while True:
            msg: AgentMessage = await task_queue.get()
            if msg.topic == "TaskAssigned":
                asyncio.create_task(self._handle_task(msg))
            task_queue.task_done()

    async def _run_structured_workflow(self, task_id: str, description: str, agent_name: str) -> str:
        """
        Priority 4 & 5 with Mandatory HITL for high-risk tasks.
        Enforces human approval for financial and outbound actions.
        """
        # --- HITL Security Gate ---
        high_risk_keywords = ["stripe", "payment", "bank", "send proposal", "upwork", "withdraw", "transfer", "email customer"]
        is_high_risk = any(k in description.lower() for k in high_risk_keywords)
        
        if is_high_risk:
            logger.warning(f"HIGH RISK TASK DETECTED: {task_id}. Waiting for manual approval...")
            # In a real system, this would send a Telegram message with buttons.
            # For now, we simulate a blocking approval check.
            approval_received = await self._wait_for_human_approval(task_id, description)
            if not approval_received:
                logger.error(f"Task {task_id} REJECTED by human.")
                return "Execution aborted: Task rejected by human supervisor for security reasons."

        available_agents = await self.chief_logic.get_available_agents()
        system_prompt = available_agents.get(agent_name, f"You are {agent_name}, a helpful agent.")
        
        draft_agent = self._get_agent(f"{agent_name}_Drafter", f"{system_prompt}\nYou are the Drafter. Write the initial solution.")
        review_agent = self._get_agent(f"{agent_name}_Reviewer", f"{system_prompt}\nYou are the Reviewer. Critique the drafted solution. Point out flaws, do NOT fix them.")
        revise_agent = self._get_agent(f"{agent_name}_Reviser", f"{system_prompt}\nYou are the Reviser. Fix the flaws pointed out by the Reviewer. Return the final corrected solution.")
        
        current_solution = ""
        max_rounds = 3
        task_start_time = time.time()
        round_num = 0
        
        for round_num in range(max_rounds):
            logger.info(f"[Structured Workflow] Round {round_num + 1} starting for task {task_id}")
            
            # 1. Draft or Revise
            if round_num == 0:
                prompt = f"Task: {description}\nShared Context: {json.dumps(self.shared_memory.get('context', {}))}"
                current_solution = await draft_agent.run_to_completion(f"{task_id}_draft", prompt)
            else:
                prompt = f"Original Task: {description}\nReviewer Critique: {critique}\nCurrent Solution: {current_solution}\nFix the solution."
                current_solution = await revise_agent.run_to_completion(f"{task_id}_revise_{round_num}", prompt)
                
            # Write to Shared Memory
            self.shared_memory[f"solution_{task_id}"] = current_solution
            
            # 2. Review
            review_prompt = f"Task: {description}\nProposed Solution:\n{current_solution}\nProvide a strict critique pointing out bugs or missed requirements."
            critique = await review_agent.run_to_completion(f"{task_id}_review_{round_num}", review_prompt)
            
            # 3. Validate
            validation = await self._validate_with_chief(description, current_solution, critique)
            score = validation.get("score", 0)
            
            logger.info(f"[Structured Workflow] Validation Score: {score}/100. Strengths: {validation.get('strengths', [])}, Weaknesses: {validation.get('weaknesses', [])}")
            
            if score >= 80 or validation.get("pass", False):
                logger.info(f"[Structured Workflow] Validation passed in round {round_num + 1} with score {score}.")
                break
                
            logger.warning(f"[Structured Workflow] Validation failed (Score: {score}) in round {round_num + 1}. Revising...")
            
        else:
            logger.error(f"[Structured Workflow] Task {task_id} failed to pass validation after {max_rounds} rounds.")
            await DeadLetterQueue.add(task_id, "Workflow", description, "Failed max debate rounds.")
            
        # Priority 5: Log task cost
        total_duration = time.time() - task_start_time
        # Simplified token estimation
        estimated_prompt_tokens = (len(description) // 4) * (round_num + 1) * 3
        estimated_comp_tokens = (len(current_solution) // 4) * (round_num + 1) * 2
        await TaskCostTracker.log_cost(task_id, agent_name, total_duration, estimated_prompt_tokens, estimated_comp_tokens)
        
        return current_solution

    async def _wait_for_human_approval(self, task_id: str, description: str) -> bool:
        """
        Pauses execution and waits for human approval via the Message Bus.
        """
        await self.bus.publish("system_events", AgentMessage(
            sender="System",
            topic="ApprovalRequired",
            content={
                "task_id": task_id,
                "description": description,
                "warning": "This is a HIGH RISK task. Please approve or reject."
            }
        ))
        
        # Subscribe to approval topic
        approval_queue = await self.bus.subscribe(f"approvals/{task_id}")
        logger.info(f"Waiting for human approval for task {task_id}...")
        
        try:
            # Wait for 10 minutes max for human to react
            msg = await asyncio.wait_for(approval_queue.get(), timeout=600)
            status = msg.content.get("status", "rejected")
            return status.lower() == "approved"
        except asyncio.TimeoutError:
            logger.error(f"Approval for task {task_id} timed out.")
            return False
        finally:
            await self.bus.unsubscribe(f"approvals/{task_id}", approval_queue)

    async def _handle_task(self, msg: AgentMessage):
        task_data = msg.content
        agent_name = msg.receiver
        description = task_data.get("description", "")
        task_id = task_data.get("id", f"task_{int(time.time())}")
        
        # Use the Priority 4 structured workflow
        final_result = await self._run_structured_workflow(task_id, description, agent_name)
        
        if "Dead Letter Queue" in final_result:
            logger.warning(f"Task {task_id} was sent to DLQ.")
            return
            
        await self.bus.publish("system_events", AgentMessage(
            sender="Chief",
            topic="TaskCompleted",
            content={"task_id": task_id, "result": final_result}
        ))
        
        # Clean up state file on success
        def _cleanup():
            state_file = AGENT_RUNS_DIR / f"{task_id}.json"
            if state_file.exists():
                try:
                    os.remove(state_file)
                    logger.info(f"Cleaned up state file for completed task {task_id}.")
                except Exception as e:
                    logger.error(f"Failed to cleanup state for task {task_id}: {e}")
        await asyncio.to_thread(_cleanup)

    async def _validate_with_chief(self, task: str, result: str, critique: str = "") -> dict:
        """
        Priority 5: Output Quality Scoring.
        Final validation step. Evaluates solution and returns a score breakdown.
        """
        logger.info("Chief validating result for quality scoring...")
        system_prompt = """You are the Chief Validator. Evaluate the proposed solution based on the task requirements and the critique.
Respond STRICTLY with a JSON object containing:
- "score": integer (0-100) representing overall quality.
- "strengths": list of strings (what was done well).
- "weaknesses": list of strings (what needs improvement).
- "pass": boolean (true if score >= 80)."""
        user_prompt = f"Task: {task}\n\nResult:\n{result}\n\nReviewer Critique:\n{critique}"
        
        response = await llm_client.generate_completion(system_prompt, user_prompt, response_format={"type": "json_object"})
        try:
            return json.loads(response)
        except json.JSONDecodeError:
            logger.error("Failed to parse validation JSON.")
            return {"score": 0, "strengths": [], "weaknesses": ["Failed to parse validation output."], "pass": False}

async def start_swarm():
    """Entry point for the real autonomous swarm."""
    orchestrator = RealSwarmOrchestrator()
    await orchestrator.listen_and_execute()
