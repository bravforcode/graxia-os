"""Tests for Task 13 — run_backfill.py CLI (parse_args + run_one_source
dispatch with manifest generation, no network).

NOTE: the monorepo root also ships a `scripts/` package, so `import
scripts.run_backfill` can resolve to the wrong tree under pytest — load the
module directly via importlib (repo pattern) and patch its attrs.
"""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

_SPEC = importlib.util.spec_from_file_location(
    "run_backfill_mod", Path(__file__).resolve().parent.parent / "scripts" / "run_backfill.py"
)
assert _SPEC is not None and _SPEC.loader is not None
_MOD = importlib.util.module_from_spec(_SPEC)
sys.modules["run_backfill_mod"] = _MOD
_SPEC.loader.exec_module(_MOD)

parse_args = _MOD.parse_args
run_one_source = _MOD.run_one_source


def test_parse_args_requires_valid_source():
    args = parse_args(["--source", "binance", "--dataset", "funding", "--start", "2026-08-01", "--end", "2026-08-02"])
    assert args.source == "binance"
    assert args.dataset == "funding"


def test_run_one_source_writes_manifest(tmp_path, monkeypatch):
    calls = {"n": 0}

    def fake_fetch_funding(symbol, start, end, out_dir, **kw):
        calls["n"] += 1
        out = Path(out_dir) / f"{symbol}_2026-08-01.parquet"
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_bytes(b"x")
        return [out]

    monkeypatch.setattr(_MOD, "fetch_funding", fake_fetch_funding)
    result = run_one_source(
        "binance",
        "funding",
        "2026-08-01",
        "2026-08-02",
        ["BTCUSDT"],
        tmp_path / "out",
        manifest_dir=tmp_path / "manifests",
    )
    assert calls["n"] == 1
    assert result == 1
    manifest = tmp_path / "manifests" / "funding_manifest.json"
    assert manifest.exists()
    assert json.loads(manifest.read_text(encoding="utf-8"))["file_count"] == 1
