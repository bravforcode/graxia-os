from fastapi import FastAPI, HTTPException, UploadFile, File, Form
from pydantic import BaseModel
from typing import List, Optional, Dict, Any
import os
import uuid
import numpy as np

# Note: In a real project, add `qdrant-client` to requirements.txt
try:
    from qdrant_client import QdrantClient
    from qdrant_client.models import Distance, VectorParams, PointStruct
    QDRANT_AVAILABLE = True
except ImportError:
    QDRANT_AVAILABLE = False

# We'll use our stub embedding from semantic cache for now
import sys
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '../../')))
try:
    from packages.bravos_core.python.semantic_cache import generate_embedding
except ImportError:
    # Fallback stub if not found
    def generate_embedding(text: str) -> np.ndarray:
        import hashlib
        h = hashlib.md5(text.encode()).digest()
        np.random.seed(int.from_bytes(h, 'little') % (2**32 - 1))
        return np.random.rand(1536)

app = FastAPI(title="BravOS Knowledge API (RAG)", version="1.0.0")

class SearchQuery(BaseModel):
    query: str
    tenant_id: str
    limit: int = 5
    min_score: float = 0.70

class SearchResult(BaseModel):
    id: str
    score: float
    payload: Dict[str, Any]

class KnowledgeIngestResponse(BaseModel):
    status: str
    points_inserted: int

# Initialize Qdrant Client (in memory for local testing/dev if no URL provided)
qdrant_url = os.environ.get("QDRANT_URL", ":memory:")
if QDRANT_AVAILABLE:
    client = QdrantClient(location=qdrant_url)
    
    # Ensure collection exists
    COLLECTION_NAME = "bravos_knowledge"
    try:
        client.get_collection(COLLECTION_NAME)
    except Exception:
        client.create_collection(
            collection_name=COLLECTION_NAME,
            vectors_config=VectorParams(size=1536, distance=Distance.COSINE),
        )

@app.post("/v1/knowledge/ingest", response_model=KnowledgeIngestResponse)
async def ingest_document(tenant_id: str = Form(...), file: UploadFile = File(...)):
    """
    Ingest a document into the tenant's knowledge base.
    In prod: split text, chunk, embed, insert.
    """
    if not QDRANT_AVAILABLE:
        raise HTTPException(status_code=500, detail="Qdrant client not installed")

    content = await file.read()
    text_content = content.decode("utf-8", errors="ignore")
    
    # Very naive chunking for demo
    chunks = [text_content[i:i+1000] for i in range(0, len(text_content), 1000)]
    
    points = []
    for chunk in chunks:
        vec = generate_embedding(chunk).tolist()
        point_id = str(uuid.uuid4())
        points.append(
            PointStruct(
                id=point_id, 
                vector=vec, 
                payload={"tenant_id": tenant_id, "text": chunk, "filename": file.filename}
            )
        )
        
    client.upsert(
        collection_name=COLLECTION_NAME,
        wait=True,
        points=points
    )
    
    return {"status": "success", "points_inserted": len(points)}

@app.post("/v1/knowledge/search", response_model=List[SearchResult])
async def search_knowledge(req: SearchQuery):
    """
    Query the vector database for RAG context, filtering by tenant_id.
    """
    if not QDRANT_AVAILABLE:
        raise HTTPException(status_code=500, detail="Qdrant client not installed")

    query_vector = generate_embedding(req.query).tolist()
    
    from qdrant_client.models import Filter, FieldCondition, MatchValue
    
    # Enforce Tenant Isolation via Qdrant Filter
    tenant_filter = Filter(
        must=[
            FieldCondition(
                key="tenant_id",
                match=MatchValue(value=req.tenant_id)
            )
        ]
    )
    
    search_result = client.search(
        collection_name=COLLECTION_NAME,
        query_vector=query_vector,
        query_filter=tenant_filter,
        limit=req.limit,
        score_threshold=req.min_score
    )
    
    results = [
        SearchResult(id=str(hit.id), score=hit.score, payload=hit.payload)
        for hit in search_result
    ]
    
    return results

@app.get("/health")
async def health_check():
    return {"status": "healthy", "service": "knowledge-api", "qdrant_available": QDRANT_AVAILABLE}
