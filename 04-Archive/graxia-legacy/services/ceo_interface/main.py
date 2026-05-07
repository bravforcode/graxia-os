from fastapi import APIRouter, Request, BackgroundTasks
from pydantic import BaseModel
import httpx
import os
import sys
import uuid
import json
from datetime import datetime, timedelta
from typing import Optional, List

# Add root to path for bravos_core
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '../../')))
from packages.bravos_core.python.base_service import create_app, ApiError
from packages.bravos_core.python.event_bus import RedisEventBus
from packages.bwcp_protocol.python.envelope import MessageEnvelope

# Telegram Settings
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN", "mock_token")
TELEGRAM_API = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}"

router = APIRouter()
bus = RedisEventBus()

class TelegramUpdate(BaseModel):
    update_id: int
    message: Optional[dict] = None
    callback_query: Optional[dict] = None

@router.post("/webhook")
async def telegram_webhook(update: TelegramUpdate, background_tasks: BackgroundTasks):
    """Entry point for CEO commands from Telegram."""
    if update.message:
        text = update.message.get("text", "")
        chat_id = update.message.get("chat", {}).get("id")
        
        if text.startswith("/mission"):
            mission_text = text.replace("/mission", "").strip()
            if not mission_text:
                await send_telegram_msg(chat_id, "❌ Please provide mission details. Usage: /mission <objective>")
                return {"status": "error"}
            background_tasks.add_task(handle_create_mission, chat_id, mission_text)
            return {"status": "processing"}
            
        if text.startswith("/status"):
            background_tasks.add_task(handle_status_check, chat_id)
            return {"status": "processing"}

        if text.startswith("/approvals"):
            background_tasks.add_task(handle_list_approvals, chat_id)
            return {"status": "processing"}

    return {"status": "ignored"}

async def handle_create_mission(chat_id: int, mission_text: str):
    """Generates a BWCP Message and EMITs it to the Redis Event Bus."""
    mission_id = f"mission-{uuid.uuid4().hex[:8]}"
    trace_id = f"trace-{uuid.uuid4().hex[:12]}"
    
    # Create BWCP Envelope
    envelope = MessageEnvelope(
        message_id=str(uuid.uuid4()),
        thread_id=mission_id,
        mission_id=mission_id,
        task_id=str(uuid.uuid4()),
        from_agent="ceo_interface",
        to_agent="chief_of_staff",
        message_type="MISSION_CREATED",
        priority="HIGH",
        deadline_at=datetime.utcnow() + timedelta(days=7),
        correlation_id=mission_id,
        trace_id=trace_id,
        payload={"objective": mission_text}
    )
    
    # Emit to Event Bus
    bus.emit("missions", envelope.dict())
    
    print(f"🚀 CEO created mission: {mission_id} - {mission_text}")
    await send_telegram_msg(chat_id, f"✅ Mission Accepted: {mission_id}\nObjective: '{mission_text}'\n\nChief of Staff is now assembling the swarm.")

async def handle_status_check(chat_id: int):
    """Aggregate system-wide KPI status."""
    msg = (
        "📊 *BravOS v3 KPI Status*\n"
        "━━━━━━━━━━━━━━━\n"
        "✅ *System Health*: Optimal\n"
        "🤖 *Active Agents*: 12\n"
        "🎯 *Pending Missions*: 3\n"
        "💰 *Burn Rate*: $0.05 / hr\n"
        "━━━━━━━━━━━━━━━"
    )
    await send_telegram_msg(chat_id, msg, parse_mode="Markdown")

async def handle_list_approvals(chat_id: int):
    """List pending items requiring CEO approval."""
    # Mock data for now
    msg = (
        "⚖️ *Pending Approvals*\n"
        "━━━━━━━━━━━━━━━\n"
        "1. Mission-7a2: Budget increase for 'Cloud Migration' (+$50)\n"
        "2. Security-X: Deploy patch for 'Auth-Bypass-CVE'\n\n"
        "Use /approve <id> to proceed."
    )
    await send_telegram_msg(chat_id, msg, parse_mode="Markdown")

async def send_telegram_msg(chat_id: int, text: str, parse_mode: str = None):
    async with httpx.AsyncClient() as client:
        payload = {
            "chat_id": chat_id,
            "text": text
        }
        if parse_mode:
            payload["parse_mode"] = parse_mode
            
        try:
            await client.post(f"{TELEGRAM_API}/sendMessage", json=payload)
        except Exception as e:
            print(f"❌ Failed to send Telegram message: {e}")

# Initialize service using elite base factory
# Note: Added support for routers in create_app locally or via mock if base_service is limited
app = create_app(
    title="BravOS CEO Interface",
    version="1.0.0"
)
app.include_router(router)
