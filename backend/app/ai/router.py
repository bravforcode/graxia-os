"""
AI Router - FastAPI endpoints for AI functionality
"""

import json

from fastapi import APIRouter, Depends, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.responses import StreamingResponse

from .client import AIClient, get_ai_client
from .models import (
    AgentNetworkStatus,
    AIUsageMetrics,
    ChatRequest,
    ChatResponse,
    CodeFixRequest,
    CodeFixResponse,
    CodeRequest,
    CodeResponse,
    DelegateRequest,
    DelegateResponse,
    SkillLoadRequest,
    SkillSearchRequest,
    SkillSearchResponse,
    VaultHealthMetrics,
    VaultQueryRequest,
    VaultQueryResponse,
    WSMessage,
    WSMessageType,
    WSResponse,
)
from .services.agent_service import AgentService
from .services.chat_service import ChatService
from .services.code_service import CodeService
from .services.vault_service import VaultService
from .websocket.manager import WebSocketManager

router = APIRouter()

# ═══════════════════════════════════════════════════════════════
# Services
# ═══════════════════════════════════════════════════════════════


async def get_chat_service(ai_client: AIClient = Depends(get_ai_client)) -> ChatService:
    return ChatService(ai_client)


async def get_code_service(ai_client: AIClient = Depends(get_ai_client)) -> CodeService:
    return CodeService(ai_client)


async def get_vault_service() -> VaultService:
    return VaultService()


async def get_agent_service() -> AgentService:
    return AgentService()


# ═══════════════════════════════════════════════════════════════
# Chat Endpoints
# ═══════════════════════════════════════════════════════════════


@router.post("/chat", response_model=ChatResponse)
async def chat(request: ChatRequest, service: ChatService = Depends(get_chat_service)):
    """Send a chat message to AI with vault context"""
    try:
        response = await service.chat(request)
        return response
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/chat/stream")
async def chat_stream(request: ChatRequest, service: ChatService = Depends(get_chat_service)):
    """Stream chat response"""

    async def generate():
        async for chunk in service.stream_chat(request):
            yield f"data: {json.dumps({'content': chunk})}\n\n"
        yield "data: [DONE]\n\n"

    return StreamingResponse(generate(), media_type="text/event-stream")


# ═══════════════════════════════════════════════════════════════
# Code Endpoints
# ═══════════════════════════════════════════════════════════════


@router.post("/code/generate", response_model=CodeResponse)
async def generate_code(request: CodeRequest, service: CodeService = Depends(get_code_service)):
    """Generate code with AI"""
    try:
        response = await service.generate(request)
        return response
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/code/fix", response_model=CodeFixResponse)
async def fix_code(request: CodeFixRequest, service: CodeService = Depends(get_code_service)):
    """Fix code with AI"""
    try:
        response = await service.fix(request)
        return response
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/code/explain")
async def explain_code(
    code: str, language: str | None = None, service: CodeService = Depends(get_code_service)
):
    """Explain what code does"""
    try:
        explanation = await service.explain(code, language)
        return {"explanation": explanation}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ═══════════════════════════════════════════════════════════════
# Vault Integration Endpoints
# ═══════════════════════════════════════════════════════════════


@router.post("/vault/query", response_model=VaultQueryResponse)
async def query_vault(
    request: VaultQueryRequest, service: VaultService = Depends(get_vault_service)
):
    """Query Obsidian vault"""
    try:
        response = await service.query(request)
        return response
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/vault/file/{file_path:path}")
async def get_vault_file(file_path: str, service: VaultService = Depends(get_vault_service)):
    """Get a specific vault file"""
    try:
        content = await service.get_file(file_path)
        return {"path": file_path, "content": content}
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail=f"File not found: {file_path}")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/vault/search")
async def search_vault(
    query: str, limit: int = 10, service: VaultService = Depends(get_vault_service)
):
    """Search vault content"""
    try:
        results = await service.search(query, limit)
        return {"query": query, "results": results}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/vault/stats", response_model=VaultHealthMetrics)
async def vault_stats(service: VaultService = Depends(get_vault_service)):
    """Get vault health metrics"""
    try:
        stats = await service.get_stats()
        return stats
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ═══════════════════════════════════════════════════════════════
# Agent Network Endpoints
# ═══════════════════════════════════════════════════════════════


