from datetime import datetime, timezone
from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, ConfigDict
from sqlalchemy import and_, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.core.time_utils import business_day_bounds_utc
from app.models.assistant_task import AssistantTask

router = APIRouter(prefix="/api/v1/tasks", tags=["tasks"])


class TaskCreate(BaseModel):
    title: str
    description: Optional[str] = None
    task_type: Optional[str] = None
    priority: int = 5
    due_date: Optional[datetime] = None
    related_entity_type: Optional[str] = None
    related_entity_id: Optional[UUID] = None
    assigned_to: str = "user"


class TaskUpdate(BaseModel):
    title: Optional[str] = None
    description: Optional[str] = None
    task_type: Optional[str] = None
    priority: Optional[int] = None
    status: Optional[str] = None
    due_date: Optional[datetime] = None


class TaskResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    title: str
    description: Optional[str]
    task_type: Optional[str]
    priority: int
    status: str
    due_date: Optional[datetime]
    related_entity_type: Optional[str]
    related_entity_id: Optional[UUID]
    assigned_to: str
    completed_at: Optional[datetime]
    created_at: datetime
    updated_at: datetime

class TaskListResponse(BaseModel):
    total: int
    items: list[TaskResponse]


@router.get("/", response_model=TaskListResponse)
async def list_tasks(
    db: AsyncSession = Depends(get_db),
    status: Optional[str] = Query(None, description="Filter by status"),
    priority_min: Optional[int] = Query(None, description="Minimum priority"),
    task_type: Optional[str] = Query(None, description="Task type"),
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
                AssistantTask.due_date < datetime.now(timezone.utc),
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
            AssistantTask.due_date < datetime.now(timezone.utc),
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
async def create_task(task_data: TaskCreate, db: AsyncSession = Depends(get_db)):
    task = AssistantTask(
        **task_data.model_dump(),
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
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

    task.updated_at = datetime.now(timezone.utc)

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
    task.updated_at = datetime.now(timezone.utc)

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
