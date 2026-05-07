"""
AI Usage Logger — Centralized logging for AI requests with cost tracking.
Integrates with OpenClaw and other LLM providers.
"""

import time
from decimal import Decimal
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.models.usage_log import UsageLog


class UsageLogger:
    """Centralized usage and cost tracking for all AI operations."""
    
    def __init__(self, db: AsyncSession):
        self.db = db
    
    async def log_ai_request(
        self,
        model_name: str,
        tokens_input: int,
        tokens_output: int,
        execution_time_ms: int,
        cost_usd: float,
        organization_id: str,
        user_id: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> UsageLog:
        """Log an AI request with full cost tracking."""
        usage_log = UsageLog(
            organization_id=organization_id,
            user_id=user_id,
            feature="ai_request",
            quantity=1,
            model_name=model_name,
            tokens_input=tokens_input,
            tokens_output=tokens_output,
            execution_time_ms=execution_time_ms,
            cost_usd=Decimal(str(cost_usd)),
            meta=metadata or {},
        )
        self.db.add(usage_log)
        await self.db.flush()
        return usage_log
    
    async def log_skill_execution(
        self,
        skill_name: str,
        model_name: str,
        tokens_input: int,
        tokens_output: int,
        execution_time_ms: int,
        cost_usd: float,
        organization_id: str,
        user_id: str | None = None,
        success: bool = True,
        error_message: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> UsageLog:
        """Log a skill execution with performance metrics."""
        feature = "skill_execution" if success else "skill_error"
        
        usage_log = UsageLog(
            organization_id=organization_id,
            user_id=user_id,
            feature=feature,
            quantity=1,
            model_name=model_name,
            tokens_input=tokens_input,
            tokens_output=tokens_output,
            execution_time_ms=execution_time_ms,
            cost_usd=Decimal(str(cost_usd)),
            meta={
                **(metadata or {}),
                "skill_name": skill_name,
                "success": success,
                "error_message": error_message,
            },
        )
        self.db.add(usage_log)
        await self.db.flush()
        return usage_log
    
    async def log_agent_execution(
        self,
        agent_name: str,
        execution_time_ms: int,
        organization_id: str,
        user_id: str | None = None,
        success: bool = True,
        metadata: dict[str, Any] | None = None,
    ) -> UsageLog:
        """Log an agent execution."""
        feature = "agent_execution" if success else "agent_error"
        
        usage_log = UsageLog(
            organization_id=organization_id,
            user_id=user_id,
            feature=feature,
            quantity=1,
            execution_time_ms=execution_time_ms,
            cost_usd=Decimal("0"),  # Agent execution itself isn't charged
            meta={
                **(metadata or {}),
                "agent_name": agent_name,
                "success": success,
            },
        )
        self.db.add(usage_log)
        await self.db.flush()
        return usage_log
    
    def calculate_openclaw_cost(
        self,
        model_name: str,
        tokens_input: int,
        tokens_output: int,
    ) -> float:
        """Calculate cost using OpenClaw pricing from config."""
        # Default pricing (can be overridden in config)
        pricing = {
            "claude-sonnet-4-5": {"input": 0.015, "output": 0.075},
            "claude-haiku-4-5": {"input": 0.001, "output": 0.005},
            "gpt-4": {"input": 0.01, "output": 0.03},
            "gpt-4-turbo": {"input": 0.003, "output": 0.004},
        }
        
        # Override with config if available
        if hasattr(settings, 'OPENCLAW_PRICING'):
            pricing.update(settings.OPENCLAW_PRICING)
        
        model_pricing = pricing.get(model_name, pricing.get("claude-sonnet-4-5"))
        
        input_cost = (tokens_input / 1000) * model_pricing["input"]
        output_cost = (tokens_output / 1000) * model_pricing["output"]
        
        return input_cost + output_cost


# Context manager for easy usage logging
class AIUsageContext:
    """Context manager for automatic AI usage logging."""
    
    def __init__(
        self,
        db: AsyncSession,
        model_name: str,
        organization_id: str,
        user_id: str | None = None,
        metadata: dict[str, Any] | None = None,
    ):
        self.db = db
        self.model_name = model_name
        self.organization_id = organization_id
        self.user_id = user_id
        self.metadata = metadata
        self.start_time = None
        self.logger = UsageLogger(db)
    
    async def __aenter__(self):
        self.start_time = time.monotonic()
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        if self.start_time is None:
            return
        
        execution_time_ms = int((time.monotonic() - self.start_time) * 1000)
        
        # Calculate cost from OpenClaw response if available
        tokens_input = 0
        tokens_output = 0
        cost_usd = 0.0
        
        # This would be populated by the LLM client wrapper
        if hasattr(self, '_llm_response'):
            response = self._llm_response
            tokens_input = getattr(response, 'usage', {}).get('input_tokens', 0)
            tokens_output = getattr(response, 'usage', {}).get('output_tokens', 0)
            cost_usd = self.logger.calculate_openclaw_cost(
                self.model_name, tokens_input, tokens_output
            )
        
        # Log the usage
        success = exc_type is None
        await self.logger.log_ai_request(
            model_name=self.model_name,
            tokens_input=tokens_input,
            tokens_output=tokens_output,
            execution_time_ms=execution_time_ms,
            cost_usd=cost_usd,
            organization_id=self.organization_id,
            user_id=self.user_id,
            metadata={
                **(self.metadata or {}),
                "success": success,
                "error_type": exc_type.__name__ if exc_type else None,
                "error_message": str(exc_val) if exc_val else None,
            },
        )


# Decorator for automatic usage logging
def log_ai_usage(
    model_name: str,
    organization_id: str,
    user_id: str | None = None,
    metadata: dict[str, Any] | None = None,
):
    """Decorator for automatic AI usage logging."""
    def decorator(func):
        async def wrapper(*args, **kwargs):
            # Extract db session from kwargs or create new one
            db = kwargs.get('db')
            if not db:
                from app.database import get_db
                async for db_session in get_db():
                    db = db_session
                    break
            
            async with AIUsageContext(
                db, model_name, organization_id, user_id, metadata
            ) as ctx:
                ctx._llm_response = None  # Will be set by LLM client
                result = await func(*args, **kwargs)
                # Capture response for logging
                if hasattr(result, 'usage'):
                    ctx._llm_response = result
                return result
        return wrapper
    return decorator
