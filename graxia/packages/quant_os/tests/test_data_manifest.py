"""Tests for data.manifest — INV-005 manifest system."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from graxia.packages.quant_os.data.manifest import DataManifest


def _write_parquet_like(path: Path, content: bytes = b"hello world") -> None:
    path.write_bytes(content)


class TestComputeChecksum:
    def test_compute_checksum_deterministic(self, tmp_path: Path):
        """Same file twice yields the same hash."""
        f = tmp_path / "data.bin"
        _write_parquet_like(f, b"abc123")
        h1 = DataManifest.compute_checksum(f)
        h2 = DataManifest.compute_checksum(f)
        assert h1 == h2
        assert len(h1) == 64  # SHA-256 hex

    def test_compute_checksum_different_files(self, tmp_path: Path):
        """Different content yields different hashes."""
        a = tmp_path / "a.bin"
        b = tmp_path / "b.bin"
        a.write_bytes(b"foo")
        b.write_bytes(b"bar")
        assert DataManifest.compute_checksum(a) != DataManifest.compute_checksum(b)


class TestCreateForFile:
    def test_create_for_file_writes_manifest(self, tmp_path: Path):
        """create_for_file writes a JSON sidecar with correct checksum."""
        f = tmp_path / "XAUUSD_M1.parquet"
        _write_parquet_like(f, b"payload")

        m = DataManifest.create_for_file(
            file_path=f,
            symbol="XAUUSD",
            date_range="2024-01-01:2024-12-31",
            row_count=10,
            columns=["open", "high", "low", "close", "volume"],
            dtypes={"open": "float64", "volume": "int64"},
        )
        manifest_path = tmp_path / "XAUUSD_M1_manifest.json"
        assert manifest_path.exists()
        payload = json.loads(manifest_path.read_text())
        assert payload["symbol"] == "XAUUSD"
        assert payload["row_count"] == 10
        assert payload["checksum"] == DataManifest.compute_checksum(f)
        # Returned object matches the file.
        assert m.checksum == payload["checksum"]


class TestLoad:
    def test_load_manifest(self, tmp_path: Path):
        """Round trip: create then load returns equal manifest."""
        f = tmp_path / "XAUUSD_M1.parquet"
        _write_parquet_like(f, b"round-trip")
        DataManifest.create_for_file(
            file_path=f,
            symbol="EURUSD",
            date_range="2024-06-01:2024-06-30",
            row_count=100,
            columns=["open", "high", "low", "close", "volume"],
            dtypes={"open": "float64"},
        )
        loaded = DataManifest.load(f)
        assert loaded.symbol == "EURUSD"
        assert loaded.row_count == 100
        assert loaded.date_range == "2024-06-01:2024-06-30"

    def test_load_missing_manifest_raises_inv005_violation(self, tmp_path: Path):
        """Loading a file with no sidecar raises FileNotFoundError mentioning INV-005."""
        f = tmp_path / "XAUUSD_M1.parquet"
        _write_parquet_like(f, b"no-manifest")
        with pytest.raises(FileNotFoundError, match="INV-005"):
            DataManifest.load(f)


class TestValidate:
    def test_validate_checksum_match(self, tmp_path: Path):
        """Unmodified file → returns (True, 'VALID')."""
        f = tmp_path / "XAUUSD_M1.parquet"
        _write_parquet_like(f, b"intact")
        DataManifest.create_for_file(
            file_path=f,
            symbol="XAUUSD",
            date_range="2024-01-01:2024-01-02",
            row_count=1,
            columns=["open", "high", "low", "close", "volume"],
            dtypes={"open": "float64"},
        )
        ok, msg = DataManifest.validate(f)
        assert ok is True
        assert msg == "VALID"

    def test_validate_checksum_mismatch(self, tmp_path: Path):
        """Corrupted file → returns (False, msg containing CHECKSUM_MISMATCH)."""
        f = tmp_path / "XAUUSD_M1.parquet"
        _write_parquet_like(f, b"original")
        DataManifest.create_for_file(
            file_path=f,
            symbol="XAUUSD",
            date_range="2024-01-01:2024-01-02",
            row_count=1,
            columns=["open", "high", "low", "close", "volume"],
            dtypes={"open": "float64"},
        )
        # Corrupt the file.
        f.write_bytes(b"tampered")
        ok, msg = DataManifest.validate(f)
        assert ok is False
        assert "CHECKSUM_MISMATCH" in msg


class TestSchemaHash:
    def test_compute_schema_hash_stable(self):
        """Same columns + dtypes produce the same hash."""
        a = DataManifest.compute_schema_hash(["open", "close"], {"open": "float64", "close": "float64"})
        b = DataManifest.compute_schema_hash(["open", "close"], {"open": "float64", "close": "float64"})
        assert a == b
        # Different schema → different hash.
        c = DataManifest.compute_schema_hash(["open", "close"], {"open": "float64", "close": "int64"})
        assert a != c
        # Hash is a 16-char prefix of SHA-256.
        assert len(a) == 16
