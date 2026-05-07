from datetime import timedelta
from temporalio import workflow
from typing import Any, Dict

# Import BWCP schemas
import sys
import os
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '../../')))
from packages.bwcp_protocol.python.envelope import MessageEnvelope

@workflow.defn
class MissionLifecycleWorkflow:
    @workflow.run
    async def run(self, mission_data: Dict[str, Any]) -> Dict[str, Any]:
        workflow.logger.info(f"🚀 Starting Mission: {mission_data.get('mission_id')}")
        
        # 1. Planning Phase (Trigger LangGraph)
        # This is where we would call an activity that runs the LangGraph Agent Mesh
        plan = await workflow.execute_activity(
            "run_mission_planning",
            mission_data,
            start_to_close_timeout=timedelta(minutes=10)
        )
        
        # 2. Execution Phase
        # Loop through tasks and track progress
        results = []
        for task in plan.get("tasks", []):
            result = await workflow.execute_activity(
                "execute_agent_task",
                task,
                start_to_close_timeout=timedelta(hours=1)
            )
            results.append(result)
            
        # 3. Completion
        return {
            "status": "COMPLETED",
            "mission_id": mission_data.get("mission_id"),
            "summary": "Mission successfully executed via BravOS Durable Workflow."
        }
