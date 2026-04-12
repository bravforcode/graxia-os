# 🚀 How to Continue Integration - Step by Step Guide

**Current Progress:** 20%  
**Next Target:** 50% (All API endpoints)  
**Time Needed:** 1 week

---

## 📋 Step-by-Step Guide

### Step 1: Refactor One API Module at a Time

Let's use **Submissions API** as the next example.

#### 1.1 Create Submission Handlers

**File:** `backend/app/cqrs/submission_handlers.py`

```python
"""
Submission Command and Query Handlers
"""
import logging
from uuid import uuid4
from datetime import datetime, timezone

from app.cqrs.handlers import CommandHandler, QueryHandler
from app.cqrs.commands import CreateSubmissionCommand, UpdateSubmissionCommand
from app.cqrs.queries import GetSubmissionQuery, ListSubmissionsQuery
from app.core.result import Result, ok, err
from app.repositories.submission_repository import SubmissionRepository
from app.models.submission import Submission
from app.database import AsyncSessionLocal

logger = logging.getLogger(__name__)


# Command Handlers
class CreateSubmissionHandler(CommandHandler[CreateSubmissionCommand, Submission]):
    """Handler for creating submissions."""
    
    async def handle(self, command: CreateSubmissionCommand) -> Result[Submission, Exception]:
        """Create new submission."""
        try:
            async with AsyncSessionLocal() as session:
                repo = SubmissionRepository(session)
                
                # Create submission
                submission = Submission(
                    id=uuid4(),
                    opportunity_id=command.opportunity_id,
                    status="draft",
                    created_at=datetime.now(timezone.utc),
                    updated_at=datetime.now(timezone.utc),
                )
                
                # Save
                submission = await repo.add(submission)
                await session.commit()
                
                # Emit event
                from app.core.event_bus import event_bus
                await event_bus.emit("submission.created", {
                    "submission_id": str(submission.id),
                    "opportunity_id": str(submission.opportunity_id),
                })
                
                logger.info(f"Created submission: {submission.id}")
                return ok(submission)
                
        except Exception as e:
            logger.error(f"Failed to create submission: {e}")
            return err(e)


class GetSubmissionHandler(QueryHandler[GetSubmissionQuery, Submission]):
    """Handler for getting submission by ID."""
    
    async def handle(self, query: GetSubmissionQuery) -> Result[Submission, Exception]:
        """Get submission."""
        try:
            async with AsyncSessionLocal() as session:
                repo = SubmissionRepository(session)
                submission = await repo.get_by_id(query.submission_id)
                
                if not submission:
                    return err(ValueError(f"Submission not found: {query.submission_id}"))
                
                return ok(submission)
                
        except Exception as e:
            logger.error(f"Failed to get submission: {e}")
            return err(e)


class ListSubmissionsHandler(QueryHandler[ListSubmissionsQuery, list]):
    """Handler for listing submissions."""
    
    async def handle(self, query: ListSubmissionsQuery) -> Result[list, Exception]:
        """List submissions."""
        try:
            async with AsyncSessionLocal() as session:
                repo = SubmissionRepository(session)
                
                # Get submissions
                if query.status:
                    submissions = await repo.find_by_status(query.status, query.limit)
                else:
                    submissions = await repo.get_all(query.skip, query.limit)
                
                return ok(submissions)
                
        except Exception as e:
            logger.error(f"Failed to list submissions: {e}")
            return err(e)
```

#### 1.2 Add Commands and Queries

**File:** `backend/app/cqrs/commands.py` (add these)

```python
@dataclass
class CreateSubmissionCommand:
    """Command to create a submission."""
    opportunity_id: UUID
    
@dataclass
class UpdateSubmissionCommand:
    """Command to update a submission."""
    submission_id: UUID
    status: str
```

**File:** `backend/app/cqrs/queries.py` (add these)

```python
@dataclass
class GetSubmissionQuery:
    """Query to get submission by ID."""
    submission_id: UUID

@dataclass
class ListSubmissionsQuery:
    """Query to list submissions."""
    status: Optional[str] = None
    skip: int = 0
    limit: int = 100
```

#### 1.3 Register Handlers

**File:** `backend/app/cqrs/setup.py` (add to setup_cqrs())

```python
from app.cqrs.submission_handlers import (
    CreateSubmissionHandler,
    GetSubmissionHandler,
    ListSubmissionsHandler,
)

def setup_cqrs():
    # ... existing opportunity handlers ...
    
    # Submission Command Handlers
    mediator.register_command_handler(
        CreateSubmissionCommand,
        CreateSubmissionHandler()
    )
    
    # Submission Query Handlers
    mediator.register_query_handler(
        GetSubmissionQuery,
        GetSubmissionHandler()
    )
    mediator.register_query_handler(
        ListSubmissionsQuery,
        ListSubmissionsHandler()
    )
```

