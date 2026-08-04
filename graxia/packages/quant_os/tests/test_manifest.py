"""Tests for Task 7 — INV-005 DataManifestManager (reconciled into
data/manifest.py alongside the existing per-file DataManifest sidecars).

Shape per plan spec 5.4: one dataset manifest JSON listing repo-root-relative
paths with size_bytes + sha256; verify returns error strings (empty = pass).
Files outside the repo root (pytest tmp_path) are stored as absolute paths.
"""

from __future__ import annotations

from pathlib import Path

from graxia.packages.quant_os.data.manifest import DataManifestManager


def _write_file(path: Path, content: bytes):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(content)
    return path


def test_update_and_verify_roundtrip(tmp_path, monkeypatch):
    monkeypatch.setattr("graxia.packages.quant_os.data.manifest.MANIFEST_DIR", tmp_path / "manifests")
    f = _write_file(tmp_path / "data" / "ticks" / "XAUUSD_2026-08-04.parquet", b"tickdata123")
    mgr = DataManifestManager()
    manifest_path = mgr.update_manifest("ticks", [f])
    assert manifest_path.exists()
    assert mgr.verify_manifest(manifest_path) == []  # clean


def test_verify_detects_tamper(tmp_path, monkeypatch):
    monkeypatch.setattr("graxia.packages.quant_os.data.manifest.MANIFEST_DIR", tmp_path / "manifests")
    f = _write_file(tmp_path / "data" / "ticks" / "XAUUSD_2026-08-04.parquet", b"tickdata123")
    mgr = DataManifestManager()
    manifest_path = mgr.update_manifest("ticks", [f])
    f.write_bytes(b"tickdata999")  # tamper after manifest
    errors = mgr.verify_manifest(manifest_path)
    assert any("sha256" in e.lower() for e in errors)


def test_verify_detects_missing_file(tmp_path, monkeypatch):
    monkeypatch.setattr("graxia.packages.quant_os.data.manifest.MANIFEST_DIR", tmp_path / "manifests")
    f = _write_file(tmp_path / "data" / "ticks" / "XAUUSD_2026-08-04.parquet", b"tickdata123")
    mgr = DataManifestManager()
    manifest_path = mgr.update_manifest("ticks", [f])
    f.unlink()
    assert mgr.verify_manifest(manifest_path)  # non-empty errors
