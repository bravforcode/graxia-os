from typing import Any
from uuid import UUID
from sqlalchemy import Column, ForeignKey
from sqlalchemy.dialects.postgresql import JSONB, UUID as PG_UUID
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.orm import DeclarativeBase, declared_attr, Mapped, mapped_column
from sqlalchemy import event


@compiles(JSONB, "sqlite")
def _compile_jsonb_for_sqlite(*_: object, **__: object) -> str:
    """Let local tests use SQLite while production keeps PostgreSQL JSONB."""
    return "JSON"


@compiles(PG_UUID, "sqlite")
def _compile_pg_uuid_for_sqlite(*_: object, **__: object) -> str:
    """Let local tests use SQLite while production keeps PostgreSQL UUID.

    Must match CHAR(32) inferred from Mapped[uuid.UUID] on SQLite
    so that foreign key constraints work correctly.
    """
    return "CHAR(32)"


class Base(DeclarativeBase):
    pass


class TenantMixin:
    """Mixin to enforce organization_id on all multi-tenant models."""
    @declared_attr
    def organization_id(cls) -> Mapped[UUID]:
        return mapped_column(PG_UUID(as_uuid=True), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True)


@event.listens_for(TenantMixin, "before_insert", propagate=True)
def validate_tenant_id(mapper: Any, connection: Any, target: Any) -> None:
    """Ensure organization_id is never null before saving to DB."""
    if not getattr(target, 'organization_id', None):
        raise ValueError(f"CRITICAL: {target.__class__.__name__} missing organization_id. Data leak prevented.")

