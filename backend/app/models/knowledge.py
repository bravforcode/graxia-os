import uuid
from sqlalchemy import (
    UUID, Boolean, CheckConstraint, Column, DateTime,
    Integer, Numeric, String, Text, func,
)
from sqlalchemy.dialects.postgresql import JSONB
from .base import Base


class KnowledgeItem(Base):
    __tablename__ = "knowledge_items"
    __table_args__ = (
        CheckConstraint(
            "category IN ('project','proposal_template','bio','skill_description','lesson','case_study','testimonial','pitch_snippet','objection_response','playbook','failure_analysis')",
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
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
