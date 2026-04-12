from fastapi import APIRouter, Query

from app.core.calendar_ops import generate_inbox_triage

router = APIRouter(prefix="/inbox", tags=["inbox"])


@router.get("/triage")
async def inbox_triage(max_results: int = Query(default=10, ge=1, le=20)):
    return await generate_inbox_triage(max_results=max_results)
