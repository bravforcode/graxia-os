import asyncio
import logging
import sys
from typing import Any
import uvicorn
from fastapi import FastAPI

from core.config import settings
from core.logger import setup_logger
from core.ingestion.pipeline import AutoIngestionPipeline
from core.chunking.semantic_chunker import SemanticChunker
from core.retrieval.graph_rag import EntityExtractor
from core.providers.openai_provider import OpenAIEmbeddingProvider, OpenAIProvider
from api import app

# Setup master logger
logger = setup_logger("graxia_os_main", level=settings.LOG_LEVEL)

SYSTEM_BANNER = \"\"\"
  â–ˆâ–ˆâ–ˆâ–ˆâ–ˆâ•—  â–ˆâ–ˆâ–ˆâ–ˆâ–ˆâ–ˆâ•—  â–ˆâ–ˆâ–ˆâ–ˆâ–ˆâ•— â–ˆâ–ˆâ•—  â–ˆâ–ˆâ•— â–ˆâ–ˆâ–ˆâ–ˆâ–ˆâ•—      â–ˆâ–ˆâ–ˆâ–ˆâ–ˆâ•—  â–ˆâ–ˆâ–ˆâ–ˆâ–ˆâ–ˆâ•— 
â–ˆâ–ˆâ•”â•—â•—â•—â•—â–ˆâ–ˆâ•”â•—â•—â–ˆâ–ˆâ•—â–ˆâ–ˆâ•”â•—â•—â–ˆâ–ˆâ•—â•šâ–ˆâ–ˆâ•—â–ˆâ–ˆâ•”â•—â–ˆâ–ˆâ•”â•—â•—â–ˆâ–ˆâ•—    â–ˆâ–ˆâ•”â•—â•—â–ˆâ–ˆâ•—â–ˆâ–ˆâ•”â•—â•—â•—â–ˆâ–ˆâ•—
â–ˆâ–ˆâ•‘  â–ˆâ–ˆâ–ˆâ–ˆâ–ˆâ–ˆâ–ˆâ–ˆâ•”â•—â•‘â–ˆâ–ˆâ–ˆâ–ˆâ–ˆâ–ˆâ–ˆâ•‘ â•šâ–ˆâ–ˆâ–ˆâ•”â•  â–ˆâ–ˆâ–ˆâ–ˆâ–ˆâ–ˆâ–ˆâ•‘    â–ˆâ–ˆâ•‘   â–ˆâ–ˆâ•‘â•šâ–ˆâ–ˆâ–ˆâ–ˆâ–ˆâ–ˆâ•— 
â–ˆâ–ˆâ•‘   â–ˆâ–ˆâ•‘â–ˆâ–ˆâ•”â•—â•—â–ˆâ–ˆâ•—â–ˆâ–ˆâ•”â•—â•—â–ˆâ–ˆâ•‘ â–ˆâ–ˆâ•”â–ˆâ–ˆâ•— â–ˆâ–ˆâ•”â•—â•—â–ˆâ–ˆâ•‘    â–ˆâ–ˆâ•‘   â–ˆâ–ˆâ•‘ â•šâ•—â•—â•—â–ˆâ–ˆâ•—
â•šâ–ˆâ–ˆâ–ˆâ–ˆâ–ˆâ•”â•‘â–ˆâ–ˆâ•‘  â–ˆâ–ˆâ•‘â–ˆâ–ˆâ•‘  â–ˆâ–ˆâ•‘â–ˆâ–ˆâ•”â•— â–ˆâ–ˆâ•—â–ˆâ–ˆâ•‘  â–ˆâ–ˆâ•‘    â•šâ–ˆâ–ˆâ–ˆâ–ˆâ–ˆâ•”â•‘â–ˆâ–ˆâ–ˆâ–ˆâ–ˆâ–ˆâ•”â• 
 â•šâ•—â•—â•—â•—â•  â•šâ•—â•  â•šâ•—â• â•šâ•—â•  â•šâ•—â• â•šâ•—â•  â•šâ•—â• â•šâ•—â•  â•šâ•—â•     â•šâ•—â•—â•—â•—â•  â•šâ•—â•—â•—â•—â•—â•  
                                                                    
      â–’â–’â–’â–’â–’â–’â–’â–’â–’â–’â–’â–’â–’â–’â–’â–’â–’â–’â–’â–’â–’â–’â–’â–’â–’â–’â–’â–’â–’â–’â–’â–’â–’â–’â–’â–’â–’â–’â–’â–’â–’â–’â–’â–’â–’â–’â–’â–’â–’â–’â–’â–’â–’â–’â–’â–’â–’
      â–’                                                         â–’
      â–’         Graxia OS Intelligence Architecture v1.0         â–’
      â–’              The Zero-Touch Enterprise OS               â–’
      â–’                                                         â–’
      â–’â–’â–’â–’â–’â–’â–’â–’â–’â–’â–’â–’â–’â–’â–’â–’â–’â–’â–’â–’â–’â–’â–’â–’â–’â–’â–’â–’â–’â–’â–’â–’â–’â–’â–’â–’â–’â–’â–’â–’â–’â–’â–’â–’â–’â–’â–’â–’â–’â–’â–’â–’â–’â–’â–’â–’â–’
\"\"\"

async def initialize_components():
    \"\"\"Initializes background services and components.\"\"\"
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
    app.state.ingestion_pipeline = await initialize_components()

@app.on_event("shutdown")
async def shutdown_event():
    logger.info("Shutting down Graxia OS...")
    await app.state.ingestion_pipeline.stop()

def main():
    \"\"\"Entry point for the application.\"\"\"
    try:
        uvicorn.run(
            "main:app",
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

if __name__ == "__main__":
    main()
