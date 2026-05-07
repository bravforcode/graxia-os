import asyncio
import logging
import os

from app.config import settings

logger = logging.getLogger(__name__)

GRAXIA_ENABLED = os.getenv("GRAXIA_ENABLED", "false").lower() == "true"
swarm = None
chief = None
message_bus = None
AgentMessage = None

if GRAXIA_ENABLED:
    try:
        import sys
        from pathlib import Path

        # Add parent directory to Python path for core module access
        sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

        from core.chunking.semantic_chunker import SemanticChunker
        from core.execution.message_bus import AgentMessage as _AgentMessage
        from core.execution.message_bus import message_bus as _message_bus
        from core.execution.real_swarm import RealSwarmOrchestrator
        from core.ingestion.pipeline import AutoIngestionPipeline
        from core.providers.openai_provider import OpenAIEmbeddingProvider, OpenAIProvider
        from core.retrieval.graph_rag import EntityExtractor
        from core.routing.task_delegator import ChiefOrchestrator

        message_bus = _message_bus
        AgentMessage = _AgentMessage
        swarm = RealSwarmOrchestrator()
        chief = ChiefOrchestrator()

        logger.info("Graxia OS components loaded successfully")
    except ImportError as e:
        logger.warning(f"Graxia OS components not available: {e}")
        logger.warning("Running in Brav OS standalone mode")
        GRAXIA_ENABLED = False
else:
    logger.info("Graxia OS disabled, running in Brav OS standalone mode")


async def initialize_graxia_components():
    """Initializes Graxia OS background services and components."""
    if not GRAXIA_ENABLED:
        logger.info("Graxia OS disabled, skipping initialization")
        return None

    logger.info("Initializing Graxia OS Intelligence components...")

    try:
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

        logger.info("Graxia OS background services initialized.")
        return pipeline
    except Exception as e:
        logger.error(f"Failed to initialize Graxia OS components: {e}")
        return None
