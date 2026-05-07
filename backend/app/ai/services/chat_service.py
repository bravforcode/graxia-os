"""
Chat Service - Handles chat conversations with AI
"""

from collections.abc import AsyncGenerator

from ..client import AIClient
from ..models import ChatMessage, ChatRequest, ChatResponse, MessageRole
from .vault_service import VaultService


class ChatService:
    """Service for handling chat conversations"""

    def __init__(self, ai_client: AIClient):
        self.ai_client = ai_client
        self.vault_service = VaultService()

    async def chat(self, request: ChatRequest) -> ChatResponse:
        """Process chat request with optional vault context"""

        messages = request.messages.copy()
        context_references = []

        # Enhance with vault context if enabled
        if request.use_vault and len(messages) > 0:
            last_message = messages[-1]
            if last_message.role == MessageRole.USER:
                # Search vault for relevant context
                vault_results = await self.vault_service.search(last_message.content, limit=3)

                if vault_results:
                    context_references = [r["path"] for r in vault_results]

                    # Build context message
                    context_parts = ["Relevant information from vault:", ""]

                    for result in vault_results:
                        context_parts.append(f"From [[{result['path']}]]:")
                        if result.get("snippet"):
                            context_parts.append(result["snippet"][:200])
                        context_parts.append("")

                    # Insert context as system message
                    context_message = ChatMessage(
                        role=MessageRole.SYSTEM, content="\n".join(context_parts)
                    )

                    # Insert before last user message
                    messages.insert(-1, context_message)

        # Enhance with skills if enabled
        if request.use_skills and len(messages) > 0:
            last_message = messages[-1]
            if last_message.role == MessageRole.USER:
                # Search for relevant skills
                skills = await self.vault_service.search_skills_for_task(last_message.content)

                if skills:
                    skills_context = ["Relevant skills available:", ""]

                    for skill in skills[:3]:
                        skills_context.append(
                            f"- {skill['name']}: {skill.get('description', '')[:100]}"
                        )

                    skills_message = ChatMessage(
                        role=MessageRole.SYSTEM, content="\n".join(skills_context)
                    )

                    messages.insert(-1, skills_message)

        # Determine task type for model routing
        task_type = self._determine_task_type(messages)

        # Send to AI
        result = await self.ai_client.chat(
            messages=messages,
            model=request.model,
            temperature=request.temperature,
            max_tokens=request.max_tokens,
            stream=request.stream,
            task_type=task_type,
        )

        return ChatResponse(
            message=ChatMessage(role=MessageRole.ASSISTANT, content=result["content"]),
            model_used=result.get("model_used", "unknown"),
            tokens_used=result.get("tokens_used"),
            context_references=context_references if context_references else None,
        )

    async def stream_chat(self, request: ChatRequest) -> AsyncGenerator[str, None]:
        """Stream chat response"""
        response = await self.chat(request)
        # For now, just yield the full response
        # Can be enhanced with actual streaming
        yield response.message.content

    def _determine_task_type(self, messages: list[ChatMessage]) -> str:
        """Determine task type from messages for model routing"""

        # Get last user message
        user_messages = [m for m in messages if m.role == MessageRole.USER]
        if not user_messages:
            return "chat"

        last_message = user_messages[-1].content.lower()

        # Code-related keywords
        code_keywords = [
            "code",
            "function",
            "class",
            "def",
            "import",
            "return",
            "error",
            "bug",
            "fix",
            "debug",
            "syntax",
            "refactor",
            "implement",
            "write code",
            "generate code",
            "script",
            "python",
            "javascript",
            "typescript",
            "sql",
            "bash",
        ]

        # Analysis keywords
        analysis_keywords = [
            "analyze",
            "explain",
            "review",
            "assess",
            "evaluate",
            "compare",
            "contrast",
            "pros and cons",
            "advantages",
        ]

        # Check for code
        if any(kw in last_message for kw in code_keywords):
            return "code_generation"

        # Check for analysis
        if any(kw in last_message for kw in analysis_keywords):
            return "analysis"

        # Default to chat
        return "chat"
