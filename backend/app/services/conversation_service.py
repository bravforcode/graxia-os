"""
Conversation Service — Feature 19
Service for managing conversation sessions and context
"""

from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import and_, desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.logger import get_logger
from app.models.skill_conversation import (
    ConversationMemoryExtract,
    ConversationMessage,
    ConversationSession,
    SkillContextPreference,
)

logger = get_logger(__name__)


class ConversationService:
    """
    Service for conversation management and context.

    Feature 19: Conversation Memory Service
    """

    def __init__(self, session: AsyncSession):
        self.session = session

    async def create_session(
        self,
        title: str | None = None,
        description: str | None = None,
        agent_id: UUID | None = None,
        user_id: UUID | None = None,
        primary_skill_id: UUID | None = None,
        max_context_messages: int = 20,
        context_window_tokens: int = 4000,
    ) -> ConversationSession:
        """Create a new conversation session."""

        session_key = f"conv_{datetime.utcnow().strftime('%Y%m%d%H%M%S')}_{str(uuid4())[:8]}"

        session = ConversationSession(
            id=uuid4(),
            session_key=session_key,
            title=title,
            description=description,
            agent_id=agent_id,
            user_id=user_id,
            primary_skill_id=primary_skill_id,
            max_context_messages=max_context_messages,
            context_window_tokens=context_window_tokens,
            status="active",
        )

        self.session.add(session)
        await self.session.commit()

        logger.info(f"Conversation session created: {session_key}")
        return session

    async def add_message(
        self,
        session_id: UUID,
        content: str,
        sender_type: str,
        sender_id: UUID | None = None,
        content_type: str = "text",
        invoked_skill_id: UUID | None = None,
        skill_input: dict | None = None,
        skill_output: dict | None = None,
        input_tokens: int | None = None,
        output_tokens: int | None = None,
        generation_duration_ms: int | None = None,
    ) -> ConversationMessage:
        """Add a message to a conversation."""

        # Get next message number
        result = await self.session.execute(
            select(ConversationMessage)
            .where(ConversationMessage.session_id == session_id)
            .order_by(desc(ConversationMessage.message_number))
            .limit(1)
        )
        last_msg = result.scalar_one_or_none()
        next_number = (last_msg.message_number + 1) if last_msg else 1

        message = ConversationMessage(
            id=uuid4(),
            session_id=session_id,
            message_number=next_number,
            sender_type=sender_type,
            sender_id=sender_id,
            content=content,
            content_type=content_type,
            invoked_skill_id=invoked_skill_id,
            skill_input=skill_input,
            skill_output=skill_output,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            generation_duration_ms=generation_duration_ms,
        )

        self.session.add(message)

        # Update session stats
        session = await self.session.get(ConversationSession, session_id)
        if session:
            session.message_count = next_number
            session.last_message_at = datetime.utcnow()

        await self.session.commit()
        return message

    async def get_session_messages(
        self,
        session_id: UUID,
        limit: int = 100,
        include_context_info: bool = True,
    ) -> list[ConversationMessage]:
        """Get messages from a session."""

        result = await self.session.execute(
            select(ConversationMessage)
            .where(ConversationMessage.session_id == session_id)
            .order_by(ConversationMessage.message_number)
            .limit(limit)
        )
        return list(result.scalars().all())

    async def get_context_window(
        self,
        session_id: UUID,
        max_messages: int = 20,
        max_tokens: int = 4000,
    ) -> list[ConversationMessage]:
        """Get the most recent messages for context window."""

        result = await self.session.execute(
            select(ConversationMessage)
            .where(ConversationMessage.session_id == session_id)
            .order_by(desc(ConversationMessage.message_number))
            .limit(max_messages)
        )
        messages = list(result.scalars().all())
        return list(reversed(messages))  # Return in chronological order

    async def extract_memory(
        self,
        session_id: UUID,
        fact_type: str,
        fact_key: str,
        fact_value: str,
        source_message_ids: list[UUID],
        extraction_confidence: float = 0.8,
        expires_at: datetime | None = None,
    ) -> ConversationMemoryExtract:
        """Extract and store a fact from conversation."""

        extract = ConversationMemoryExtract(
            id=uuid4(),
            session_id=session_id,
            fact_type=fact_type,
            fact_key=fact_key,
            fact_value=fact_value,
            source_message_ids=source_message_ids,
            extraction_confidence=extraction_confidence,
            expires_at=expires_at,
        )

        self.session.add(extract)
        await self.session.commit()

        return extract

    async def get_memories(
        self,
        session_id: UUID,
        fact_type: str | None = None,
        active_only: bool = True,
    ) -> list[ConversationMemoryExtract]:
        """Get extracted memories for a session."""

        query = select(ConversationMemoryExtract).where(
            ConversationMemoryExtract.session_id == session_id
        )

        if fact_type:
            query = query.where(ConversationMemoryExtract.fact_type == fact_type)
        if active_only:
            query = query.where(ConversationMemoryExtract.is_active)

        result = await self.session.execute(query)
        return list(result.scalars().all())

    async def set_context_preference(
        self,
        agent_id: UUID,
        skill_id: UUID | None = None,
        default_context_variables: dict | None = None,
        preferred_conversation_style: str = "professional",
        auto_invoke_on_keywords: list[str] | None = None,
        require_confirmation: bool = True,
    ) -> SkillContextPreference:
        """Set context preferences for an agent."""

        # Check for existing preference
        result = await self.session.execute(
            select(SkillContextPreference).where(
                and_(
                    SkillContextPreference.agent_id == agent_id,
                    SkillContextPreference.skill_id == skill_id,
                )
            )
        )
        existing = result.scalar_one_or_none()

        if existing:
            if default_context_variables:
                existing.default_context_variables = default_context_variables
            existing.preferred_conversation_style = preferred_conversation_style
            if auto_invoke_on_keywords:
                existing.auto_invoke_on_keywords = auto_invoke_on_keywords
            existing.require_confirmation = require_confirmation
            await self.session.commit()
            return existing

        preference = SkillContextPreference(
            id=uuid4(),
            agent_id=agent_id,
            skill_id=skill_id,
            default_context_variables=default_context_variables or {},
            preferred_conversation_style=preferred_conversation_style,
            auto_invoke_on_keywords=auto_invoke_on_keywords or [],
            require_confirmation=require_confirmation,
        )

        self.session.add(preference)
        await self.session.commit()

        return preference

    async def archive_session(self, session_id: UUID) -> ConversationSession:
        """Archive a conversation session."""

        session = await self.session.get(ConversationSession, session_id)
        if not session:
            raise ValueError(f"Session not found: {session_id}")

        session.status = "archived"
        session.archived_at = datetime.utcnow()

        await self.session.commit()
        return session
