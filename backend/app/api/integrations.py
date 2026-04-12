from datetime import date
from typing import Any

from fastapi import APIRouter, Query, Request

from app.core.google_workspace import google_workspace
from app.telegram_bot.bot import send_message

router = APIRouter(prefix="/integrations", tags=["integrations"])


@router.get("/google/health")
async def google_health():
    return await google_workspace.health()


@router.get("/google/gmail/inbox-summary")
async def google_gmail_inbox_summary(max_results: int = Query(default=5, ge=1, le=20)):
    return await google_workspace.get_gmail_inbox_summary(max_results=max_results)


@router.get("/google/calendar/today")
async def google_calendar_today(max_results: int = Query(default=10, ge=1, le=20)):
    return await google_workspace.get_calendar_day_summary(date.today(), max_results=max_results)


def _format_alertmanager_message(payload: dict[str, Any]) -> str:
    alerts = payload.get("alerts") or []
    status = payload.get("status", "unknown")
    lines = [f"Alertmanager notification status={status} count={len(alerts)}"]
    for alert in alerts[:5]:
        labels = alert.get("labels") or {}
        annotations = alert.get("annotations") or {}
        alert_name = labels.get("alertname", "unknown")
        severity = labels.get("severity", "unknown")
        summary = annotations.get("summary") or annotations.get("description") or "No summary"
        runbook = annotations.get("runbook") or "runbook missing"
        current = annotations.get("current_value") or annotations.get("current_age") or annotations.get("value")
        lines.append(f"- {alert_name} severity={severity}: {summary}")
        if current:
            lines.append(f"  current={current}")
        lines.append(f"  runbook={runbook}")
    if len(alerts) > 5:
        lines.append(f"- {len(alerts) - 5} additional alerts omitted")
    return "\n".join(lines)


@router.post("/alerts/telegram")
async def alertmanager_telegram_webhook(request: Request, payload: dict[str, Any]):
    message = _format_alertmanager_message(payload)
    delivered = await send_message(message, parse_mode=None)
    return {"status": "delivered" if delivered else "accepted", "alerts": len(payload.get("alerts") or [])}
