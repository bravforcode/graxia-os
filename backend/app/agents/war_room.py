import logging
from typing import Any
import hashlib

from app.agents.base import BaseAgent
from app.core.llm import llm_client
from app.core.model_router import route_task
from app.core.event_bus import event_bus
from app.database import AsyncSessionLocal
from app.models.orchestration import AgentMessage

logger = logging.getLogger(__name__)

class WarRoomAgent(BaseAgent):
    """
    Facilitates multi-agent meetings and discussions.
    """
    name = "war_room"

    async def start(self):
        event_bus.subscribe("agent.meeting.requested", self.on_meeting_requested)
        logger.info("WarRoom Agent online. Ready to host meetings.")

    async def on_meeting_requested(self, payload: dict[str, Any]):
        topic = payload.get("topic")
        participants = payload.get("participants", [])
        requested_by = payload.get("requested_by")
        
        session_id = hashlib.md5(f"{topic}-{requested_by}".encode()).hexdigest()
        
        logger.info(f"WarRoom initiating meeting '{topic}'. Participants: {participants}")
        
        await self._broadcast(session_id, self.name, f"Meeting started on topic: {topic}. Initiated by {requested_by}.")
        
        # Simulate a round-robin discussion
        chat_history = []
        chat_history.append(f"{self.name}: Meeting started on topic: {topic}.")
        
        for turn in range(2): # 2 rounds of discussion
            for agent_name in participants:
                try:
                    routing = route_task("analysis")
                    system_prompt = f"You are the {agent_name} agent in a war room meeting. Respond to the discussion concisely."
                    user_prompt = "Recent discussion:\n" + "\n".join(chat_history)
                    
                    response = await llm_client.complete(
                        system=system_prompt,
                        user=user_prompt,
                        model=routing.model,
                        task_class="analysis"
                    )
                    
                    if response:
                        await self._broadcast(session_id, agent_name, response)
                        chat_history.append(f"{agent_name}: {response}")
                        
                except Exception as e:
                    logger.error(f"Meeting error for {agent_name}: {e}")

        await self._broadcast(session_id, self.name, "Meeting adjourned. Saving transcript.")
        
        # Emit a meeting concluded event with the transcript so the orchestrator or requestor can act on it
        await event_bus.emit("agent.meeting.concluded", {
            "session_id": session_id,
            "topic": topic,
            "transcript": "\n".join(chat_history)
        })

    async def _broadcast(self, session_id: str, sender: str, content: str):
        async with AsyncSessionLocal() as db:
            msg = AgentMessage(
                session_id=session_id,
                sender=sender,
                content=content
            )
            db.add(msg)
            await db.commit()
            
war_room_agent = WarRoomAgent()
