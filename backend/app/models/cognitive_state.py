import uuid

from sqlalchemy import (
    UUID,
    CheckConstraint,
    Column,
    Date,
    DateTime,
    Integer,
    SmallInteger,
    Text,
    func,
)

from .base import Base


class CognitiveState(Base):
    __tablename__ = "cognitive_state"
    __table_args__ = (
        CheckConstraint("energy BETWEEN 0 AND 10", name="ck_cog_energy"),
        CheckConstraint("stress BETWEEN 0 AND 10", name="ck_cog_stress"),
        CheckConstraint("exam_pressure BETWEEN 0 AND 10", name="ck_cog_exam"),
    )

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    date = Column(Date, unique=True, nullable=False, server_default=func.current_date())
    energy = Column(SmallInteger, default=7)
    stress = Column(SmallInteger, default=3)
    available_hours_this_week = Column(Integer, default=20)
    exam_pressure = Column(SmallInteger, default=0)
    mood_note = Column(Text)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
