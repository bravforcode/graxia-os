import uuid
from datetime import datetime, timezone, timedelta
from typing import Any, List
from pydantic import BaseModel, Field

from graxia.packages.bravos_core.python.agent import BaseBravOSAgent
from graxia.packages.bwcp_protocol.models import BWCPMessage, BWCPMessageType, BWCPPriority

class Opportunity(BaseModel):
    """Strict Pydantic V2 model for Opportunity (e.g., Hackathons, Grants)"""
    opportunity_id: str = Field(default_factory=lambda: str(uuid.uuid4()), description="Unique ID for the opportunity")
    source: str = Field(..., description="Source of the opportunity (e.g., Devpost, NECTEC)")
    title: str = Field(..., description="Title or name of the opportunity")
    url: str = Field(..., description="Link to apply or learn more")
    deadline: datetime = Field(..., description="Application or submission deadline")
    fit_score: float = Field(..., ge=0.0, le=100.0, description="Calculated fit score from 0 to 100")
    description: str = Field(..., description="Brief description")

class ResearchAgent(BaseBravOSAgent):
    """
    Research Agent responsible for finding and scoring hackathons or funding opportunities.
    """
    def __init__(self):
        super().__init__(agent_id="research_agent", agent_type="Research")

    async def execute_task(self, message: BWCPMessage) -> BWCPMessage:
        """
        Simulate finding and scoring hackathons (e.g., from Devpost, NECTEC).
        """
        now = datetime.now(timezone.utc)
        
        # Simulate finding opportunities
        opportunities: List[Opportunity] = [
            Opportunity(
                source="Devpost",
                title="Global AI Hackathon 2025",
                url="https://devpost.com/hackathons/global-ai",
                deadline=now + timedelta(days=30),
                fit_score=95.5,
                description="Build innovative AI agents to solve real-world problems."
            ),
            Opportunity(
                source="NECTEC",
                title="National Tech Innovation Grant",
                url="https://nectec.or.th/grants/tech-innovation",
                deadline=now + timedelta(days=60),
                fit_score=88.0,
                description="Funding for local startups building deep tech solutions."
            ),
            Opportunity(
                source="Devpost",
                title="Web3 & Blockchain Builder Challenge",
                url="https://devpost.com/hackathons/web3-builder",
                deadline=now + timedelta(days=15),
                fit_score=45.0,
                description="Develop decentralized applications on Ethereum."
            )
        ]

        # Filter opportunities based on a threshold (e.g., fit_score > 50)
        high_fit_opportunities = [opp for opp in opportunities if opp.fit_score > 50.0]

        # Prepare payload
        payload = {
            "total_found": len(opportunities),
            "high_fit_found": len(high_fit_opportunities),
            "opportunities": [opp.model_dump() for opp in high_fit_opportunities],
            "summary": f"Scored {len(opportunities)} opportunities. Found {len(high_fit_opportunities)} with high fit score."
        }

        # Return a valid BWCPMessage TASK_RESULT
        return BWCPMessage(
            message_id=str(uuid.uuid4()),
            sender_agent=self.agent_id,
            receiver_agent=message.sender_agent,
            mission_id=message.mission_id,
            task_id=message.task_id,
            type=BWCPMessageType.TASK_RESULT,
            priority=BWCPPriority.NORMAL,
            payload=payload
        )
