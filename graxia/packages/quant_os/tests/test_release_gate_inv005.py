"""Tests for Task 17 — release gate INV-005 data-integrity step.
Importlib-loaded: monorepo root ships its own scripts/ package, so
`import scripts.run_release_gate` can resolve to the wrong tree."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

_SPEC = importlib.util.spec_from_file_location(
    "release_gate_mod", Path(__file__).resolve().parent.parent / "scripts" / "run_release_gate.py"
)
assert _SPEC is not None and _SPEC.loader is not None
_MOD = importlib.util.module_from_spec(_SPEC)
sys.modules["release_gate_mod"] = _MOD
_SPEC.loader.exec_module(_MOD)

check_data_integrity_inv005 = _MOD.check_data_integrity_inv005
DataManifestManager = _MOD.DataManifestManager


def test_inv005_passes_when_no_manifests(tmp_path, monkeypatch):
    monkeypatch.setattr(_MOD, "MANIFEST_DIR", tmp_path / "none")
    assert check_data_integrity_inv005() is True


def test_inv005_fails_on_tamper(tmp_path, monkeypatch):
    manifest_dir = tmp_path / "manifests"
    manifest_dir.mkdir()
    data = tmp_path / "data" / "ticks" / "XAUUSD_2026-08-04.parquet"
    data.parent.mkdir(parents=True)
    data.write_bytes(b"tickdata123")
    mgr = DataManifestManager(manifest_dir)
    mgr.update_manifest("ticks", [data])
    data.write_bytes(b"tampered!")
    monkeypatch.setattr(_MOD, "MANIFEST_DIR", manifest_dir)
    assert check_data_integrity_inv005() is False
