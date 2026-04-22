from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from typing import Any

from app.database import get_db
from app.models.orchestration import AgentTask, AgentMessage
from app.core.event_bus import event_bus

router = APIRouter()

@router.get("/tasks")
async def list_tasks(db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(AgentTask).order_by(AgentTask.created_at.desc()).limit(100))
    tasks = result.scalars().all()
    return {"tasks": tasks}

@router.get("/meetings/{session_id}")
async def get_meeting_transcript(session_id: str, db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(AgentMessage)
        .where(AgentMessage.session_id == session_id)
        .order_by(AgentMessage.timestamp.asc())
    )
    messages = result.scalars().all()
    return {"session_id": session_id, "messages": messages}

@router.post("/delegate")
async def delegate_goal(payload: dict[str, Any]):
    goal = payload.get("goal")
    if not goal:
        raise HTTPException(status_code=400, detail="Missing 'goal'")
    
    # We trigger the orchestrator directly or via event
    from app.agents.orchestrator import orchestrator_agent
    import asyncio
    asyncio.create_task(orchestrator_agent.orchestrate_goal(goal))
    
    return {"status": "accepted", "goal": goal}

@router.post("/meeting")
async def start_meeting(payload: dict[str, Any]):
    topic = payload.get("topic")
    participants = payload.get("participants", [])
    if not topic:
        raise HTTPException(status_code=400, detail="Missing 'topic'")
    
    await event_bus.emit("agent.meeting.requested", {
        "topic": topic,
        "participants": participants,
        "requested_by": "api_user"
    })
    
    return {"status": "meeting_requested", "topic": topic}
