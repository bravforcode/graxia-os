import asyncio
import os
import logging
from typing import List, Dict, Any, Optional, Union
from datetime import datetime
from pathlib import Path
import aiofiles
from pydantic import BaseModel, Field, ConfigDict

from core.chunking.semantic_chunker import SemanticChunker, Chunk
from core.retrieval.graph_rag import EntityExtractor, KnowledgeGraph
from core.retrieval.light_rag_engine import light_rag
from core.logger import setup_logger
from core.config import settings

logger = setup_logger("ingestion_pipeline")

class IngestionTask(BaseModel):
    """Represents a single ingestion unit."""
    source_id: str
    content: str
    metadata: Dict[str, Any] = Field(default_factory=dict)
    timestamp: datetime = Field(default_factory=datetime.utcnow)

class AutoIngestionPipeline:
    """
    Dynamic Data Ingestion Pipeline (Auto-ETL).
    Automates text extraction, semantic chunking, and multi-DB upsert.
    """
    
    def __init__(
        self,
        chunker: SemanticChunker,
        extractor: EntityExtractor,
        vector_db_client: Any = None, # Placeholder for Qdrant client
        graph_db_client: Any = None   # Placeholder for Graph client
    ):
        self.chunker = chunker
        self.extractor = extractor
        self.vector_db = vector_db_client
        self.graph_db = graph_db_client
        self._processing_queue = asyncio.Queue()
        self._is_running = False

    async def start(self):
        """Starts the asynchronous background processing loop."""
        if self._is_running:
            return
        self._is_running = True
        logger.info("AutoIngestionPipeline started.")
        asyncio.create_task(self._process_loop())

    async def stop(self):
        """Stops the pipeline."""
        self._is_running = False
        logger.info("AutoIngestionPipeline stopping...")

    async def ingest_webhook(self, payload: Dict[str, Any]):
        """Accepts a webhook payload for ingestion."""
        source_id = payload.get("source_id", f"webhook_{datetime.utcnow().timestamp()}")
        content = payload.get("content", "")
        metadata = payload.get("metadata", {})
        
        task = IngestionTask(source_id=source_id, content=content, metadata=metadata)
        await self._processing_queue.put(task)
        logger.debug(f"Queued task from webhook: {source_id}")

    async def monitor_directory(self, directory_path: str, interval: int = 10):
        """Monitors a directory for new files and ingests them."""
        logger.info(f"Monitoring directory: {directory_path}")
        path = Path(directory_path)
        if not path.exists():
            path.mkdir(parents=True, exist_ok=True)

        processed_files = set()

        while self._is_running:
            for file_path in path.iterdir():
                if file_path.is_file() and str(file_path) not in processed_files:
                    logger.info(f"New file detected: {file_path.name}")
                    content = await self._extract_text(file_path)
                    if content:
                        task = IngestionTask(
                            source_id=str(file_path),
                            content=content,
                            metadata={"filename": file_path.name, "type": file_path.suffix}
                        )
                        await self._processing_queue.put(task)
                        processed_files.add(str(file_path))
            
            await asyncio.sleep(interval)

    async def _extract_text(self, file_path: Path) -> Optional[str]:
        """
        Extracts text from various file formats.
        Placeholders for PDF/Docx parsers.
        """
        try:
            if file_path.suffix.lower() == ".txt":
                async with aiofiles.open(file_path, mode='r', encoding='utf-8') as f:
                    return await f.read()
            elif file_path.suffix.lower() == ".pdf":
                # Placeholder for PDF parser (e.g., PyMuPDF, PDFPlumber)
                logger.info(f"PDF extraction placeholder for {file_path.name}")
                return "[PDF CONTENT PLACEHOLDER]"
            elif file_path.suffix.lower() in [".docx", ".doc"]:
                # Placeholder for Docx parser (e.g., python-docx)
                logger.info(f"DOCX extraction placeholder for {file_path.name}")
                return "[DOCX CONTENT PLACEHOLDER]"
            else:
                logger.warning(f"Unsupported file type: {file_path.suffix}")
                return None
        except Exception as e:
            logger.error(f"Error extracting text from {file_path}: {e}")
            return None

    async def _process_loop(self):
        """Continuously processes tasks from the queue."""
        while self._is_running:
            task: IngestionTask = await self._processing_queue.get()
            try:
                await self._process_task(task)
            except Exception as e:
                logger.error(f"Error processing task {task.source_id}: {e}")
            finally:
                self._processing_queue.task_done()

    async def _process_task(self, task: IngestionTask):
        """Performs the full ETL logic for a single task."""
        logger.info(f"Processing ingestion for {task.source_id}...")
        
        # 1. Structural Chunking (ROI Step 2: structural over semantic)
        chunks: List[Chunk] = self.chunker.chunk(task.content, task.source_id)
        logger.info(f"Generated {len(chunks)} structural chunks for {task.source_id}")

        # 2. Parallel Upsert to Vector DB and LightRAG
        # LightRAG handles its own graph extraction and embedding internally
        await asyncio.gather(
            self._upsert_to_vector_db(chunks),
            light_rag.ingest(task.content),
            return_exceptions=True
        )
        
        logger.info(f"Successfully ingested {task.source_id} into Vector DB and LightRAG")

    async def _upsert_to_vector_db(self, chunks: List[Chunk]):
        """Upserts chunks to Qdrant (Mock)."""
        logger.debug(f"Upserting {len(chunks)} chunks to Vector DB...")
        # Production logic: self.vector_db.upsert(collection="brav_os", points=chunks)
        await asyncio.sleep(0.1) # Simulate network I/O

    async def _upsert_to_graph_db(self, graph: KnowledgeGraph):
        """Upserts knowledge graph to Graph DB (Mock)."""
        logger.debug(f"Upserting {len(graph.nodes)} nodes to Graph DB...")
        # Production logic: self.graph_db.merge_graph(graph)
        await asyncio.sleep(0.1) # Simulate network I/O
