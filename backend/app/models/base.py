from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.orm import DeclarativeBase


@compiles(JSONB, "sqlite")
def _compile_jsonb_for_sqlite(*_: object, **__: object) -> str:
    """Let local tests use SQLite while production keeps PostgreSQL JSONB."""
    return "JSON"


class Base(DeclarativeBase):
    pass
