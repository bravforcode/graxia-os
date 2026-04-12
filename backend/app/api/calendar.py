from datetime import date

from fastapi import APIRouter, Query

from app.core.calendar_ops import generate_today_calendar_overview

router = APIRouter(prefix="/calendar", tags=["calendar"])


@router.get("/today")
async def calendar_today(duration_minutes: int = Query(default=30, ge=15, le=180)):
    return await generate_today_calendar_overview(date.today(), duration_minutes=duration_minutes)
