from fastapi import APIRouter
from app.core.event_bus import event_bus
from app.core.llm import llm_client

router = APIRouter(prefix="/system", tags=["system"])


@router.get("/health")
async def health():
    call_count = await llm_client.get_call_count_today()
    return {
        "status": "ok",
        "llm_degraded": llm_client.is_degraded(),
        "llm_cost_paused": llm_client.is_cost_paused(),
        "gemini_calls_today": call_count,
        "event_stats": event_bus.get_event_stats(),
    }


@router.post("/scan/now")
async def trigger_scan():
    """Manually trigger a scan (for testing/on-demand use)."""
    from app.tasks.daily_scan import run_daily_scan
    import asyncio
    asyncio.create_task(run_daily_scan())
    return {"status": "scan_triggered"}


@router.post("/brief/now")
async def trigger_brief():
    """Send morning brief immediately."""
    from app.agents.briefer import briefer_agent
    import asyncio
    asyncio.create_task(briefer_agent.send_morning_brief())
    return {"status": "brief_triggered"}
