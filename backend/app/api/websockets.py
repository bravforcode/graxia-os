import asyncio
import logging

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from app.core.swarm_bootstrap import GRAXIA_ENABLED, AgentMessage, message_bus

logger = logging.getLogger(__name__)
router = APIRouter()

@router.websocket("/v1/graxia/stream")
async def graxia_websocket_stream(websocket: WebSocket, token: str | None = None):
    """Real-time thought and event stream from the Graxia Swarm. Requires bearer token."""
    # Validate token BEFORE accept â€” rejecting before accept costs nothing
    if not token:
        await websocket.close(code=1008, reason="Authentication required: pass ?token=<bearer>")
        return
    try:
        from app.core.auth import decode_access_token

        payload = decode_access_token(token)
        if not payload or not payload.get("sub"):
            await websocket.close(code=1008, reason="Invalid or expired token")
            return
    except Exception:
        await websocket.close(code=1008, reason="Invalid or expired token")
        return

    if not GRAXIA_ENABLED or message_bus is None:
        await websocket.close(code=1008, reason="Graxia OS not enabled")
        return

    await websocket.accept()

    # Subscribe to multiple topics for full visibility
    events_queue = await message_bus.subscribe("system_events")
    tasks_queue = await message_bus.subscribe("tasks")
    debates_queue = await message_bus.subscribe("debates")

    async def push_messages(q: asyncio.Queue, category: str):
        try:
            while True:
                msg: AgentMessage = await q.get()
                payload = msg.model_dump(mode="json")
                payload["category"] = category
                await websocket.send_json(payload)
                q.task_done()
        except asyncio.CancelledError:
            pass
        except Exception as e:
            logger.error(f"WS push error: {e}")

    # Forward thoughts in parallel
    forward_events = asyncio.create_task(push_messages(events_queue, "thought"))
    forward_tasks = asyncio.create_task(push_messages(tasks_queue, "assignment"))
    forward_debates = asyncio.create_task(push_messages(debates_queue, "debate"))

    try:
        while True:
            # Maintain connection
            _ = await websocket.receive_text()
    except WebSocketDisconnect:
        # Cleanup subscriptions on disconnect
        forward_events.cancel()
        forward_tasks.cancel()
        forward_debates.cancel()
        await message_bus.unsubscribe("system_events", events_queue)
        await message_bus.unsubscribe("tasks", tasks_queue)
        await message_bus.unsubscribe("debates", debates_queue)
        logger.info("Graxia WebSocket Stream Terminated.")
