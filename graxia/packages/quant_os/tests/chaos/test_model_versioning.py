"""Tests for ML model versioning."""

from __future__ import annotations

import pickle
import time
from pathlib import Path

import pytest

from graxia.packages.quant_os.core.ml.versioning import (
    cleanup_old_versions,
    latest_model,
    list_versions,
    versioned_filename,
)


@pytest.fixture
def model_dir(tmp_path: Path) -> Path:
    """Create a temp directory with fake model files."""
    for i in range(8):
        # Manually construct unique names since versioned_filename has second-level granularity
        fname = f"xgboost_v20260628_{164000 + i:06d}.pkl"
        (tmp_path / fname).write_bytes(pickle.dumps({"version": i}))
        time.sleep(0.05)  # ensure distinct mtimes
    return tmp_path


def test_versioned_filename_format():
    name = versioned_filename("xgboost")
    assert name.startswith("xgboost_v")
    assert name.endswith(".pkl")
    # Format: xgboost_vYYYYMMDD_HHMMSS.pkl
    ts_part = name.replace("xgboost_v", "").replace(".pkl", "")
    date, time_ = ts_part.split("_")
    assert len(date) == 8
    assert len(time_) == 6


def test_latest_model_finds_most_recent(model_dir: Path):
    latest = latest_model(model_dir, "xgboost_v*.pkl")
    assert latest is not None
    versions = list_versions(model_dir, "xgboost_v*.pkl")
    assert latest == versions[-1]


def test_latest_model_returns_none_on_empty(tmp_path: Path):
    assert latest_model(tmp_path) is None


def test_list_versions_sorted(model_dir: Path):
    versions = list_versions(model_dir, "xgboost_v*.pkl")
    assert len(versions) == 8
    # Oldest first
    for i in range(len(versions) - 1):
        assert versions[i].stat().st_mtime <= versions[i + 1].stat().st_mtime


def test_cleanup_keeps_n_versions(model_dir: Path):
    deleted = cleanup_old_versions(model_dir, keep=5)
    assert len(deleted) == 3
    remaining = list_versions(model_dir, "xgboost_v*.pkl")
    assert len(remaining) == 5
    for d in deleted:
        assert not d.exists()


def test_cleanup_noop_when_under_limit(model_dir: Path):
    deleted = cleanup_old_versions(model_dir, keep=10)
    assert deleted == []
    assert len(list_versions(model_dir, "xgboost_v*.pkl")) == 8


def test_cleanup_empty_dir(tmp_path: Path):
    deleted = cleanup_old_versions(tmp_path, keep=5)
    assert deleted == []
