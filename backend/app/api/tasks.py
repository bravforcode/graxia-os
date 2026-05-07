from datetime import UTC, datetime
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, ConfigDict
from sqlalchemy import and_, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.time_utils import business_day_bounds_utc
from app.database import get_db
from app.middleware.auth import get_current_user
from app.models.assistant_task import AssistantTask

router = APIRouter(prefix="/api/v1/tasks", tags=["tasks"])


class TaskCreate(BaseModel):
    title: str
    description: str | None = None
    task_type: str | None = None
    priority: int = 5
    due_date: datetime | None = None
    related_entity_type: str | None = None
    related_entity_id: UUID | None = None
    assigned_to: str = "user"


class TaskUpdate(BaseModel):
    title: str | None = None
    description: str | None = None
    task_type: str | None = None
    priority: int | None = None
    status: str | None = None
    due_date: datetime | None = None


class TaskResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    title: str
    description: str | None
    task_type: str | None
    priority: int
    status: str
    due_date: datetime | None
    related_entity_type: str | None
    related_entity_id: UUID | None
    assigned_to: str
    completed_at: datetime | None
    created_at: datetime
    updated_at: datetime

class TaskListResponse(BaseModel):
    total: int
    items: list[TaskResponse]


@router.get("/", response_model=TaskListResponse)
async def list_tasks(
    db: AsyncSession = Depends(get_db),
    status: str | None = Query(None, description="Filter by status"),
    priority_min: int | None = Query(None, description="Minimum priority"),
    task_type: str | None = Query(None, description="Task type"),
    overdue_only: bool = Query(False, description="Show only overdue tasks"),
    limit: int = Query(50, le=100),
    offset: int = Query(0, ge=0),
):
    query = select(AssistantTask)

    conditions = []
    if status:
        conditions.append(AssistantTask.status == status)
    if priority_min:
        conditions.append(AssistantTask.priority >= priority_min)
    if task_type:
        conditions.append(AssistantTask.task_type == task_type)
    if overdue_only:
        conditions.append(
            and_(
                AssistantTask.due_date < datetime.now(UTC),
                AssistantTask.status != "completed",
            )
        )

    if conditions:
        query = query.where(and_(*conditions))

    total = await db.scalar(select(func.count()).select_from(query.subquery()))
    result = await db.execute(
        query.order_by(AssistantTask.priority.desc(), AssistantTask.due_date.asc())
        .offset(offset)
        .limit(limit)
    )
    tasks = [TaskResponse.model_validate(task) for task in result.scalars().all()]
    return TaskListResponse(total=int(total or 0), items=tasks)


@router.get("/stats", response_model=dict)
@router.get("/stats/summary", response_model=dict)
async def get_task_stats(db: AsyncSession = Depends(get_db)):
    today_start_utc, tomorrow_start_utc = business_day_bounds_utc()

    status_query = select(AssistantTask.status, func.count(AssistantTask.id)).group_by(AssistantTask.status)
    status_result = await db.execute(status_query)
    by_status = {row[0]: int(row[1]) for row in status_result}

    overdue_query = select(func.count(AssistantTask.id)).where(
        and_(
            AssistantTask.due_date < datetime.now(UTC),
            AssistantTask.status != "completed",
        )
    )
    overdue_result = await db.execute(overdue_query)
    overdue_count = int(overdue_result.scalar() or 0)

    due_today_query = select(func.count(AssistantTask.id)).where(
        and_(
            AssistantTask.due_date >= today_start_utc,
            AssistantTask.due_date < tomorrow_start_utc,
            AssistantTask.status != "completed",
        )
    )
    due_today_result = await db.execute(due_today_query)
    due_today_count = int(due_today_result.scalar() or 0)

    return {
        "total_tasks": int(sum(by_status.values())),
        "by_status": by_status,
        "overdue_count": overdue_count,
        "due_today_count": due_today_count,
    }


@router.get("/{task_id}", response_model=TaskResponse)
async def get_task(task_id: UUID, db: AsyncSession = Depends(get_db)):
    query = select(AssistantTask).where(AssistantTask.id == task_id)
    result = await db.execute(query)
    task = result.scalar_one_or_none()

    if not task:
        raise HTTPException(status_code=404, detail="Task not found")

    return TaskResponse.model_validate(task)


@router.post("/", response_model=TaskResponse, status_code=201)
async def create_task(
    task_data: TaskCreate,
    db: AsyncSession = Depends(get_db),
    current_user: "User" = Depends(get_current_user),
):
    task = AssistantTask(
        **task_data.model_dump(),
        organization_id=current_user.organization_id,
        created_at=datetime.now(UTC),
        updated_at=datetime.now(UTC),
    )

    db.add(task)
    await db.commit()
    await db.refresh(task)

    from app.core.event_bus import event_bus

    await event_bus.emit(
        "task.created",
        {"task_id": str(task.id), "title": task.title, "priority": task.priority},
    )

    return TaskResponse.model_validate(task)


@router.patch("/{task_id}", response_model=TaskResponse)
async def update_task(task_id: UUID, task_data: TaskUpdate, db: AsyncSession = Depends(get_db)):
    query = select(AssistantTask).where(AssistantTask.id == task_id)
    result = await db.execute(query)
    task = result.scalar_one_or_none()

    if not task:
        raise HTTPException(status_code=404, detail="Task not found")

    for field, value in task_data.model_dump(exclude_unset=True).items():
        setattr(task, field, value)

    task.updated_at = datetime.now(UTC)

    await db.commit()
    await db.refresh(task)

    from app.core.event_bus import event_bus

    await event_bus.emit(
        "task.updated",
        {"task_id": str(task.id), "title": task.title, "status": task.status},
    )
    return TaskResponse.model_validate(task)


@router.patch("/{task_id}/complete", response_model=TaskResponse)
@router.post("/{task_id}/complete", response_model=TaskResponse)
async def complete_task(task_id: UUID, db: AsyncSession = Depends(get_db)):
    query = select(AssistantTask).where(AssistantTask.id == task_id)
    result = await db.execute(query)
    task = result.scalar_one_or_none()

    if not task:
        raise HTTPException(status_code=404, detail="Task not found")

    task.mark_completed()
    task.updated_at = datetime.now(UTC)

    await db.commit()
    await db.refresh(task)

    from app.core.event_bus import event_bus

    await event_bus.emit(
        "task.completed",
        {"task_id": str(task.id), "title": task.title, "status": task.status},
    )
    return TaskResponse.model_validate(task)


@router.delete("/{task_id}", status_code=204)
async def delete_task(task_id: UUID, db: AsyncSession = Depends(get_db)):
    query = select(AssistantTask).where(AssistantTask.id == task_id)
    result = await db.execute(query)
    task = result.scalar_one_or_none()

    if not task:
        raise HTTPException(status_code=404, detail="Task not found")

    await db.delete(task)
    await db.commit()
