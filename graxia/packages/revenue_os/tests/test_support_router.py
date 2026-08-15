import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from ..agents.support import SupportAgent
from ..schemas import SupportChatRequest


@pytest.mark.asyncio
async def test_handle_message_direct(db_session: AsyncSession, sample_order_data):
    req = SupportChatRequest(message="where is my order?", customer_email="nobody@example.com")
    reply = await SupportAgent.handle_message(db_session, req.message, req.customer_email)
    assert reply.intent.value in {"wismo", "other"}
