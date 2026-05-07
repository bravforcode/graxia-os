import uuid

from pgvector.sqlalchemy import Vector
from sqlalchemy import (
    UUID,
    Boolean,
    CheckConstraint,
    Column,
    DateTime,
    ForeignKey,
    Integer,
    Numeric,
    String,
    Text,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import relationship

from .base import Base


class KnowledgeItem(Base):
    __tablename__ = "knowledge_items"
    __table_args__ = (
        CheckConstraint(
            "category IN ('project','proposal_template','bio','skill_description','lesson','case_study','testimonial','pitch_snippet','objection_response','playbook','failure_analysis','vault_note','research')",
            name="ck_knowledge_category",
        ),
    )

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    category = Column(String(50))
    title = Column(String(500), nullable=False)
    content = Column(Text, nullable=False)
    tags = Column(JSONB, default=list)
    best_for = Column(JSONB, default=list)
    project_url = Column(Text)
    github_url = Column(Text)
    tech_stack = Column(JSONB, default=list)
    metrics_achieved = Column(Text)
    use_count = Column(Integer, default=0)
    last_used_at = Column(DateTime(timezone=True))
    approval_rate_when_used = Column(Numeric(5, 2))
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=func.now())
    updated_at = Column(DateTime, default=func.now(), onupdate=func.now())
    iuse_count = Column(Integer, default=0)

    embedding = Column(Vector(768), nullable=True)
    chunk_hash = Column(String(64), nullable=True, index=True)
    chunk_index = Column(Integer, nullable=True)
    source_path = Column(String(512), nullable=True)


class KnowledgeChunk(Base):
    """Knowledge chunk for vector search and retrieval."""
    __tablename__ = "knowledge_chunks"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    document_id = Column(UUID(as_uuid=True), ForeignKey("knowledge_documents.id"))
    content = Column(Text, nullable=False)
    embedding = Column(Vector(1536))  # OpenAI embedding dimension
    chunk_metadata = Column(JSONB, default=dict)  # Renamed to avoid conflict
    chunk_index = Column(Integer, default=0)
    created_at = Column(DateTime, default=func.now())

    # Relationship
    document = relationship("KnowledgeDocument", back_populates="chunks")


class KnowledgeDocument(Base):
    """Knowledge document for organizing chunks."""
    __tablename__ = "knowledge_documents"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    title = Column(String(500), nullable=False)
    source_type = Column(String(50))  # vault, file, api, etc.
    source_path = Column(Text)
    content_hash = Column(String(64))  # SHA-256 hash
    doc_metadata = Column(JSONB, default=dict)  # Renamed to avoid conflict
    created_at = Column(DateTime, default=func.now())
    updated_at = Column(DateTime, default=func.now(), onupdate=func.now())

    # Relationships
    chunks = relationship("KnowledgeChunk", back_populates="document", cascade="all, delete-orphan")
