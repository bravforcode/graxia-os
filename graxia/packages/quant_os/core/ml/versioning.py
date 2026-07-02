"""ML Model Versioning — prevent overwrites, enable rollback."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path


def versioned_filename(base_name: str = "xgboost") -> str:
    """Generate versioned filename: xgboost_v20260628_183045.pkl"""
    ts = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
    return f"{base_name}_v{ts}.pkl"


def latest_model(model_dir: Path, pattern: str = "xgboost_v*.pkl") -> Path | None:
    """Find most recently modified model matching pattern."""
    model_files = sorted(model_dir.glob(pattern), key=lambda p: p.stat().st_mtime)
    return model_files[-1] if model_files else None


def list_versions(model_dir: Path, pattern: str = "xgboost_v*.pkl") -> list[Path]:
    """List all model versions sorted oldest→newest."""
    return sorted(model_dir.glob(pattern), key=lambda p: p.stat().st_mtime)


def cleanup_old_versions(model_dir: Path, pattern: str = "xgboost_v*.pkl", keep: int = 5) -> list[Path]:
    """Delete oldest versions, keeping the newest `keep`. Returns deleted paths."""
    versions = list_versions(model_dir, pattern)
    if len(versions) <= keep:
        return []
    to_delete = versions[: len(versions) - keep]
    for p in to_delete:
        p.unlink(missing_ok=True)
    return to_delete