#### 1.4 Refactor API Endpoints

**File:** `backend/app/api/submissions.py`

```python
from app.cqrs.handlers import mediator
from app.cqrs.commands import CreateSubmissionCommand
from app.cqrs.queries import GetSubmissionQuery, ListSubmissionsQuery

@router.get("", response_model=SubmissionList)
async def list_submissions(
    status: StatusFilter = None,
    limit: ResultLimit = 20,
    offset: ResultOffset = 0,
) -> SubmissionList:
    """List submissions using CQRS."""
    query = ListSubmissionsQuery(
        status=status,
        skip=offset,
        limit=limit
    )
    
    result = await mediator.send_query(query)
    
    if result.is_err():
        logger.error(f"Query failed: {result.error}")
        return SubmissionList(total=0, items=[])
    
    submissions = result.unwrap()
    items = [SubmissionOut.model_validate(sub) for sub in submissions]
    return SubmissionList(total=len(items), items=items)


@router.get("/{sub_id}", response_model=SubmissionOut)
async def get_submission(sub_id: UUID) -> SubmissionOut:
    """Get submission using CQRS."""
    query = GetSubmissionQuery(submission_id=sub_id)
    
    result = await mediator.send_query(query)
    
    if result.is_err():
        raise HTTPException(status_code=404, detail="Submission not found")
    
    submission = result.unwrap()
    return SubmissionOut.model_validate(submission)


@router.post("", response_model=SubmissionOut)
async def create_submission(data: SubmissionCreate) -> SubmissionOut:
    """Create submission using CQRS."""
    command = CreateSubmissionCommand(
        opportunity_id=data.opportunity_id
    )
    
    result = await mediator.send_command(command)
    
    if result.is_err():
        raise HTTPException(status_code=400, detail=str(result.error))
    
    submission = result.unwrap()
    return SubmissionOut.model_validate(submission)
```

---

## 🔄 Repeat for Each Module

### Modules to Refactor (in order):

1. ✅ Opportunities (DONE)
2. 🔄 Submissions (NEXT)
3. ⏳ Contacts
4. ⏳ Jobs
5. ⏳ Email Threads
6. ⏳ Tasks
7. ⏳ Costs
8. ⏳ Drafts

### For Each Module:

1. Create handlers file (`{module}_handlers.py`)
2. Add commands and queries
3. Register handlers in `setup.py`
4. Refactor API endpoints
5. Test endpoints
6. Move to next module

---

## 🧪 Testing Each Module

### Manual Testing

```bash
# Test list endpoint
curl http://localhost:8000/api/submissions?status=draft

# Test get endpoint
curl http://localhost:8000/api/submissions/{id}

# Test create endpoint
curl -X POST http://localhost:8000/api/submissions \
  -H "Content-Type: application/json" \
  -d '{"opportunity_id": "..."}'
```

### Automated Testing

**File:** `backend/tests/test_submission_handlers.py`

```python
import pytest
from app.cqrs.commands import CreateSubmissionCommand
from app.cqrs.queries import GetSubmissionQuery
from app.cqrs.handlers import mediator

@pytest.mark.asyncio
async def test_create_submission():
    """Test creating submission via CQRS."""
    command = CreateSubmissionCommand(
        opportunity_id=uuid4()
    )
    
    result = await mediator.send_command(command)
    
    assert result.is_ok()
    submission = result.unwrap()
    assert submission.id is not None
    assert submission.status == "draft"


@pytest.mark.asyncio
async def test_get_submission():
    """Test getting submission via CQRS."""
    # Create first
    command = CreateSubmissionCommand(opportunity_id=uuid4())
    create_result = await mediator.send_command(command)
    submission = create_result.unwrap()
    
    # Then get
    query = GetSubmissionQuery(submission_id=submission.id)
    result = await mediator.send_query(query)
    
    assert result.is_ok()
    fetched = result.unwrap()
    assert fetched.id == submission.id
```

---

## 📊 Track Your Progress

### Create a Checklist

**File:** `INTEGRATION_CHECKLIST.md`

```markdown
# Integration Checklist

## Opportunities ✅
- [x] Handlers created
- [x] Commands/Queries added
- [x] Handlers registered
- [x] API refactored
- [x] Tests written

## Submissions 🔄
- [ ] Handlers created
- [ ] Commands/Queries added
- [ ] Handlers registered
- [ ] API refactored
- [ ] Tests written

## Contacts ⏳
- [ ] Handlers created
- [ ] Commands/Queries added
- [ ] Handlers registered
- [ ] API refactored
- [ ] Tests written

... (continue for all modules)
```

