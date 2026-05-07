"""
graxia/database.py
Shared SQLAlchemy DeclarativeBase for all Graxia packages.
Single source of truth — never create another Base class anywhere in the codebase.
"""
from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    """Universal base model for all Graxia ORM models."""
    pass