@router.post("/agent/delegate", response_model=DelegateResponse)
async def delegate_task(
    request: DelegateRequest, service: AgentService = Depends(get_agent_service)
):
    """Delegate task to an agent"""
    try:
        response = await service.delegate(request)
        return response
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/agent/status", response_model=AgentNetworkStatus)
async def agent_status(service: AgentService = Depends(get_agent_service)):
    """Get agent network status"""
    try:
        status = await service.get_network_status()
        return status
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/agent/{agent_name}/command")
async def agent_command(
    agent_name: str, command: str, service: AgentService = Depends(get_agent_service)
):
    """Send command to specific agent"""
    try:
        result = await service.send_command(agent_name, command)
        return {"agent": agent_name, "command": command, "result": result}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ═══════════════════════════════════════════════════════════════
# Skills Endpoints
# ═══════════════════════════════════════════════════════════════


@router.post("/skills/search", response_model=SkillSearchResponse)
async def search_skills(
    request: SkillSearchRequest, service: VaultService = Depends(get_vault_service)
):
    """Search skills registry"""
    try:
        results = await service.search_skills(request)
        return results
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/skills/load")
async def load_skill(request: SkillLoadRequest, service: VaultService = Depends(get_vault_service)):
    """Load a specific skill"""
    try:
        skill = await service.load_skill(request.skill_id, request.include_content)
        return skill
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/skills/categories")
async def get_skill_categories(service: VaultService = Depends(get_vault_service)):
    """Get all skill categories"""
    try:
        categories = await service.get_skill_categories()
        return categories
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ═══════════════════════════════════════════════════════════════
# Auto-System Endpoints
# ═══════════════════════════════════════════════════════════════


@router.post("/auto/classify")
async def auto_classify(
    dry_run: bool = True, max_files: int = 50, service: VaultService = Depends(get_vault_service)
):
    """Run auto classifier"""
    try:
        result = await service.auto_classify(dry_run, max_files)
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/auto/link")
async def auto_link(
    dry_run: bool = True, limit: int = 100, service: VaultService = Depends(get_vault_service)
):
    """Run auto linker"""
    try:
        result = await service.auto_link(dry_run, limit)
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/auto/optimize")
async def auto_optimize(service: VaultService = Depends(get_vault_service)):
    """Run full vault optimization"""
    try:
        result = await service.optimize_all()
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ═══════════════════════════════════════════════════════════════
# Analytics Endpoints
# ═══════════════════════════════════════════════════════════════


@router.get("/analytics/usage", response_model=AIUsageMetrics)
async def ai_usage_metrics():
    """Get AI usage metrics"""
    # TODO: Implement metrics tracking
    return AIUsageMetrics(
        total_requests=0,
        total_tokens_used=0,
        average_response_time_ms=0.0,
        models_used={},
        errors_count=0,
        top_queries=[],
    )


# ═══════════════════════════════════════════════════════════════
# WebSocket Endpoint
# ═══════════════════════════════════════════════════════════════

ws_manager = WebSocketManager()


@router.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    """WebSocket for real-time AI communication"""
    await ws_manager.connect(websocket)
    try:
        while True:
            data = await websocket.receive_text()
            message = WSMessage.parse_raw(data)

            # Process message based on type
            if message.type == WSMessageType.CHAT:
                response = await ws_manager.handle_chat(message)
            elif message.type == WSMessageType.CODE_REQUEST:
                response = await ws_manager.handle_code_request(message)
            elif message.type == WSMessageType.VAULT_SEARCH:
                response = await ws_manager.handle_vault_search(message)
            elif message.type == WSMessageType.AGENT_COMMAND:
                response = await ws_manager.handle_agent_command(message)
            else:
                response = WSResponse(
                    type=WSMessageType.ERROR,
                    request_id=message.id,
                    payload={"error": f"Unknown message type: {message.type}"},
                )

            await websocket.send_text(response.json())

    except WebSocketDisconnect:
        ws_manager.disconnect(websocket)
    except Exception as e:
        error_response = WSResponse(type=WSMessageType.ERROR, payload={"error": str(e)})
        await websocket.send_text(error_response.json())
        ws_manager.disconnect(websocket)


# ═══════════════════════════════════════════════════════════════
# Health Check
# ═══════════════════════════════════════════════════════════════


@router.get("/health")
async def health_check():
    """AI module health check"""
    return {
        "status": "healthy",
        "version": "1.0.0",
        "features": {
            "chat": True,
            "code_generation": True,
            "vault_integration": True,
            "agent_network": True,
            "skills": True,
        },
    }
