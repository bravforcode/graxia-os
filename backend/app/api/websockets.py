import asyncio
import logging

from fastapi import APIRouter, Depends, Request, WebSocket, WebSocketDisconnect
from fastapi.security import HTTPAuthorizationCredentials
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.auth import extract_bearer_token
from app.core.errors import build_error_response
from app.core.swarm_bootstrap import GRAXIA_ENABLED, AgentMessage, message_bus
from app.database import get_db
from app.middleware.auth import get_current_user_from_token

router = APIRouter()
logger = logging.getLogger(__name__)


def _message_matches_organization(message: object, organization_id: str) -> bool:
    """Require trusted metadata to bind each event to one organization."""
    metadata = getattr(message, "metadata", None)
    if not isinstance(metadata, dict):
        return False
    message_organization_id = metadata.get("organization_id")
    if message_organization_id is None or str(message_organization_id) != organization_id:
        return False

    content = getattr(message, "content", None)
    content_organization_id = (
        content.get("organization_id") if isinstance(content, dict) else None
    )
    return content_organization_id is None or str(content_organization_id) == organization_id


@router.get("/v1/graxia/stream")
@router.get("/api/v1/stream")
@router.get("/api/v1/graxia/stream")
async def graxia_stream_requires_websocket(request: Request, token: str | None = None):
    """Reject plain HTTP access to the authenticated stream endpoint."""
    if not token:
        return build_error_response(
            request,
            code="AUTH_REQUIRED",
            message="Authentication required",
            status_code=401,
        )
    return build_error_response(
        request,
        code="AUTH_INVALID",
        message="Authentication required",
        status_code=401,
    )


@router.websocket("/v1/graxia/stream")
@router.websocket("/api/v1/stream")
@router.websocket("/api/v1/graxia/stream")
async def graxia_websocket_stream(
    websocket: WebSocket,
    token: str | None = None,
    db: AsyncSession = Depends(get_db),
):
    """Stream only events scoped to the authenticated user's organization."""
    access_token = (token or "").strip() or extract_bearer_token(
        websocket.headers.get("authorization")
    )
    credentials = (
        HTTPAuthorizationCredentials(scheme="Bearer", credentials=access_token)
        if access_token
        else None
    )
    try:
        user = await get_current_user_from_token(websocket, credentials, db)
    except Exception:
        await websocket.close(code=1008, reason="Invalid or expired token")
        return

    organization_id = getattr(user, "organization_id", None)
    if not organization_id:
        await websocket.close(code=1008, reason="Organization required")
        return
    organization_id = str(organization_id)

    if not GRAXIA_ENABLED or message_bus is None:
        await websocket.close(code=1008, reason="Graxia OS not enabled")
        return

    await websocket.accept()

    organization_topics = {
        f"organizations/{organization_id}/system_events": "thought",
        f"organizations/{organization_id}/tasks": "assignment",
        f"organizations/{organization_id}/debates": "debate",
    }
    subscriptions: list[tuple[str, asyncio.Queue, str]] = []
    for topic, category in organization_topics.items():
        queue = await message_bus.subscribe(topic)
        subscriptions.append((topic, queue, category))

    async def push_messages(q: asyncio.Queue, category: str):
        try:
            while True:
                msg: AgentMessage = await q.get()
                if not _message_matches_organization(msg, organization_id):
                    q.task_done()
                    continue
                payload = msg.model_dump(mode="json")
                payload["category"] = category
                await websocket.send_json(payload)
                q.task_done()
        except asyncio.CancelledError:
            pass
        except Exception as e:
            logger.error(f"WS push error: {e}")

    forwarders = [
        asyncio.create_task(push_messages(queue, category))
        for _, queue, category in subscriptions
    ]

    try:
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        for task in forwarders:
            task.cancel()
        for topic, queue, _ in subscriptions:
            await message_bus.unsubscribe(topic, queue)
        logger.info("Graxia WebSocket Stream Terminated.")
