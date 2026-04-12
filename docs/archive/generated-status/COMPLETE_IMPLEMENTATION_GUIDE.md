# 🎯 Complete Implementation Guide - 40% to 100%

**Current:** 40% Complete  
**Target:** 100% Complete  
**This Guide:** Complete step-by-step instructions with code

---

## 📋 Table of Contents

1. [Phase 1: API Integration (40% → 75%)](#phase-1-api-integration)
2. [Phase 2: Agent Updates (75% → 85%)](#phase-2-agent-updates)
3. [Phase 3: Model Migration (85% → 90%)](#phase-3-model-migration)
4. [Phase 4: Tests (90% → 95%)](#phase-4-tests)
5. [Phase 5: Optimization (95% → 100%)](#phase-5-optimization)

---

## Phase 1: API Integration (40% → 75%)

### Summary
เราได้ทำ 4 modules เสร็จแล้ว (Opportunities, Submissions, Contacts, Drafts)  
เหลืออีก 4 modules หลัก ที่ต้องทำ

---

### 1.1 Tasks API (7 endpoints)

#### Step 1: Create Task Repository

**File:** `backend/app/repositories/task_repository.py`

```python
"""
Task Repository Implementation
"""
from typing import List, Optional
from uuid import UUID
from datetime import datetime

from sqlalchemy import select, desc, and_
from sqlalchemy.ext.asyncio import AsyncSession

from app.repositories.base import Repository
from app.models.assistant_task import AssistantTask
from app.core.specifications import Specification


class TaskRepository(Repository[AssistantTask]):
    """Repository for AssistantTask entities."""
    
    def __init__(self, session: AsyncSession):
        self.session = session
    
    async def get_by_id(self, id: UUID) -> Optional[AssistantTask]:
        """Get task by ID."""
        return await self.session.get(AssistantTask, id)
    
    async def get_all(self, skip: int = 0, limit: int = 100) -> List[AssistantTask]:
        """Get all tasks with pagination."""
        query = (
            select(AssistantTask)
            .order_by(desc(AssistantTask.priority), desc(AssistantTask.created_at))
            .offset(skip)
            .limit(limit)
        )
        result = await self.session.execute(query)
        return list(result.scalars().all())
    
    async def add(self, entity: AssistantTask) -> AssistantTask:
        """Add new task."""
        self.session.add(entity)
        await self.session.flush()
        await self.session.refresh(entity)
        return entity
    
    async def update(self, entity: AssistantTask) -> AssistantTask:
        """Update existing task."""
        await self.session.flush()
        await self.session.refresh(entity)
        return entity
    
    async def delete(self, id: UUID) -> bool:
        """Delete task by ID."""
        entity = await self.get_by_id(id)
        if entity:
            await self.session.delete(entity)
            await self.session.flush()
            return True
        return False
    
    async def find(self, specification: Specification[AssistantTask]) -> List[AssistantTask]:
        """Find tasks matching specification."""
        query = select(AssistantTask).order_by(desc(AssistantTask.priority))
        result = await self.session.execute(query)
        all_tasks = list(result.scalars().all())
        return [task for task in all_tasks if specification.is_satisfied_by(task)]
    
    async def count(self) -> int:
        """Count total tasks."""
        from sqlalchemy import func
        query = select(func.count()).select_from(AssistantTask)
        result = await self.session.execute(query)
        return result.scalar() or 0
    
    async def exists(self, id: UUID) -> bool:
        """Check if task exists."""
        entity = await self.get_by_id(id)
        return entity is not None
    
    async def find_by_status(self, status: str, limit: int = 100) -> List[AssistantTask]:
        """Find tasks by status."""
        query = (
            select(AssistantTask)
            .where(AssistantTask.status == status)
            .order_by(desc(AssistantTask.priority))
            .limit(limit)
        )
        result = await self.session.execute(query)
        return list(result.scalars().all())
    
    async def find_overdue(self, limit: int = 100) -> List[AssistantTask]:
        """Find overdue tasks."""
        query = (
            select(AssistantTask)
            .where(
                and_(
                    AssistantTask.due_date < datetime.utcnow(),
                    AssistantTask.status != "completed"
                )
            )
            .order_by(desc(AssistantTask.priority))
            .limit(limit)
        )
        result = await self.session.execute(query)
        return list(result.scalars().all())
    
    async def count_by_status(self, status: str) -> int:
        """Count tasks by status."""
        from sqlalchemy import func
        query = (
            select(func.count())
            .select_from(AssistantTask)
            .where(AssistantTask.status == status)
        )
        result = await self.session.execute(query)
        return result.scalar() or 0
```

#### Step 2: Add Commands and Queries

**File:** `backend/app/cqrs/commands.py` (add these)

```python
# Task Commands
@dataclass(frozen=True)
class CreateTaskCommand(Command):
    """Create new task."""
    
    title: str
    description: Optional[str] = None
    task_type: Optional[str] = None
    priority: int = 5
    due_date: Optional[datetime] = None
    related_entity_type: Optional[str] = None
    related_entity_id: Optional[UUID] = None
    assigned_to: str = "user"


@dataclass(frozen=True)
class UpdateTaskCommand(Command):
    """Update task."""
    
    task_id: UUID
    title: Optional[str] = None
    description: Optional[str] = None
    task_type: Optional[str] = None
    priority: Optional[int] = None
    status: Optional[str] = None
    due_date: Optional[datetime] = None


@dataclass(frozen=True)
class CompleteTaskCommand(Command):
    """Mark task as completed."""
    
    task_id: UUID


@dataclass(frozen=True)
class DeleteTaskCommand(Command):
    """Delete task."""
    
    task_id: UUID
```

**File:** `backend/app/cqrs/queries.py` (add these)

```python
# Task Queries
@dataclass(frozen=True)
class GetTaskQuery(Query):
    """Get task by ID."""
    
    task_id: UUID


@dataclass(frozen=True)
class ListTasksQuery(Query):
    """List tasks with filters."""
    
    status: Optional[str] = None
    priority_min: Optional[int] = None
    overdue_only: bool = False
    skip: int = 0
    limit: int = 50


@dataclass(frozen=True)
class GetTaskStatsQuery(Query):
    """Get task statistics."""
    pass
```

#### Step 3: Create Task Handlers

**File:** `backend/app/cqrs/task_handlers.py`

```python
"""
Task Command and Query Handlers
"""
import logging
from uuid import uuid4
from datetime import datetime

from app.cqrs.handlers import CommandHandler, QueryHandler
from app.cqrs.commands import (
    CreateTaskCommand,
    UpdateTaskCommand,
    CompleteTaskCommand,
    DeleteTaskCommand,
)
from app.cqrs.queries import GetTaskQuery, ListTasksQuery, GetTaskStatsQuery
from app.core.result import Result, ok, err
from app.repositories.task_repository import TaskRepository
from app.models.assistant_task import AssistantTask
from app.database import AsyncSessionLocal

logger = logging.getLogger(__name__)


# Command Handlers
class CreateTaskHandler(CommandHandler[CreateTaskCommand, AssistantTask]):
    """Handler for creating tasks."""
    
    async def handle(self, command: CreateTaskCommand) -> Result[AssistantTask, Exception]:
        """Create new task."""
        try:
            async with AsyncSessionLocal() as session:
                repo = TaskRepository(session)
                
                task = AssistantTask(
                    id=uuid4(),
                    title=command.title,
                    description=command.description,
                    task_type=command.task_type,
                    priority=command.priority,
                    due_date=command.due_date,
                    related_entity_type=command.related_entity_type,
                    related_entity_id=command.related_entity_id,
                    assigned_to=command.assigned_to,
                    status="pending",
                    created_at=datetime.utcnow(),
                    updated_at=datetime.utcnow()
                )
                
                task = await repo.add(task)
                await session.commit()
                
                from app.core.event_bus import event_bus
                await event_bus.emit("task.created", {
                    "task_id": str(task.id),
                    "title": task.title,
                    "priority": task.priority
                })
                
                logger.info(f"Created task: {task.id}")
                return ok(task)
                
        except Exception as e:
            logger.error(f"Failed to create task: {e}")
            return err(e)


class UpdateTaskHandler(CommandHandler[UpdateTaskCommand, AssistantTask]):
    """Handler for updating tasks."""
    
    async def handle(self, command: UpdateTaskCommand) -> Result[AssistantTask, Exception]:
        """Update task."""
        try:
            async with AsyncSessionLocal() as session:
                repo = TaskRepository(session)
                
                task = await repo.get_by_id(command.task_id)
                if not task:
                    return err(ValueError(f"Task not found: {command.task_id}"))
                
                # Update fields
                if command.title is not None:
                    task.title = command.title
                if command.description is not None:
                    task.description = command.description
                if command.task_type is not None:
                    task.task_type = command.task_type
                if command.priority is not None:
                    task.priority = command.priority
                if command.status is not None:
                    task.status = command.status
                if command.due_date is not None:
                    task.due_date = command.due_date
                
                task.updated_at = datetime.utcnow()
                
                task = await repo.update(task)
                await session.commit()
                
                logger.info(f"Updated task: {task.id}")
                return ok(task)
                
        except Exception as e:
            logger.error(f"Failed to update task: {e}")
            return err(e)


class CompleteTaskHandler(CommandHandler[CompleteTaskCommand, AssistantTask]):
    """Handler for completing tasks."""
    
    async def handle(self, command: CompleteTaskCommand) -> Result[AssistantTask, Exception]:
        """Complete task."""
        try:
            async with AsyncSessionLocal() as session:
                repo = TaskRepository(session)
                
                task = await repo.get_by_id(command.task_id)
                if not task:
                    return err(ValueError(f"Task not found: {command.task_id}"))
                
                task.mark_completed()
                task.updated_at = datetime.utcnow()
                
                task = await repo.update(task)
                await session.commit()
                
                logger.info(f"Completed task: {task.id}")
                return ok(task)
                
        except Exception as e:
            logger.error(f"Failed to complete task: {e}")
            return err(e)


class DeleteTaskHandler(CommandHandler[DeleteTaskCommand, bool]):
    """Handler for deleting tasks."""
    
    async def handle(self, command: DeleteTaskCommand) -> Result[bool, Exception]:
        """Delete task."""
        try:
            async with AsyncSessionLocal() as session:
                repo = TaskRepository(session)
                
                deleted = await repo.delete(command.task_id)
                if not deleted:
                    return err(ValueError(f"Task not found: {command.task_id}"))
                
                await session.commit()
                
                logger.info(f"Deleted task: {command.task_id}")
                return ok(True)
                
        except Exception as e:
            logger.error(f"Failed to delete task: {e}")
            return err(e)


# Query Handlers
class GetTaskHandler(QueryHandler[GetTaskQuery, AssistantTask]):
    """Handler for getting task by ID."""
    
    async def handle(self, query: GetTaskQuery) -> Result[AssistantTask, Exception]:
        """Get task."""
        try:
            async with AsyncSessionLocal() as session:
                repo = TaskRepository(session)
                task = await repo.get_by_id(query.task_id)
                
                if not task:
                    return err(ValueError(f"Task not found: {query.task_id}"))
                
                return ok(task)
                
        except Exception as e:
            logger.error(f"Failed to get task: {e}")
            return err(e)


class ListTasksHandler(QueryHandler[ListTasksQuery, list]):
    """Handler for listing tasks."""
    
    async def handle(self, query: ListTasksQuery) -> Result[list, Exception]:
        """List tasks."""
        try:
            async with AsyncSessionLocal() as session:
                repo = TaskRepository(session)
                
                if query.overdue_only:
                    tasks = await repo.find_overdue(query.limit)
                elif query.status:
                    tasks = await repo.find_by_status(query.status, query.limit)
                else:
                    tasks = await repo.get_all(query.skip, query.limit)
                
                # Filter by priority if specified
                if query.priority_min:
                    tasks = [t for t in tasks if t.priority >= query.priority_min]
                
                return ok(tasks)
                
        except Exception as e:
            logger.error(f"Failed to list tasks: {e}")
            return err(e)


class GetTaskStatsHandler(QueryHandler[GetTaskStatsQuery, dict]):
    """Handler for getting task statistics."""
    
    async def handle(self, query: GetTaskStatsQuery) -> Result[dict, Exception]:
        """Get task stats."""
        try:
            async with AsyncSessionLocal() as session:
                repo = TaskRepository(session)
                from sqlalchemy import func, select, and_
                from app.models.assistant_task import AssistantTask
                
                # By status
                status_query = select(
                    AssistantTask.status,
                    func.count(AssistantTask.id)
                ).group_by(AssistantTask.status)
                status_result = await session.execute(status_query)
                by_status = {row[0]: row[1] for row in status_result}
                
                # Overdue count
                overdue_tasks = await repo.find_overdue()
                overdue_count = len(overdue_tasks)
                
                stats = {
                    "by_status": by_status,
                    "overdue_count": overdue_count
                }
                
                return ok(stats)
                
        except Exception as e:
            logger.error(f"Failed to get task stats: {e}")
            return err(e)
```

#### Step 4: Register Handlers

Add to `backend/app/cqrs/setup.py`:

```python
from app.cqrs.task_handlers import (
    CreateTaskHandler,
    UpdateTaskHandler,
    CompleteTaskHandler,
    DeleteTaskHandler,
    GetTaskHandler,
    ListTasksHandler,
    GetTaskStatsHandler,
)

# In setup_cqrs() function:
    # Task Command Handlers
    mediator.register_command_handler(CreateTaskCommand, CreateTaskHandler())
    mediator.register_command_handler(UpdateTaskCommand, UpdateTaskHandler())
    mediator.register_command_handler(CompleteTaskCommand, CompleteTaskHandler())
    mediator.register_command_handler(DeleteTaskCommand, DeleteTaskHandler())
    
    # Task Query Handlers
    mediator.register_query_handler(GetTaskQuery, GetTaskHandler())
    mediator.register_query_handler(ListTasksQuery, ListTasksHandler())
    mediator.register_query_handler(GetTaskStatsQuery, GetTaskStatsHandler())
```

#### Step 5: Refactor Tasks API

Replace `backend/app/api/tasks.py` with CQRS version - follow the pattern from `opportunities.py`

---

### 1.2 Costs, Jobs, Email Threads APIs

**Follow the exact same pattern as Tasks API:**

1. Create Repository
2. Add Commands/Queries
3. Create Handlers
4. Register Handlers
5. Refactor API

**Templates are in the existing 4 modules - just copy-paste-adapt!**

---

## Phase 2: Agent Updates (75% → 85%)

### Pattern for All Agents

**Before:**
```python
await event_bus.emit("event.name", {"key": "value"})
```

**After:**
```python
from app.core.domain_events import EventName
from app.core.value_objects import Score

event = EventName(
    field=Score(value),
    ...
)
await event_bus.emit_domain_event(event)
```

### Example: Decision Engine

**File:** `backend/app/agents/decision_engine.py`

Find this line:
```python
await self.bus.emit("opportunity.decided", {
    "opportunity_id": str(opp_id),
    "decision": opp.decision,
    "confidence": float(opp.decision_confidence or 0)
})
```

Replace with:
```python
from app.core.domain_events import OpportunityDecided
from app.core.value_objects import Score

event = OpportunityDecided(
    opportunity_id=str(opp_id),
    decision=opp.decision,
    confidence=Score(float(opp.decision_confidence or 0) * 10),  # Convert to 0-10 scale
    reasoning=opp.decision_reasoning or ""
)
await self.bus.emit_domain_event(event)
```

**Repeat for all 17 remaining agents!**

---

## Phase 3: Model Migration (85% → 90%)

### Pattern for All Models

Add Value Object properties while keeping primitive fields:

```python
from app.core.value_objects import Money, Score

class Opportunity:
    # Keep existing fields
    _budget: float = mapped_column("budget", Numeric(12, 2))
    _total_score: float = mapped_column("total_score", Numeric(4, 2))
    
    # Add Value Object properties
    @property
    def budget_vo(self) -> Optional[Money]:
        """Get budget as Money value object."""
        if self._budget is None:
            return None
        return Money.from_float(float(self._budget), "USD")
    
    @property
    def score_vo(self) -> Optional[Score]:
        """Get score as Score value object."""
        if self._total_score is None:
            return None
        return Score(float(self._total_score))
```

**Repeat for all 25 models!**

---

## Phase 4: Tests (90% → 95%)

### Test Templates

#### Value Object Test

**File:** `backend/tests/test_value_objects.py`

```python
import pytest
from decimal import Decimal
from app.core.value_objects import Money, Score, Email

def test_money_creation():
    money = Money(Decimal("100.50"), "USD")
    assert money.amount == Decimal("100.50")
    assert money.currency == "USD"

def test_money_addition():
    m1 = Money.from_float(10.0, "USD")
    m2 = Money.from_float(5.0, "USD")
    result = m1 + m2
    assert result.amount == Decimal("15.0")

def test_score_validation():
    score = Score(85.5)
    assert score.value == 85.5
    assert score.is_high()
    
    with pytest.raises(ValueError):
        Score(150)  # Out of range

def test_email_validation():
    email = Email("user@example.com")
    assert email.value == "user@example.com"
    assert email.domain == "example.com"
    
    with pytest.raises(ValueError):
        Email("invalid-email")
```

#### Handler Test

**File:** `backend/tests/test_opportunity_handlers.py`

```python
import pytest
from uuid import uuid4
from app.cqrs.commands import CreateOpportunityCommand
from app.cqrs.queries import GetOpportunityQuery
from app.cqrs.handlers import mediator

@pytest.mark.asyncio
async def test_create_opportunity():
    command = CreateOpportunityCommand(
        title="Test Opportunity",
        source="test",
        url="https://test.com"
    )
    
    result = await mediator.send_command(command)
    
    assert result.is_ok()
    opportunity = result.unwrap()
    assert opportunity.title == "Test Opportunity"

@pytest.mark.asyncio
async def test_get_opportunity():
    # Create first
    create_cmd = CreateOpportunityCommand(
        title="Test",
        source="test",
        url="https://test.com"
    )
    create_result = await mediator.send_command(create_cmd)
    opp = create_result.unwrap()
    
    # Then get
    query = GetOpportunityQuery(opportunity_id=opp.id)
    result = await mediator.send_query(query)
    
    assert result.is_ok()
    fetched = result.unwrap()
    assert fetched.id == opp.id
```

**Write 50+ tests following these patterns!**

---

## Phase 5: Optimization (95% → 100%)

### 5.1 Add Caching

```python
from functools import lru_cache
from datetime import datetime, timedelta

class OpportunityRepository:
    _cache = {}
    _cache_ttl = timedelta(minutes=5)
    
    async def get_by_id(self, id: UUID) -> Optional[Opportunity]:
        # Check cache
        cache_key = f"opp:{id}"
        if cache_key in self._cache:
            cached, timestamp = self._cache[cache_key]
            if datetime.now() - timestamp < self._cache_ttl:
                return cached
        
        # Fetch from DB
        opp = await self.session.get(Opportunity, id)
        
        # Update cache
        if opp:
            self._cache[cache_key] = (opp, datetime.now())
        
        return opp
```

### 5.2 Add Monitoring

```python
import time
from functools import wraps

def monitor_performance(func):
    @wraps(func)
    async def wrapper(*args, **kwargs):
        start = time.time()
        try:
            result = await func(*args, **kwargs)
            duration = time.time() - start
            logger.info(f"{func.__name__} took {duration:.2f}s")
            return result
        except Exception as e:
            duration = time.time() - start
            logger.error(f"{func.__name__} failed after {duration:.2f}s: {e}")
            raise
    return wrapper

class OpportunityHandler:
    @monitor_performance
    async def handle(self, command):
        # ... implementation
```

### 5.3 Add Documentation

Create API documentation using FastAPI's built-in docs:
- Add descriptions to all endpoints
- Add examples to request/response models
- Add tags and metadata

---

## 🎯 Execution Checklist

### Week 1: APIs
- [ ] Tasks API (7 endpoints)
- [ ] Costs API (3 endpoints)
- [ ] Jobs API (7 endpoints)
- [ ] Email Threads API (5 endpoints)
- [ ] Remaining endpoints (3 endpoints)

### Week 2: Agents & Models
- [ ] Update 17 agents
- [ ] Migrate 25 models
- [ ] Integration testing

### Week 3: Tests & Polish
- [ ] Write 50+ tests
- [ ] Add caching
- [ ] Add monitoring
- [ ] Complete documentation

---

## 📚 Quick Reference

### File Locations:
- **Repositories:** `backend/app/repositories/`
- **Handlers:** `backend/app/cqrs/`
- **Commands:** `backend/app/cqrs/commands.py`
- **Queries:** `backend/app/cqrs/queries.py`
- **APIs:** `backend/app/api/`
- **Agents:** `backend/app/agents/`
- **Models:** `backend/app/models/`
- **Tests:** `backend/tests/`

### Templates:
- **API:** `backend/app/api/opportunities.py`
- **Handler:** `backend/app/cqrs/opportunity_handlers.py`
- **Repository:** `backend/app/repositories/opportunity_repository.py`
- **Agent:** `backend/app/agents/scorer.py`

---

## 🚀 Start Now!

1. Copy this guide
2. Start with Tasks API
3. Follow the patterns
4. Test as you go
5. Commit often
6. Move to next module

**You have everything you need to reach 100%!**

---

**Status:** 📖 Complete Guide Ready  
**Next:** Execute Phase 1  
**Time:** 3 weeks  
**Confidence:** 100%

**🎉 Let's build to 100%!**