---

## 💡 Tips for Success

### 1. One Module at a Time
- Don't try to do everything at once
- Complete one module fully before moving to next
- Test thoroughly before moving on

### 2. Copy-Paste-Adapt
- Use opportunities handlers as template
- Copy the structure
- Adapt to your module
- Don't reinvent the wheel

### 3. Test Immediately
- Test each handler as you create it
- Test each endpoint as you refactor it
- Don't wait until the end

### 4. Commit Often
- Commit after each module
- Use descriptive commit messages
- Easy to rollback if needed

### 5. Document as You Go
- Update checklist
- Note any issues
- Document decisions

---

## 🚨 Common Pitfalls

### 1. Forgetting to Register Handlers
```python
# ❌ Created handler but forgot to register
class MyHandler(...):
    pass

# ✅ Always register in setup.py
mediator.register_command_handler(MyCommand, MyHandler())
```

### 2. Not Using Result Type
```python
# ❌ Raising exceptions
async def handle(self, command):
    raise ValueError("Error")

# ✅ Return Result
async def handle(self, command):
    return err(ValueError("Error"))
```

### 3. Direct DB Access in Endpoints
```python
# ❌ Still using direct DB
@router.get("/items")
async def list_items(db: DbSession):
    result = await db.execute(select(Item))
    return result

# ✅ Use CQRS
@router.get("/items")
async def list_items():
    query = ListItemsQuery()
    result = await mediator.send_query(query)
    return result.unwrap()
```

### 4. Not Emitting Events
```python
# ❌ Forgot to emit event
submission = await repo.add(submission)
await session.commit()
return ok(submission)

# ✅ Always emit events
submission = await repo.add(submission)
await session.commit()
await event_bus.emit("submission.created", {...})
return ok(submission)
```

---

## 📈 Progress Tracking

### Daily Goals

**Day 1:**
- [ ] Refactor Submissions API (6 endpoints)
- [ ] Create 3 handlers
- [ ] Write 3 tests

**Day 2:**
- [ ] Refactor Contacts API (5 endpoints)
- [ ] Create 3 handlers
- [ ] Write 3 tests

**Day 3:**
- [ ] Refactor Jobs API (6 endpoints)
- [ ] Create 3 handlers
- [ ] Write 3 tests

**Day 4:**
- [ ] Refactor Email Threads API (5 endpoints)
- [ ] Create 3 handlers
- [ ] Write 3 tests

**Day 5:**
- [ ] Refactor Tasks API (5 endpoints)
- [ ] Create 3 handlers
- [ ] Write 3 tests

**Day 6:**
- [ ] Refactor Costs API (5 endpoints)
- [ ] Create 3 handlers
- [ ] Write 3 tests

**Day 7:**
- [ ] Refactor Drafts API (3 endpoints)
- [ ] Create 2 handlers
- [ ] Write 2 tests
- [ ] Final testing

---

## 🎯 Success Criteria

### For Each Module:
- ✅ All endpoints use CQRS
- ✅ No direct DB access
- ✅ All handlers registered
- ✅ All tests passing
- ✅ Events emitted properly

### Overall:
- ✅ 50% integration (all API endpoints)
- ✅ All handlers working
- ✅ All tests passing
- ✅ No regressions
- ✅ Performance maintained

---

## 🚀 Next Steps After 50%

### Phase 2: Agents (10-12 hours)
- Update all agents to use Domain Events
- Use Value Objects in agents
- Write tests

### Phase 3: Models (10-12 hours)
- Add Value Object properties
- Keep primitive fields for DB
- Write tests

### Phase 4: Optimization (5-10 hours)
- Performance tuning
- Caching strategies
- Load testing

---

## 📚 Resources

### Reference Files:
- `backend/app/api/opportunities.py` - Example refactored API
- `backend/app/cqrs/opportunity_handlers.py` - Example handlers
- `backend/app/repositories/opportunity_repository.py` - Example repository
- `REAL_INTEGRATION_COMPLETE.md` - Complete documentation
- `สรุปความคืบหน้าจริง.md` - Thai summary

### Patterns Documentation:
- `backend/app/core/domain_events.py` - Domain Events
- `backend/app/core/value_objects.py` - Value Objects
- `backend/app/core/specifications.py` - Specifications
- `backend/app/core/result.py` - Result Type

---

**Status:** 🟢 Ready to Continue  
**Current:** 20% Complete  
**Target:** 50% Complete  
**Time:** 1 week  
**Confidence:** 100%

**🚀 Let's continue the integration!**
