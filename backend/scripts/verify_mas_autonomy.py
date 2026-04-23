import asyncio
import logging
import uuid
import sys
import os

# Add backend to path
sys.path.append(os.getcwd())

from app.agents.orchestrator import orchestrator_agent
from app.agents.war_room import war_room_agent
from app.core.event_bus import event_bus
from app.core.agent_registry import agent_registry

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

async def test_mas_autonomy():
    logger.info("🚀 Starting Multi-Agent Autonomy Verification")
    
    # 0. Initialize DB Tables
    from app.database import engine
    from app.models import Base
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    logger.info("DB Tables created.")
    
    # 1. Initialize services
    loop_task = asyncio.create_task(event_bus.start_processing())
    await orchestrator_agent.start()
    await war_room_agent.start()
    
    # 2. Trigger a complex goal
    goal = "Analyze the competitive landscape of personal AI assistants and draft a blog post summary."
    logger.info(f"Target Goal: {goal}")
    
    master_tid = await orchestrator_agent.orchestrate_goal(goal)
    logger.info(f"Master Task Created: {master_tid}")
    
    # 3. Wait for progress (simulated)
    logger.info("Waiting for agents to communicate...")
    await asyncio.sleep(15)
    
    # 4. Request a meeting to check communication
    logger.info("Requesting a team meeting...")
    await orchestrator_agent.request_meeting(
        topic="Consolidating findings on AI assistants",
        participants=["research_collector", "drafter"]
    )
    
    await asyncio.sleep(15)
    
    # 5. Shut down
    event_bus.stop()
    loop_task.cancel()
    
    logger.info("✅ Verification script finished. Check 'agent_tasks' and 'agent_messages' tables for proof of life.")

if __name__ == "__main__":
    asyncio.run(test_mas_autonomy())
