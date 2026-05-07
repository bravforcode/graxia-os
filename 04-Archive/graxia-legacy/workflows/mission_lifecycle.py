import asyncio
import logging
from datetime import timedelta
from typing import Any, Dict, Optional

from temporalio import activity, workflow
from temporalio.common import RetryPolicy

# Configure basic logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Try to import audit service, fallback to standard logging if unavailable
try:
    from graxia.packages.logging.python.audit import audit_log
except ImportError:
    def audit_log(event_type: str, mission_id: str, details: str):
        logger.info(f"AUDIT [{event_type}] Mission {mission_id}: {details}")

# --- Activities ---

@activity.defn
async def verify_funding(payload: Dict[str, Any]) -> bool:
    """Stub activity to verify mission funding."""
    mission_id = payload.get("mission_id", "unknown_mission")
    audit_log("ACTIVITY_START", mission_id, "Verifying funding.")
    # Simulate network call or database query
    await asyncio.sleep(1)
    audit_log("ACTIVITY_COMPLETE", mission_id, "Funding verified successfully.")
    return True

@activity.defn
async def trigger_cos_agent(payload: Dict[str, Any]) -> Dict[str, Any]:
    """Stub activity to trigger the Chief of Staff agent and await its response."""
    mission_id = payload.get("mission_id", "unknown_mission")
    audit_log("ACTIVITY_START", mission_id, "Triggering COS agent.")
    # Simulate an agent doing complex work
    await asyncio.sleep(2)
    audit_log("ACTIVITY_COMPLETE", mission_id, "COS agent completed task.")
    return {"status": "success", "agent_result": "All mission objectives met."}

@activity.defn
async def finalize_mission(payload: Dict[str, Any]) -> bool:
    """Stub activity to finalize the mission and clean up resources."""
    mission_id = payload.get("mission_id", "unknown_mission")
    audit_log("ACTIVITY_START", mission_id, "Finalizing mission.")
    # Simulate cleanup
    await asyncio.sleep(1)
    audit_log("ACTIVITY_COMPLETE", mission_id, "Mission finalized.")
    return True

# --- Workflow ---

@workflow.defn
class MissionLifecycleWorkflow:
    """Orchestrates the lifecycle of a mission."""

    @workflow.run
    async def run(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        """
        Executes the mission lifecycle given a BWCPMessage-like payload.
        """
        mission_id = payload.get("mission_id", "unknown_mission")
        
        # Log mission start durably
        workflow.logger.info(f"Starting MissionLifecycleWorkflow for mission {mission_id}")
        audit_log("MISSION_START", mission_id, f"Workflow started with payload: {payload}")
        
        # Define a robust retry policy for all activities
        default_retry_policy = RetryPolicy(
            initial_interval=timedelta(seconds=1),
            backoff_coefficient=2.0,
            maximum_interval=timedelta(minutes=1),
            maximum_attempts=5,
            non_retryable_error_types=["ValueError", "TypeError"] # Examples of fatal errors
        )

        try:
            # 1. Verify Funding
            is_funded = await workflow.execute_activity(
                verify_funding,
                payload,
                start_to_close_timeout=timedelta(minutes=2),
                retry_policy=default_retry_policy,
            )
            
            if not is_funded:
                audit_log("MISSION_SUSPEND", mission_id, "Mission suspended due to insufficient funding.")
                return {"status": "suspended", "reason": "insufficient_funding", "mission_id": mission_id}

            # 2. Trigger Chief of Staff Agent
            agent_result = await workflow.execute_activity(
                trigger_cos_agent,
                payload,
                # Start to close timeout could be long for an agent (e.g., hours or days)
                start_to_close_timeout=timedelta(hours=1),
                retry_policy=default_retry_policy,
            )

            # 3. Finalize Mission
            await workflow.execute_activity(
                finalize_mission,
                payload,
                start_to_close_timeout=timedelta(minutes=2),
                retry_policy=default_retry_policy,
            )

            # Log durable completion
            audit_log("MISSION_COMPLETE", mission_id, "Workflow completed successfully.")
            return {
                "status": "completed",
                "mission_id": mission_id,
                "result": agent_result
            }

        except Exception as e:
            # Durably log failures and re-raise so Temporal knows it failed
            error_msg = f"Workflow failed with error: {str(e)}"
            workflow.logger.error(error_msg)
            audit_log("MISSION_FAILED", mission_id, error_msg)
            raise
