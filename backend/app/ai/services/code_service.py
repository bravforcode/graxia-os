"""
Code Service - Handles code generation, fixing, and explanation
"""

import re

from ..client import AIClient
from ..models import (
    ChatMessage,
    CodeFixRequest,
    CodeFixResponse,
    CodeRequest,
    CodeResponse,
    MessageRole,
)
from .vault_service import VaultService


class CodeService:
    """Service for code-related AI operations"""

    def __init__(self, ai_client: AIClient):
        self.ai_client = ai_client
        self.vault_service = VaultService()

    async def generate(self, request: CodeRequest) -> CodeResponse:
        """Generate code with AI"""

        # Load relevant skills for this language
        skills = await self.vault_service.search_skills(
            f"{request.language} best practices", limit=3
        )

        # Build system prompt
        system_prompt = f"""You are an expert {request.language} developer.
Write clean, production-ready code with proper error handling.

Requirements:
- Include type hints where appropriate
- Add docstrings for functions/classes
- Handle edge cases and errors
- Follow language-specific best practices
- Include example usage in comments"""

        if request.style_guide:
            system_prompt += f"\n- Follow style guide: {request.style_guide}"

        # Build user prompt
        user_prompt = f"Task: {request.prompt}\n\n"

        if request.context:
            user_prompt += f"Context:\n{request.context}\n\n"

        if request.existing_code:
            user_prompt += (
                f"Existing code to modify:\n```{request.language}\n{request.existing_code}\n```\n\n"
            )

        user_prompt += f"Please generate {request.language} code."

        # Add skills context
        if skills and skills.get("results"):
            user_prompt += "\n\nRelevant best practices:\n"
            for skill in skills["results"][:2]:
                user_prompt += f"- {skill['name']}\n"

        messages = [
            ChatMessage(role=MessageRole.SYSTEM, content=system_prompt),
            ChatMessage(role=MessageRole.USER, content=user_prompt),
        ]

        # Generate code
        result = await self.ai_client.chat(
            messages=messages,
            task_type="code_generation",
            temperature=0.3,  # Lower temperature for code
        )

        # Extract code from response
        generated_text = result["content"]
        code = self._extract_code_block(generated_text, request.language)

        # Extract explanation
        explanation = self._extract_explanation(generated_text)

        # Generate tests if requested
        tests = None
        if request.include_tests:
            tests = await self._generate_tests(code, request.language)

        # Generate docs if requested
        documentation = None
        if request.include_docs:
            documentation = await self._generate_docs(code, request.language)

        return CodeResponse(
            code=code or generated_text,
            language=request.language,
            explanation=explanation,
            tests=tests,
            documentation=documentation,
            model_used=result.get("model_used", "unknown"),
            suggestions=self._extract_suggestions(generated_text),
        )

    async def fix(self, request: CodeFixRequest) -> CodeFixResponse:
        """Fix code issues with AI"""

        system_prompt = f"""You are an expert {request.language} debugger.
Analyze the provided code and error, then provide a fixed version.

Respond in this format:
1. Analysis of the issue
2. Fixed code in a code block
3. Explanation of changes made"""

        user_prompt = f"Code with issues:\n```{request.language}\n{request.code}\n```\n\n"

        if request.error_message:
            user_prompt += f"Error message:\n{request.error_message}\n\n"

        if request.error_log:
            user_prompt += f"Error log:\n```\n{request.error_log}\n```\n\n"

        if request.context:
            user_prompt += f"Additional context:\n{request.context}\n\n"

        messages = [
            ChatMessage(role=MessageRole.SYSTEM, content=system_prompt),
            ChatMessage(role=MessageRole.USER, content=user_prompt),
        ]

        result = await self.ai_client.chat(
            messages=messages, task_type="code_generation", temperature=0.3
        )

        response_text = result["content"]

        # Extract fixed code
        fixed_code = self._extract_code_block(response_text, request.language)

        # Extract explanation and changes
        explanation = self._extract_explanation(response_text)
        changes_made = self._extract_changes(response_text)

        # Calculate confidence (simplified)
        confidence = 0.8 if fixed_code and len(changes_made) > 0 else 0.5

        return CodeFixResponse(
            original_code=request.code,
            fixed_code=fixed_code or request.code,
            changes_made=changes_made if changes_made else ["Applied automatic fixes"],
            explanation=explanation,
            confidence=confidence,
            tests_suggested=None,  # Could generate tests
            auto_applied=request.auto_apply and confidence > 0.8,
        )

    async def explain(self, code: str, language: str | None = None) -> str:
        """Explain what code does"""

        lang_info = f" ({language})" if language else ""

        messages = [
            ChatMessage(
                role=MessageRole.SYSTEM,
                content="You are a code documentation expert. Explain code clearly and concisely.",
            ),
            ChatMessage(
                role=MessageRole.USER,
                content=f"Explain what this{lang_info} code does:\n\n```{language or ''}\n{code}\n```",
            ),
        ]

        result = await self.ai_client.chat(messages=messages, temperature=0.5)

        return result["content"]

    async def _generate_tests(self, code: str, language: str) -> str | None:
        """Generate tests for code"""

        test_frameworks = {"python": "pytest", "typescript": "jest", "javascript": "jest"}

        framework = test_frameworks.get(language, "unit tests")

        messages = [
            ChatMessage(
                role=MessageRole.SYSTEM,
                content=f"Generate {framework} tests for the provided code.",
            ),
            ChatMessage(
                role=MessageRole.USER, content=f"Generate tests for:\n\n```{language}\n{code}\n```"
            ),
        ]

        result = await self.ai_client.chat(
            messages=messages, task_type="code_generation", temperature=0.3
        )

        return self._extract_code_block(result["content"], language)

    async def _generate_docs(self, code: str, language: str) -> str | None:
        """Generate documentation for code"""

        messages = [
            ChatMessage(
                role=MessageRole.SYSTEM,
                content="Generate markdown documentation for the provided code.",
            ),
            ChatMessage(
                role=MessageRole.USER, content=f"Document this code:\n\n```{language}\n{code}\n```"
            ),
        ]

        result = await self.ai_client.chat(messages=messages, temperature=0.5)

        return result["content"]

    def _extract_code_block(self, text: str, language: str) -> str | None:
        """Extract code block from markdown"""

        # Try to extract code block
        pattern = rf"```{language}\n(.*?)```"
        match = re.search(pattern, text, re.DOTALL)

        if match:
            return match.group(1).strip()

        # Try generic code block
        pattern = r"```\n?(.*?)```"
        match = re.search(pattern, text, re.DOTALL)

        if match:
            return match.group(1).strip()

        return None

    def _extract_explanation(self, text: str) -> str:
        """Extract explanation from response"""

        # Remove code blocks
        cleaned = re.sub(r"```.*?```", "", text, flags=re.DOTALL)

        # Clean up
        cleaned = cleaned.strip()

        # Limit length
        if len(cleaned) > 1000:
            cleaned = cleaned[:1000] + "..."

        return cleaned

    def _extract_changes(self, text: str) -> list[str]:
        """Extract list of changes from response"""

        changes = []

        # Look for bullet points or numbered lists
        lines = text.split("\n")
        for line in lines:
            # Match bullet points or numbered items
            if re.match(r"^[\s]*[-*•]\s+", line) or re.match(r"^[\s]*\d+[.\)]\s+", line):
                change = re.sub(r"^[\s]*[-*•\d.\)]\s+", "", line).strip()
                if change:
                    changes.append(change)

        return changes

    def _extract_suggestions(self, text: str) -> list[str]:
        """Extract suggestions from response"""

        suggestions = []

        # Look for sections like "Suggestions", "Recommendations", "Notes"
        lines = text.split("\n")
        in_suggestions = False

        for line in lines:
            lower_line = line.lower()

            if any(
                word in lower_line
                for word in ["suggestion", "recommendation", "note", "tip", "improvement"]
            ):
                in_suggestions = True
                continue

            if in_suggestions:
                if re.match(r"^[\s]*[-*•]\s+", line):
                    suggestion = re.sub(r"^[\s]*[-*•]\s+", "", line).strip()
                    if suggestion and len(suggestion) > 10:
                        suggestions.append(suggestion)

        return suggestions[:5]  # Limit to 5 suggestions
