"""Alembic environment for Quant OS."""

import importlib.util
import os
import sys
from logging.config import fileConfig
from pathlib import Path

from sqlalchemy import engine_from_config, pool

from alembic import context

# Make the quant_os package tree importable without relying on the api
# package's __init__.py (which eagerly imports runtime routers that pull in
# modules with broken imports in the current environment).
_QUANT_OS_ROOT = Path(__file__).resolve().parent.parent
_PACKAGES_ROOT = _QUANT_OS_ROOT.parent

if str(_PACKAGES_ROOT) not in sys.path:
    sys.path.insert(0, str(_PACKAGES_ROOT))

# Ensure the quant_os package exists in sys.modules so relative imports in
# api/models.py and api/db.py resolve correctly.
if "quant_os" not in sys.modules:
    import quant_os  # noqa: F401


def _load_module_directly(module_name: str, rel_path: Path):
    """Load a quant_os module by path, bypassing package __init__.py."""
    full_name = f"quant_os.{module_name}"
    if full_name in sys.modules:
        return sys.modules[full_name]
    spec = importlib.util.spec_from_file_location(full_name, rel_path)
    mod = importlib.util.module_from_spec(spec)
    mod.__package__ = "quant_os.api" if module_name.startswith("api.") else "quant_os"
    sys.modules[full_name] = mod
    spec.loader.exec_module(mod)
    return mod


# Load api/models.py first, then api/db.py which re-exports Base.
_load_module_directly("api.models", _QUANT_OS_ROOT / "api" / "models.py")
_db = _load_module_directly("api.db", _QUANT_OS_ROOT / "api" / "db.py")
Base = _db.Base

# this is the Alembic Config object, which provides
# access to the values within the .ini file in use.
config = context.config

# Resolve database URL from the environment. Alembic needs a synchronous driver,
# so normalize the common asyncpg URL used by the API to psycopg2.
_raw_url = os.environ.get("DATABASE_URL", "")
if not _raw_url:
    raise RuntimeError("DATABASE_URL environment variable is required")
config.set_main_option("sqlalchemy.url", _raw_url.replace("postgresql+asyncpg://", "postgresql+psycopg2://"))

# Interpret the config file for Python logging.
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# Metadata object for autogenerate support.
target_metadata = Base.metadata


def run_migrations_offline() -> None:
    """Run migrations in 'offline' mode."""
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """Run migrations in 'online' mode."""
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    with connectable.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata)

        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
