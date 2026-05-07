"""
Skill Chaining Service — Feature 17
Service for composing and executing skill chains
"""

from datetime import datetime
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import Integer, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.logger import get_logger
from app.models.skill_chaining import (
    SkillChain,
    SkillChainExecution,
    SkillComposition,
)

logger = get_logger(__name__)


class SkillChainingService:
    """
    Service for skill chaining and composition.

    Feature 17: Skill Chaining Service
    """

    def __init__(self, session: AsyncSession):
        self.session = session

    async def create_chain(
        self,
        name: str,
        steps: list[dict],
        description: str | None = None,
        input_schema: dict | None = None,
        output_schema: dict | None = None,
        is_parallel: bool = False,
        max_execution_time_ms: int | None = None,
        on_step_failure: str = "stop",
        fallback_skill_id: UUID | None = None,
        created_by_agent_id: UUID | None = None,
    ) -> SkillChain:
        """Create a new skill chain."""

        chain_key = f"chain_{datetime.utcnow().strftime('%Y%m%d%H%M%S')}_{str(uuid4())[:8]}"

        chain = SkillChain(
            id=uuid4(),
            chain_key=chain_key,
            name=name,
            description=description,
            steps=steps,
            input_schema=input_schema or {},
            output_schema=output_schema or {},
            is_parallel=is_parallel,
            max_execution_time_ms=max_execution_time_ms,
            on_step_failure=on_step_failure,
            fallback_skill_id=fallback_skill_id,
            created_by_agent_id=created_by_agent_id,
        )

        self.session.add(chain)
        await self.session.commit()

        logger.info(f"Skill chain created: {chain_key}")
        return chain

    async def execute_chain(
        self,
        chain_id: UUID,
        input_data: dict[str, Any],
        executed_by_agent_id: UUID | None = None,
        execution_context: dict | None = None,
    ) -> SkillChainExecution:
        """Execute a skill chain."""

        chain = await self.session.get(SkillChain, chain_id)
        if not chain:
            raise ValueError(f"Skill chain not found: {chain_id}")

        execution_key = f"exec_{datetime.utcnow().strftime('%Y%m%d%H%M%S')}_{str(uuid4())[:8]}"

        execution = SkillChainExecution(
            id=uuid4(),
            chain_id=chain_id,
            execution_key=execution_key,
            input_data=input_data,
            status="running",
            executed_by_agent_id=executed_by_agent_id,
            execution_context=execution_context or {},
        )

        self.session.add(execution)
        await self.session.commit()

        logger.info(f"Skill chain execution started: {execution_key}")
        return execution

    async def update_execution_result(
        self,
        execution_id: UUID,
        step_results: list[dict],
        output_data: dict[str, Any],
        total_duration_ms: int,
        status: str,
        failed_step_number: int | None = None,
        error_message: str | None = None,
    ) -> SkillChainExecution:
        """Update chain execution with results."""

        execution = await self.session.get(SkillChainExecution, execution_id)
        if not execution:
            raise ValueError(f"Chain execution not found: {execution_id}")

        execution.step_results = step_results
        execution.output_data = output_data
        execution.total_duration_ms = total_duration_ms
        execution.status = status
        execution.failed_step_number = failed_step_number
        execution.error_message = error_message
        execution.completed_at = datetime.utcnow()

        await self.session.commit()
        return execution

    async def create_composition(
        self,
        name: str,
        component_skills: list[dict],
        composition_type: str = "sequential",
        data_mappings: list[dict] | None = None,
        description: str | None = None,
        created_by_agent_id: UUID | None = None,
    ) -> SkillComposition:
        """Create a skill composition."""

        composition_key = f"comp_{datetime.utcnow().strftime('%Y%m%d%H%M%S')}_{str(uuid4())[:8]}"

        composition = SkillComposition(
            id=uuid4(),
            composition_key=composition_key,
            name=name,
            description=description,
            component_skills=component_skills,
            composition_type=composition_type,
            data_mappings=data_mappings or [],
            created_by_agent_id=created_by_agent_id,
        )

        self.session.add(composition)
        await self.session.commit()

        logger.info(f"Skill composition created: {composition_key}")
        return composition

    async def list_chains(
        self,
        created_by_agent_id: UUID | None = None,
        is_active: bool | None = True,
    ) -> list[SkillChain]:
        """List skill chains."""

        query = select(SkillChain)

        if created_by_agent_id:
            query = query.where(SkillChain.created_by_agent_id == created_by_agent_id)
        if is_active is not None:
            query = query.where(SkillChain.is_active == is_active)

        result = await self.session.execute(query)
        return list(result.scalars().all())

    async def get_chain_executions(
        self,
        chain_id: UUID,
        limit: int = 100,
    ) -> list[SkillChainExecution]:
        """Get execution history for a chain."""

        result = await self.session.execute(
            select(SkillChainExecution)
            .where(SkillChainExecution.chain_id == chain_id)
            .order_by(SkillChainExecution.started_at.desc())
            .limit(limit)
        )
        return list(result.scalars().all())

    async def get_chain_statistics(self, chain_id: UUID) -> dict[str, Any]:
        """Get execution statistics for a chain."""
        from sqlalchemy import func

        result = await self.session.execute(
            select(
                func.count(SkillChainExecution.id).label("total"),
                func.sum((SkillChainExecution.status == "completed").cast(Integer)).label(
                    "completed"
                ),
                func.avg(SkillChainExecution.total_duration_ms).label("avg_duration"),
            ).where(SkillChainExecution.chain_id == chain_id)
        )
        stats = result.one()

        total = stats.total or 0
        completed = stats.completed or 0

        return {
            "total_executions": total,
            "completed": completed,
            "failed": total - completed,
            "success_rate": (completed / total * 100) if total else 0,
            "average_duration_ms": float(stats.avg_duration) if stats.avg_duration else 0,
        }
