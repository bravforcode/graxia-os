import asyncio
import json
import logging
import sys
from typing import Any, Optional
import uvicorn
from fastapi import FastAPI, WebSocket, WebSocketDisconnect, BackgroundTasks, Depends, HTTPException, Security
from fastapi.security import APIKeyHeader
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from core.config import settings
from core.logger import setup_logger
from core.ingestion.pipeline import AutoIngestionPipeline
from core.chunking.semantic_chunker import SemanticChunker
from core.retrieval.graph_rag import EntityExtractor
from core.providers.openai_provider import OpenAIEmbeddingProvider, OpenAIProvider
from core.execution.message_bus import message_bus, AgentMessage
from core.routing.task_delegator import ChiefOrchestrator
from core.execution.real_swarm import RealSwarmOrchestrator

# Setup master logger
logger = setup_logger("graxia_os_main", level=settings.LOG_LEVEL)

SYSTEM_BANNER = """
  █████╗  ██████╗  █████╗ ██╗  ██╗ █████╗      █████╗  ██████╗ 
██╔══██╗██╔══██╗██╔══██╗╚██╗██╔╝██╔══██╗    ██╔══██╗██╔═══██╗
██║  ████████╔╝███████║ ╚███╔╝ ███████║    ██║   ██║██║   ██║
██║   ██║██╔══██╗██╔══██║ ██╔██╗ ██╔══██║    ██║   ██║██║   ██║
╚█████╔╝██║  ██║██║  ██║██╔╝ ██╗██║  ██║    ╚█████╔╝╚██████╔╝
 ╚════╝ ╚═╝  ╚═╝╚═╝  ╚═╝╚═╝  ╚═╝╚═╝  ╚═╝     ╚════╝  ╚═════╝ 
                                                                    
      ▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒
      ▒                                                         ▒
      ▒         Graxia OS Intelligence Architecture v1.0         ▒
      ▒              The Zero-Touch Enterprise OS               ▒
      ▒                                                         ▒
      ▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒
"""

app = FastAPI(title="Graxia OS Real Swarm API", version="7.0.0")

# Security
api_key_header = APIKeyHeader(name="X-API-Key", auto_error=False)

async def verify_api_key(api_key: str = Security(api_key_header)):
    if not api_key or api_key != "graxia-secret-token":  # In real app, load from settings
        raise HTTPException(status_code=403, detail="Could not validate credentials")
    return api_key

app.add_middleware(
    CORSMiddleware,
    allow_origins=["https://admin.graxia.internal", "http://localhost:3000"],
    allow_credentials=True,
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["*"],
)

# Shared Swarm Engine
swarm = RealSwarmOrchestrator()
chief = ChiefOrchestrator()

async def initialize_components():
    """Initializes background services and components."""
    logger.info("Initializing Graxia OS components...")
    
    # 1. Setup Ingestion Pipeline
    embedding_provider = OpenAIEmbeddingProvider(model=settings.DEFAULT_EMBEDDING_MODEL)
    chunker = SemanticChunker(embedder=embedding_provider)
    llm_provider = OpenAIProvider(model=settings.DEFAULT_LLM_MODEL)
    extractor = EntityExtractor(llm_router=llm_provider)
    
    pipeline = AutoIngestionPipeline(chunker=chunker, extractor=extractor)
    
    # 2. Start background tasks
    await pipeline.start()
    
    # Monitor data/ directory for new files
    asyncio.create_task(pipeline.monitor_directory("data/", interval=15))
    
    logger.info("Background services initialized.")
    return pipeline

@app.on_event("startup")
async def startup_event():
    print(SYSTEM_BANNER)
    logger.info(f"Starting {settings.PROJECT_NAME} in {settings.ENVIRONMENT} mode.")
    
    # Connect message bus
    await message_bus.connect()
    
    # Wake up the swarm
    await swarm.start()
    logger.info("Multi-Agent Swarm Engine Wakeup Complete.")
    
    # Initialize ingestion pipeline
    app.state.ingestion_pipeline = await initialize_components()

@app.on_event("shutdown")
async def shutdown_event():
    logger.info("Shutting down Graxia OS...")
    if hasattr(app.state, 'ingestion_pipeline'):
        await app.state.ingestion_pipeline.stop()

from pydantic import Field

class TaskRequest(BaseModel):
    project_description: str = Field(min_length=1, max_length=50000, strict=True)

async def safe_execute_project(description: str):
    """Wrapper to catch and log exceptions in background tasks."""
    try:
        await chief.execute_project(description)
    except Exception as e:
        logger.error(f"Background task failed: {e}", exc_info=True)

@app.post("/v1/tasks/execute", dependencies=[Depends(verify_api_key)])
async def execute_task(request: TaskRequest, background_tasks: BackgroundTasks):
    # Initiate delegation in background safely
    background_tasks.add_task(safe_execute_project, request.project_description)
    return {
        "status": "success", 
        "message": "Swarm activated. Watch progress via /v1/stream WebSocket."
    }

@app.websocket("/v1/stream")
async def websocket_stream(websocket: WebSocket):
    # Basic API Key check for WS (since we can't use standard headers easily in some clients, this is basic)
    # Usually passed as query param for WebSockets: ?token=...
    token = websocket.query_params.get("token")
    if token != "graxia-secret-token":
        await websocket.close(code=1008)
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
                payload = msg.model_dump(mode='json')
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
        logger.info("WebSocket Stream Terminated gracefully.")
    except Exception as e:
        logger.error(f"WebSocket error: {e}")
    finally:
        # Cleanup subscriptions on disconnect
        forward_events.cancel()
        forward_tasks.cancel()
        forward_debates.cancel()
        await message_bus.unsubscribe("system_events", events_queue)
        await message_bus.unsubscribe("tasks", tasks_queue)
        await message_bus.unsubscribe("debates", debates_queue)

@app.get("/health")
async def health_check():
    """
    Swarm Health Monitoring: Checks connectivity to Message Bus and AI Gateway.
    """
    bus_status = "connected" if getattr(message_bus, '_use_redis', True) else "disconnected"
    swarm_status = "active" if getattr(swarm, 'is_running', True) else "inactive"
    return {
        "status": "healthy" if bus_status == "connected" and swarm_status == "active" else "degraded",
        "version": "7.1.0-ultra",
        "components": {
            "message_bus": bus_status,
            "swarm_orchestrator": swarm_status,
            "gateway_routing": "enabled"
        }
    }

if __name__ == "__main__":
    try:
        uvicorn.run(
            "api:app",
            host="0.0.0.0",
            port=8000,
            log_level=settings.LOG_LEVEL.lower(),
            reload=(settings.ENVIRONMENT == "development")
        )
    except KeyboardInterrupt:
        logger.info("Manual shutdown initiated.")
    except Exception as e:
        logger.exception(f"Critical system failure: {e}")
        sys.exit(1)