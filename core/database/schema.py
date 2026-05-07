from datetime import datetime
from enum import Enum
from typing import List, Optional
from sqlalchemy import Column, DateTime, ForeignKey, Integer, String, Text, JSON, Enum as SQLEnum
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship

class Base(DeclarativeBase):
    pass

class ProjectStatus(str, Enum):
    ACTIVE = "active"
    COMPLETED = "completed"
    FAILED = "failed"
    PAUSED = "paused"

class TaskStatus(str, Enum):
    PENDING = "pending"
    WORKING = "working"
    CRITIQUING = "critiquing"
    COMPLETED = "completed"
    FAILED = "failed"

class Project(Base):
    __tablename__ = "projects"
    
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(255))
    status: Mapped[ProjectStatus] = mapped_column(SQLEnum(ProjectStatus), default=ProjectStatus.ACTIVE)
    goal: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    tasks: Mapped[List["Task"]] = relationship(back_populates="project", cascade="all, delete-orphan")

class Task(Base):
    __tablename__ = "tasks"
    
    id: Mapped[int] = mapped_column(primary_key=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id"))
    assigned_agent: Mapped[Optional[str]] = mapped_column(String(255))
    status: Mapped[TaskStatus] = mapped_column(SQLEnum(TaskStatus), default=TaskStatus.PENDING)
    description: Mapped[str] = mapped_column(Text)
    logs: Mapped[Optional[str]] = mapped_column(Text)
    metadata_json: Mapped[Optional[dict]] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    completed_at: Mapped[Optional[datetime]] = mapped_column(DateTime)
    
    project: Mapped["Project"] = relationship(back_populates="tasks")
    artifacts: Mapped[List["Artifact"]] = relationship(back_populates="task")

class Artifact(Base):
    __tablename__ = "artifacts"
    
    id: Mapped[int] = mapped_column(primary_key=True)
    task_id: Mapped[int] = mapped_column(ForeignKey("tasks.id"))
    file_path: Mapped[str] = mapped_column(String(1024))
    file_type: Mapped[Optional[str]] = mapped_column(String(100))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    
    task: Mapped["Task"] = relationship(back_populates="artifacts")
