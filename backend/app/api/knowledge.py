"""
Knowledge Base API endpoints
"""

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db as get_async_session
from app.services.knowledge_service import get_knowledge_service

router = APIRouter(prefix="/api/v1/knowledge", tags=["knowledge"])


# ═════════════════════════════════════════════════════════════════════════════
# Request/Response Models
# ═════════════════════════════════════════════════════════════════════════════


class DocumentIngestRequest(BaseModel):
    """Request model for document ingestion."""

    title: str = Field(..., min_length=1, max_length=500)
    content: str = Field(..., min_length=1, max_length=100000)
    source: str = Field(default="api", description="Source of the document")
    tags: list[str] = Field(default_factory=list, max_length=50)

    model_config = {
        "json_schema_extra": {
            "example": {
                "title": "Project Documentation",
                "content": "This is a sample document content...",
                "source": "api",
                "tags": ["documentation", "project"],
            }
        }
    }


class DocumentIngestResponse(BaseModel):
    """Response model for document ingestion."""

    document_id: UUID
    status: str
    chunks_created: int

    model_config = {
        "json_schema_extra": {
            "example": {
                "document_id": "123e4567-e89b-12d3-a456-426614174000",
                "status": "ingested",
                "chunks_created": 5,
            }
        }
    }


class SearchRequest(BaseModel):
    """Request model for knowledge search."""

    query: str = Field(..., min_length=1, max_length=1000)
    top_k: int = Field(default=5, ge=1, le=50)
    rerank_to: int | None = Field(default=None, ge=1, le=20)

    model_config = {
        "json_schema_extra": {
            "example": {"query": "How does the system handle errors?", "top_k": 5, "rerank_to": 3}
        }
    }


class SearchResult(BaseModel):
    """Single search result."""

    content: str
    similarity: float
    document_id: UUID | None = None
    chunk_index: int | None = None


class SearchResponse(BaseModel):
    """Response model for knowledge search."""

    results: list[SearchResult]
    total_found: int
    query: str

    model_config = {
        "json_schema_extra": {
            "example": {
                "results": [
                    {
                        "content": "The system uses structured logging...",
                        "similarity": 0.92,
                        "document_id": "123e4567-e89b-12d3-a456-426614174000",
                        "chunk_index": 0,
                    }
                ],
                "total_found": 5,
                "query": "How does the system handle errors?",
            }
        }
    }


class ContextRequest(BaseModel):
    """Request model for context formatting."""

    query: str = Field(..., min_length=1, max_length=1000)
    max_tokens: int = Field(default=2000, ge=100, le=8000)
    top_k: int = Field(default=5, ge=1, le=50)

    model_config = {
        "json_schema_extra": {
            "example": {"query": "Explain the architecture", "max_tokens": 2000, "top_k": 5}
        }
    }


class ContextResponse(BaseModel):
    """Response model for context formatting."""

    context: str
    sources_used: int
    estimated_tokens: int

    model_config = {
        "json_schema_extra": {
            "example": {
                "context": "[Relevance: 0.95]\\nSystem architecture...",
                "sources_used": 3,
                "estimated_tokens": 450,
            }
        }
    }


class ErrorResponse(BaseModel):
    """Error response model."""

    error: dict

    model_config = {
        "json_schema_extra": {
            "example": {
                "error": {"code": "search_failed", "message": "Failed to search knowledge base"}
            }
        }
    }


# ═════════════════════════════════════════════════════════════════════════════
# API Endpoints
# ═════════════════════════════════════════════════════════════════════════════


@router.post(
    "/documents",
    response_model=DocumentIngestResponse,
    responses={
        201: {"model": DocumentIngestResponse},
        400: {"model": ErrorResponse},
        422: {"model": ErrorResponse},
        500: {"model": ErrorResponse},
    },
    status_code=201,
)
async def ingest_document(
    request: DocumentIngestRequest, db: AsyncSession = Depends(get_async_session)
):
    """
    Ingest a document into the knowledge base.

    The document will be:
    - Split into semantic chunks
    - Embedded using the configured embedding model
    - Stored in the knowledge base with vector search capabilities
    """
    try:
        service = await get_knowledge_service()

        # Note: Chunk counting would require chunking first, simplified here
        doc_id = await service.ingest_document(
            db=db,
            title=request.title,
            content=request.content,
            source=request.source,
            tags=request.tags,
        )

        # Estimate chunks (rough approximation)
        estimated_chunks = max(1, len(request.content) // 500)

        return DocumentIngestResponse(
            document_id=doc_id, status="ingested", chunks_created=estimated_chunks
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Document ingestion failed: {str(e)}")


@router.post(
    "/search",
    response_model=SearchResponse,
    responses={
        200: {"model": SearchResponse},
        400: {"model": ErrorResponse},
        422: {"model": ErrorResponse},
        500: {"model": ErrorResponse},
    },
)
async def search_knowledge(request: SearchRequest, db: AsyncSession = Depends(get_async_session)):
    """
    Search the knowledge base using semantic similarity.

    - Converts query to embedding vector
    - Searches vector database for similar content
    - Optional reranking for better relevance
    """
    try:
        service = await get_knowledge_service()
        results = await service.search(
            db=db, query=request.query, top_k=request.top_k, rerank_to=request.rerank_to
        )

        return SearchResponse(
            results=[
                SearchResult(
                    content=r.get("content", ""),
                    similarity=r.get("similarity", 0.0),
                    document_id=r.get("document_id"),
                    chunk_index=r.get("chunk_index"),
                )
                for r in results
            ],
            total_found=len(results),
            query=request.query,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Search failed: {str(e)}")


@router.post(
    "/context",
    response_model=ContextResponse,
    responses={
        200: {"model": ContextResponse},
        400: {"model": ErrorResponse},
        422: {"model": ErrorResponse},
        500: {"model": ErrorResponse},
    },
)
async def get_context(request: ContextRequest, db: AsyncSession = Depends(get_async_session)):
    """
    Get formatted context for LLM consumption.

    - Searches knowledge base
    - Formats results as structured context
    - Respects token budget
    """
    try:
        service = await get_knowledge_service()

        # Search
        results = await service.search(db=db, query=request.query, top_k=request.top_k)

        # Format as context
        context = await service.format_as_context(results, max_tokens=request.max_tokens)

        # Estimate tokens (rough approximation)
        estimated_tokens = len(context.split())

        return ContextResponse(
            context=context, sources_used=len(results), estimated_tokens=estimated_tokens
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Context generation failed: {str(e)}")


@router.get("/health")
async def knowledge_health():
    """Health check for knowledge service."""
    try:
        await get_knowledge_service()
        return {"status": "healthy", "service": "knowledge"}
    except Exception as e:
        raise HTTPException(status_code=503, detail=f"Service unhealthy: {str(e)}")
