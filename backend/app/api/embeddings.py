"""
Embedding API endpoints
POST /api/v1/embeddings - Generate embeddings for texts
"""

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from app.services.embedding_service import get_embedding_service

router = APIRouter(prefix="/api/v1/embeddings", tags=["embeddings"])


class EmbeddingRequest(BaseModel):
    """Request model for embedding generation."""

    texts: list[str] = Field(..., min_items=1, max_items=100, description="Texts to embed")
    use_cache: bool = Field(default=True, description="Whether to use Redis cache")

    model_config = {
        "json_schema_extra": {
            "example": {"texts": ["Hello world", "Test embedding"], "use_cache": True}
        }
    }


class EmbeddingResponse(BaseModel):
    """Response model for embedding generation."""

    embeddings: list[list[float]]
    model: str
    dimension: int
    cached: bool = False

    model_config = {
        "json_schema_extra": {
            "example": {
                "embeddings": [[0.1, 0.2, 0.3]],
                "model": "nomic-embed-text",
                "dimension": 768,
                "cached": False,
            }
        }
    }


class EmbeddingErrorResponse(BaseModel):
    """Error response model."""

    error: dict

    model_config = {
        "json_schema_extra": {
            "example": {
                "error": {"code": "embedding_failed", "message": "Failed to generate embeddings"}
            }
        }
    }


@router.post(
    "",
    response_model=EmbeddingResponse,
    responses={
        200: {"model": EmbeddingResponse},
        400: {"model": EmbeddingErrorResponse},
        422: {"model": EmbeddingErrorResponse},
        500: {"model": EmbeddingErrorResponse},
    },
)
async def create_embeddings(request: EmbeddingRequest):
    """
    Generate embeddings for a list of texts.

    - Uses nomic-embed-text (768-dim) via Ollama by default
    - Falls back to OpenAI text-embedding-3-small if Ollama fails
    - Results are cached in Redis for 24 hours
    """
    try:
        service = await get_embedding_service()
        embeddings = await service.generate(texts=request.texts, use_cache=request.use_cache)

        return EmbeddingResponse(
            embeddings=embeddings,
            model=service.model,
            dimension=service.dimension,
            cached=False,  # Simplified - actual cache tracking would check Redis
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except RuntimeError as e:
        raise HTTPException(status_code=503, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Embedding generation failed: {str(e)}")


@router.get("/health")
async def embedding_health():
    """Health check for embedding service."""
    try:
        service = await get_embedding_service()
        return {
            "status": "healthy",
            "model": service.model,
            "dimension": service.dimension,
            "providers": {
                "ollama_available": True,  # Simplified
                "openai_available": bool(service.openai_key),
            },
        }
    except Exception as e:
        raise HTTPException(status_code=503, detail=f"Service unhealthy: {str(e)}")
