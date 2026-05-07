from typing import List, Optional, Protocol, Union
from datetime import datetime
import re
from pydantic import BaseModel, Field, ConfigDict

class ChunkMetadata(BaseModel):
    """Schema for chunk-level metadata."""
    chunk_id: str
    source: str
    page: Optional[int] = None
    section: Optional[str] = None
    parent_chunk_id: Optional[str] = None
    created_at: datetime = Field(default_factory=datetime.utcnow)
    token_count: int
    embedding_model: str
    chunk_type: str = "text"
    
    model_config = ConfigDict(frozen=True)

class Chunk(BaseModel):
    """A unit of text with its metadata."""
    content: str
    metadata: ChunkMetadata
    embedding: Optional[List[float]] = None

class Embedder(Protocol):
    """Interface for embedding generation."""
    def embed(self, text: str) -> List[float]:
        ...
    
    def embed_batch(self, texts: List[str]) -> List[List[float]]:
        ...
    
    @property
    def model_name(self) -> str:
        ...

class StructuralChunker:
    """
    Priority 3: Structural Chunker.
    Replaces expensive LLM-based semantic chunking with structural chunking
    (headings for markdown, functions/classes for code, paragraphs for plain text).
    """
    
    def __init__(
        self, 
        embedder: Embedder, 
        max_tokens_per_chunk: int = 512
    ):
        self.embedder = embedder
        self.max_tokens_per_chunk = max_tokens_per_chunk

    def split_code(self, text: str) -> List[str]:
        """Splits Python code by class and function definitions."""
        pattern = r'(?m)^(class\s+\w+|def\s+\w+)'
        parts = re.split(pattern, text)
        
        chunks = []
        if parts[0].strip():
            chunks.append(parts[0].strip())
            
        for i in range(1, len(parts), 2):
            declaration = parts[i]
            body = parts[i+1] if i+1 < len(parts) else ""
            chunks.append((declaration + body).strip())
            
        return chunks

    def split_markdown(self, text: str) -> List[str]:
        """Splits markdown by headings."""
        pattern = r'(?m)^(#+\s+.*)'
        parts = re.split(pattern, text)
        
        chunks = []
        if parts[0].strip():
            chunks.append(parts[0].strip())
            
        for i in range(1, len(parts), 2):
            heading = parts[i]
            body = parts[i+1] if i+1 < len(parts) else ""
            chunks.append((heading + "\n" + body).strip())
            
        return chunks

    def split_paragraphs(self, text: str) -> List[str]:
        """Splits raw text by double newlines."""
        return [p.strip() for p in re.split(r'\n\s*\n', text) if p.strip()]

    def chunk(self, text: str, source: str, file_type: str = "text") -> List[Chunk]:
        """Main entry point for structural chunking."""
        if file_type.lower() in ["python", "py", "code"]:
            raw_chunks = self.split_code(text)
            chunk_type = "code"
        elif file_type.lower() in ["markdown", "md"]:
            raw_chunks = self.split_markdown(text)
            chunk_type = "markdown"
        else:
            raw_chunks = self.split_paragraphs(text)
            chunk_type = "paragraph"
            
        if not raw_chunks:
            return []

        # Embed all chunks at once for efficiency
        embeddings = self.embedder.embed_batch(raw_chunks)
        
        chunks = []
        for i, content in enumerate(raw_chunks):
            token_count = len(content.split())
            metadata = ChunkMetadata(
                chunk_id=f"chk_{datetime.utcnow().timestamp()}_{i}",
                source=source,
                token_count=token_count,
                embedding_model=self.embedder.model_name,
                chunk_type=chunk_type
            )
            chunks.append(Chunk(
                content=content,
                metadata=metadata,
                embedding=embeddings[i]
            ))
            
        return chunks

# Keep SemanticChunker alias for backwards compatibility across the codebase
SemanticChunker = StructuralChunker
