"""
WebSocket Manager - Handles real-time WebSocket connections
"""

from typing import Any

from fastapi import WebSocket

from ..client import get_ai_client
from ..models import ChatMessage, WSMessage, WSMessageType, WSResponse
from ..services.vault_service import VaultService


class WebSocketManager:
    """Manages WebSocket connections for real-time AI communication"""

    def __init__(self):
        self.active_connections: list[WebSocket] = []
        self.vault_service = VaultService()

    async def connect(self, websocket: WebSocket):
        """Accept new WebSocket connection"""
        await websocket.accept()
        self.active_connections.append(websocket)

    def disconnect(self, websocket: WebSocket):
        """Remove WebSocket connection"""
        if websocket in self.active_connections:
            self.active_connections.remove(websocket)

    async def broadcast(self, message: WSResponse):
        """Broadcast message to all connected clients"""
        for connection in self.active_connections:
            try:
                await connection.send_text(message.json())
            except:
                pass

    async def handle_chat(self, message: WSMessage) -> WSResponse:
        """Handle chat message via WebSocket"""

        payload = message.payload
        messages_data = payload.get("messages", [])

        # Convert to ChatMessage objects
        messages = [
            ChatMessage(role=m.get("role", "user"), content=m.get("content", ""))
            for m in messages_data
        ]

        # Get AI client
        ai_client = await get_ai_client()

        try:
            result = await ai_client.chat(
                messages=messages,
                model=payload.get("model", "auto"),
                temperature=payload.get("temperature", 0.7),
            )

            return WSResponse(
                type=WSMessageType.CHAT,
                request_id=message.id,
                payload={
                    "content": result["content"],
                    "model_used": result.get("model_used"),
                    "tokens_used": result.get("tokens_used"),
                },
                done=True,
            )

        except Exception as e:
            return WSResponse(
                type=WSMessageType.ERROR,
                request_id=message.id,
                payload={"error": str(e)},
                done=True,
            )

    async def handle_code_request(self, message: WSMessage) -> WSResponse:
        """Handle code generation request via WebSocket"""

        payload = message.payload

        # Get AI client
        ai_client = await get_ai_client()

        try:
            result = await ai_client.generate_code(
                prompt=payload.get("prompt", ""),
                language=payload.get("language", "python"),
                context=payload.get("context"),
                existing_code=payload.get("existing_code"),
            )

            return WSResponse(
                type=WSMessageType.CODE_REQUEST,
                request_id=message.id,
                payload={
                    "code": result["code"],
                    "explanation": result.get("explanation", ""),
                    "model_used": result.get("model_used"),
                },
                done=True,
            )

        except Exception as e:
            return WSResponse(
                type=WSMessageType.ERROR,
                request_id=message.id,
                payload={"error": str(e)},
                done=True,
            )

    async def handle_vault_search(self, message: WSMessage) -> WSResponse:
        """Handle vault search request via WebSocket"""

        payload = message.payload
        query = payload.get("query", "")
        limit = payload.get("limit", 10)

        try:
            results = await self.vault_service.search(query, limit)

            return WSResponse(
                type=WSMessageType.VAULT_SEARCH,
                request_id=message.id,
                payload={"query": query, "total": len(results), "results": results},
                done=True,
            )

        except Exception as e:
            return WSResponse(
                type=WSMessageType.ERROR,
                request_id=message.id,
                payload={"error": str(e)},
                done=True,
            )

    async def handle_agent_command(self, message: WSMessage) -> WSResponse:
        """Handle agent command via WebSocket"""

        payload = message.payload
        agent = payload.get("agent")
        command = payload.get("command")

        # This would route to agent service
        return WSResponse(
            type=WSMessageType.AGENT_COMMAND,
            request_id=message.id,
            payload={
                "agent": agent,
                "command": command,
                "status": "received",
                "message": f"Command sent to {agent}",
            },
            done=True,
        )

    async def send_progress(self, websocket: WebSocket, progress: dict[str, Any]):
        """Send progress update to specific client"""

        response = WSResponse(type=WSMessageType.PROGRESS, payload=progress, done=False)

        try:
            await websocket.send_text(response.json())
        except:
            pass
