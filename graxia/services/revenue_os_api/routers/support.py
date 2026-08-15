"""Customer support chat endpoint (public - identity verified inside the agent)."""
from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from ....packages.revenue_os.agents.support import SupportAgent
from ....packages.revenue_os.db import get_db
from ....packages.revenue_os.schemas import SupportChatRequest, SupportChatResponse

router = APIRouter(prefix="/support")


@router.post("/chat", response_model=SupportChatResponse)
async def chat(body: SupportChatRequest, db: AsyncSession = Depends(get_db)) -> SupportChatResponse:
    reply = await SupportAgent.handle_message(
        db, body.message, body.customer_email, verification_code=body.verification_code
    )
    return SupportChatResponse(
        intent=reply.intent.value,
        reply=reply.text,
        action_taken=reply.action_taken,
    )
