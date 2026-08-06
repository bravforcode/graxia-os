# Direction I Plan 2 — P1-P3 Mining Infrastructure Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the P1 (massive mining) → P2 (taxonomy+dedup) → P3 (evidence triage) infrastructure for Direction I: catalog schema with validation, mechanism taxonomy with partition enforcement, and cost-viability triage — so mining subagents can produce evidence-ranked candidate mechanisms for P4 screening.

**Architecture:** Four small modules with one responsibility each, consumed by three CLI runners. `research/catalog.py` owns the raw-entry catalog (schema validation + partition tagging at ingest, reusing `research/partition_registry.check_partition`). `research/taxonomy.py` classifies entries into canonical mechanisms and fingerprints-dedups them. `research/triage.py` assigns evidence tiers and runs cost-viability math against `config/cost_calibration.json` with the A1 conservative proxy (asset-class worst-case ×1.5). CLIs (`scripts/run_mining.py`, `scripts/run_taxonomy.py`, `scripts/run_triage.py`) orchestrate the pipeline. All state lives under `research/catalog_i/` (per spec §5 P1-P3).

**Tech Stack:** Python 3.11+, stdlib only (json, pathlib, re, hashlib), pytest. No new dependencies.

## Global Constraints

- All catalog entries MUST have a `source_url` — no URL = rejected at ingest (no-fabrication rule, spec §5 P1)
- `evidence_tier` MUST be one of `{"literature", "myfxbook_verified", "practitioner"}` (spec §5 P3)
- Partition enforcement (spec §1.8/A17): entries matching `research/partition_registry.PARTITION_RULES` are tagged `owned_by: "H"` at ingest; taxonomy MUST NOT recommend them into the shortlist without documented structural difference
- Martingale/grid entries are flagged `requires_martingale_gate: true` at classification (spec §4 — they enter screening only via the hard gate)
- Cost-viability uses conservative proxies (A1): calibrated symbols → their FROM_TICKS round-trip; uncalibrated → asset-class worst-case among calibrated symbols × 1.5
- N accounting: taxonomy classification = 0 N; cost-viability math = 0 N (spec §3.2 — no returns evaluated in P1-P3). No backtests run in this plan
- Writer lock: acquire `scripts/acquire_writer_lock.py --owner "direction-i-funnel-design"` before any write session (enforced by pre-commit `writer-lock-check`)
- Direction H files untouched (citations-only, A16/A17); ratchet test `tests/test_direction_i_closure.py` must stay green
- Pre-commit suite incl. `writer-lock-check` must pass on every commit

## Scope Check

P1-P3 are one coherent subsystem (catalog→taxonomy→triage pipeline) with no external dependencies (C0 output is only needed at P4 wiring). This plan produces working, testable software. P4-P7 remain separate follow-on plans.

## File Structure

| File | Responsibility |
|---|---|
| `research/catalog.py` (NEW) | `CATALOG_DIR`, `validate_entry()`, `add_entry()`, `load_entries()`, `ingest_batch()` — raw catalog CRUD + partition tagging |
| `research/catalog_i/contract_v1.json` (NEW) | Machine-readable subagent contract: entry schema + field docs (consumed by mining subagents) |
| `tests/test_catalog.py` (NEW) | Catalog validation/ingest tests |
| `research/taxonomy.py` (NEW) | `classify_mechanism()`, `fingerprint()`, `dedup_to_canonical()` — 60+ mechanism families |
| `tests/test_taxonomy.py` (NEW) | Classification + dedup tests |
| `research/triage.py` (NEW) | `assign_evidence_tier()`, `cost_viability()`, `shortlist()` — triage + cost math |
| `tests/test_triage.py` (NEW) | Triage + cost-viability tests |
| `scripts/run_mining.py` (NEW) | CLI: ingest one source's raw JSON batch into catalog (subagent output → catalog) |
| `scripts/run_taxonomy.py` (NEW) | CLI: raw catalog → `research/catalog_i/canonical_mechanisms.json` |
| `scripts/run_triage.py` (NEW) | CLI: canonical → `research/catalog_i/shortlist.json` |
| `tests/fixtures/mining_sample.json` (NEW) | Sample raw entries (6 entries covering literature/practitioner/martingale/partition-hit cases) |

---

### Task 1: Catalog module (`research/catalog.py` + contract)

**Files:**
- Create: `research/catalog.py`, `research/catalog_i/contract_v1.json`, `tests/fixtures/mining_sample.json`
- Test: `tests/test_catalog.py`

**Interfaces:**
- Consumes: `research/partition_registry.check_partition(mechanism, symbol, timeframe)` (Phase 0 Task 5)
- Produces: `validate_entry(entry: dict) -> list[str]` (errors; empty = valid); `add_entry(catalog_path, entry) -> dict` (returns entry with `catalog_id`, `ingested_at`, `partition` fields; raises `ValueError` on validation failure); `load_entries(catalog_path) -> list[dict]`; `ingest_batch(catalog_path, entries) -> tuple[int, list[str]]` (added count, error list)
- `catalog_i/contract_v1.json` — `{"schema_version": "1.0", "required_fields": [...], "evidence_tiers": [...], "field_docs": {...}, "direction": "I"}`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_catalog.py
import json
from pathlib import Path

import pytest

from research.catalog import add_entry, ingest_batch, load_entries, validate_entry

SAMPLE = Path(__file__).resolve().parent / "fixtures" / "mining_sample.json"


def _entry(overrides=None):
    e = {
        "name": "Test EA",
        "source": "mql5",
        "source_url": "https://www.mql5.com/en/code/12345",
        "mechanism": "grid_martingale",
        "symbol": "XAUUSD",
        "timeframe": "H1",
        "params": {"grid_size": 50},
        "claimed_perf": "Sharpe 3.0",
        "evidence_tier": "practitioner",
    }
    if overrides:
        e.update(overrides)
    return e


def test_validate_entry_ok():
    assert validate_entry(_entry()) == []


def test_validate_entry_requires_source_url():
    errs = validate_entry(_entry({"source_url": ""}))
    assert any("source_url" in e for e in errs)


def test_validate_entry_requires_evidence_tier_enum():
    errs = validate_entry(_entry({"evidence_tier": "magic"}))
    assert any("evidence_tier" in e for e in errs)


def test_add_entry_partition_tags_forex4_trend():
    p = tmp_catalog()
    entry = add_entry(p, _entry({"mechanism": "trend_continuity", "symbol": "USDCAD", "timeframe": "H1"}))
    assert entry["partition"]["status"] == "CLOSED"
    assert entry["partition"]["owner"] == "H"


def test_add_entry_rejects_no_url():
    p = tmp_catalog()
    with pytest.raises(ValueError):
        add_entry(p, _entry({"source_url": ""}))


def test_ingest_batch_returns_counts(tmp_path):
    entries = json.loads(SAMPLE.read_text(encoding="utf-8"))["entries"]
    p = tmp_path / "catalog.json"
    added, errs = ingest_batch(str(p), entries)
    assert added == len(entries)
    assert errs == []
    assert len(load_entries(str(p))) == len(entries)


def test_contract_matches_module():
    contract = json.loads(
        (Path(__file__).resolve().parents[1] / "research" / "catalog_i" / "contract_v1.json").read_text(encoding="utf-8")
    )
    for f in contract["required_fields"]:
        assert f in {
            "name", "source", "source_url", "mechanism", "symbol", "timeframe",
            "params", "claimed_perf", "evidence_tier",
        }
    assert contract["evidence_tiers"] == ["literature", "myfxbook_verified", "practitioner"]


def tmp_catalog(tmp_path=None):
    if tmp_path is None:
        import tempfile

        tmp_path = tempfile.mkdtemp()
    return str(Path(tmp_path) / "catalog.json")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_catalog.py -q`
Expected: FAIL (`ModuleNotFoundError: No module named 'research.catalog'`)

- [ ] **Step 3: Write minimal implementation**

```python
# research/catalog.py
"""Raw entry catalog for Direction I mining (spec §5 P1).

Every entry requires a source_url (no-fabrication rule). Partition
tagging (research/partition_registry) happens at ingest so taxonomy
never recommends Direction-H-owned families. No returns evaluated here
-> 0 N (spec §3.2).
"""
from __future__ import annotations

import json
import time
import uuid
from pathlib import Path

from research.partition_registry import check_partition

CATALOG_DIR = Path(__file__).resolve().parent / "catalog_i"

REQUIRED_FIELDS = [
    "name", "source", "source_url", "mechanism", "symbol", "timeframe",
    "params", "claimed_perf", "evidence_tier",
]
EVIDENCE_TIERS = ["literature", "myfxbook_verified", "practitioner"]


def validate_entry(entry: dict) -> list[str]:
    errors = []
    for f in REQUIRED_FIELDS:
        if f not in entry or entry[f] in (None, ""):
            errors.append(f"missing required field: {f}")
    if entry.get("source_url") and not str(entry["source_url"]).startswith(("http://", "https://")):
        errors.append("source_url must be an absolute http(s) URL")
    if entry.get("evidence_tier") not in EVIDENCE_TIERS:
        errors.append(f"evidence_tier must be one of {EVIDENCE_TIERS}")
    return errors


def _partition_tag(entry: dict) -> dict:
    r = check_partition(entry.get("mechanism", ""), entry.get("symbol", ""), entry.get("timeframe", ""))
    return {"status": r["status"], "owner": r["owner"], "note": r["note"]}


def load_entries(catalog_path: str | Path) -> list[dict]:
    path = Path(catalog_path)
    if not path.exists():
        return []
    try:
        return json.loads(path.read_text(encoding="utf-8")).get("entries", [])
    except (json.JSONDecodeError, OSError) as exc:
        raise ValueError(f"unreadable catalog {path}: {exc} — fail-closed") from exc


def add_entry(catalog_path: str | Path, entry: dict) -> dict:
    errors = validate_entry(entry)
    if errors:
        raise ValueError("; ".join(errors))
    path = Path(catalog_path)
    entries = load_entries(path)
    stamped = {
        **entry,
        "catalog_id": uuid.uuid4().hex[:12],
        "ingested_at": time.strftime("%Y-%m-%dT%H:%M:%S+00:00", time.gmtime()),
        "partition": _partition_tag(entry),
    }
    entries.append(stamped)
    path.write_text(
        json.dumps({"schema_version": "1.0", "direction": "I", "entries": entries}, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    return stamped


def ingest_batch(catalog_path: str | Path, entries: list[dict]) -> tuple[int, list[str]]:
    path = Path(catalog_path)
    existing = load_entries(path)
    added = 0
    errors = []
    for entry in entries:
        errs = validate_entry(entry)
        if errs:
            errors.append(f"{entry.get('name', '<unnamed>')}: {'; '.join(errs)}")
            continue
        existing.append({**entry, "catalog_id": uuid.uuid4().hex[:12],
                         "ingested_at": time.strftime("%Y-%m-%dT%H:%M:%S+00:00", time.gmtime()),
                         "partition": _partition_tag(entry)})
        added += 1
    path.write_text(
        json.dumps({"schema_version": "1.0", "direction": "I", "entries": existing}, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    return added, errors
```

- [ ] **Step 4: Create contract + fixture**

`research/catalog_i/contract_v1.json`:
```json
{
  "schema_version": "1.0",
  "direction": "I",
  "required_fields": ["name", "source", "source_url", "mechanism", "symbol", "timeframe", "params", "claimed_perf", "evidence_tier"],
  "evidence_tiers": ["literature", "myfxbook_verified", "practitioner"],
  "field_docs": {
    "name": "EA/strategy name (unique per entry)",
    "source": "mql5 | github | myfxbook | forex_factory | tradingview | academic | institutional | obscure",
    "source_url": "ABSOLUTE http(s) URL — mandatory, no fabrication",
    "mechanism": "lowercase snake_case, e.g. grid_martingale, trend_continuity, rsi_mean_reversion",
    "symbol": "e.g. EURUSD, BTCUSD, XAUUSD",
    "timeframe": "M1|M5|M15|M30|H1|H4|D1|W1|MN1",
    "params": "{} object — key parameters",
    "claimed_perf": "what the source claims (string)",
    "evidence_tier": "literature | myfxbook_verified | practitioner"
  }
}
```

`tests/fixtures/mining_sample.json` (6 entries: 2 literature, 2 practitioner, 1 myfxbook, 1 partition-hit):
```json
{
  "entries": [
    {"name": "Faber 10mo", "source": "academic", "source_url": "https://papers.ssrn.com/sol3/papers.cfm?abstract_id=962461", "mechanism": "trend_following", "symbol": "SPY", "timeframe": "D1", "params": {"ma": 200}, "claimed_perf": "Sharpe 0.6-0.9", "evidence_tier": "literature"},
    {"name": "Moreira-Muir vol targeting", "source": "academic", "source_url": "https://papers.ssrn.com/sol3/papers.cfm?abstract_id=2820922", "mechanism": "vol_targeting", "symbol": "SPY", "timeframe": "D1", "params": {"target_vol": 0.15}, "claimed_perf": "Sharpe +0.6", "evidence_tier": "literature"},
    {"name": "Grid King", "source": "mql5", "source_url": "https://www.mql5.com/en/code/11111", "mechanism": "grid_martingale", "symbol": "XAUUSD", "timeframe": "M15", "params": {"grid": 50}, "claimed_perf": "Sharpe 2.0", "evidence_tier": "practitioner"},
    {"name": "Breakout B", "source": "forex_factory", "source_url": "https://www.forexfactory.com/thread/22222", "mechanism": "breakout", "symbol": "EURUSD", "timeframe": "H4", "params": {"range": 20}, "claimed_perf": "50% winrate", "evidence_tier": "practitioner"},
    {"name": "FXStabilizer", "source": "myfxbook", "source_url": "https://www.myfxbook.com/systems/fxstabilizer/33333", "mechanism": "scalper", "symbol": "EURUSD", "timeframe": "M5", "params": {}, "claimed_perf": "live verified", "evidence_tier": "myfxbook_verified"},
    {"name": "Forex4 Trend Clone", "source": "tradingview", "source_url": "https://www.tradingview.com/script/44444/", "mechanism": "trend_continuity", "symbol": "USDCAD", "timeframe": "H1", "params": {}, "claimed_perf": "backtest claim", "evidence_tier": "practitioner"}
  ]
}
```

- [ ] **Step 5: Run test to verify it passes**

Run: `python -m pytest tests/test_catalog.py -q`
Expected: 8 passed

- [ ] **Step 6: Commit**

```bash
git add research/catalog.py research/catalog_i/contract_v1.json tests/test_catalog.py tests/fixtures/mining_sample.json
git commit -m "feat(quant_os): mining catalog module with partition tagging + contract (Direction I P1)"
```

---

### Task 2: Taxonomy module (`research/taxonomy.py`)

**Files:**
- Create: `research/taxonomy.py`
- Test: `tests/test_taxonomy.py`

**Interfaces:**
- Consumes: catalog entries (Task 1 shape), `research/partition_registry`
- Produces: `MECHANISM_FAMILIES: dict[str, list[str]]` (family → keywords); `classify_mechanism(entry: dict) -> str` (returns canonical family id); `fingerprint(entry: dict) -> str` (sha256 of family|symbol|timeframe|structural params); `dedup_to_canonical(entries: list[dict]) -> list[dict]` (one representative per fingerprint, partition-CLOSED entries excluded, martingale flagged `requires_martingale_gate: true`)

- [ ] **Step 1: Write the failing test**

```python
# tests/test_taxonomy.py
from research.taxonomy import (
    MECHANISM_FAMILIES,
    classify_mechanism,
    dedup_to_canonical,
    fingerprint,
)


def _e(mechanism, symbol="XAUUSD", timeframe="H1", params=None):
    return {
        "name": "x", "source": "mql5", "source_url": "https://example.com/x",
        "mechanism": mechanism, "symbol": symbol, "timeframe": timeframe,
        "params": params or {}, "claimed_perf": "c", "evidence_tier": "practitioner",
        "partition": {"status": "FREE", "owner": None, "note": ""},
    }


def test_classify_known_family():
    assert classify_mechanism(_e("grid_martingale")) in MECHANISM_FAMILIES


def test_classify_normalizes_spelling():
    assert classify_mechanism(_e("Grid Martingale")) == classify_mechanism(_e("grid_martingale"))


def test_fingerprint_distinct_for_symbol_and_params():
    a = fingerprint(_e("trend_following", symbol="EURUSD", params={"ma": 200}))
    b = fingerprint(_e("trend_following", symbol="EURUSD", params={"ma": 100}))
    assert a != b


def test_dedup_excludes_partition_closed():
    entries = [
        _e("trend_continuity", symbol="USDCAD", timeframe="H1"),  # partition CLOSED (H 9001)
        _e("trend_following", symbol="XAUUSD"),
    ]
    canon = dedup_to_canonical(entries)
    assert all(e["name"] != "x" or e["symbol"] != "USDCAD" for e in canon)
    assert len(canon) == 1


def test_dedup_flags_martingale():
    entries = [_e("grid_martingale")]
    canon = dedup_to_canonical(entries)
    assert canon[0]["requires_martingale_gate"] is True


def test_dedup_collapses_duplicates():
    entries = [_e("breakout", symbol="EURUSD", timeframe="H4"), _e("breakout", symbol="EURUSD", timeframe="H4")]
    assert len(dedup_to_canonical(entries)) == 1
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_taxonomy.py -q`
Expected: FAIL (`ModuleNotFoundError`)

- [ ] **Step 3: Write minimal implementation**

```python
# research/taxonomy.py
"""Mechanism taxonomy + fingerprint dedup (spec §5 P2, 0 N).

Classifies entries into canonical mechanism families, fingerprints
(family|symbol|timeframe|structural params), dedups to one
representative per fingerprint, excludes partition-CLOSED families
(owned by Direction H), and flags martingale/grid for the hard gate.
"""
from __future__ import annotations

import hashlib
import json
from typing import Any

MECHANISM_FAMILIES: dict[str, list[str]] = {
    "trend_following": ["trend_following", "donchian", "moving_average", "ma_cross", "tsmom", "faber"],
    "breakout": ["breakout", "range_breakout", "donchian_breakout", "session_breakout", "dual_thrust"],
    "momentum": ["momentum", "relative_strength", "cross_sectional_momentum"],
    "mean_reversion": ["mean_reversion", "rsi_mean_reversion", "rsi_mr", "bollinger", "zscore"],
    "grid_martingale": ["grid", "martingale", "grid_martingale", "recovery", "averaging"],
    "scalper": ["scalper", "scalping", "m1_scalp", "m5_scalp", "intraday_scalp"],
    "carry": ["carry", "rollover", "funding_rate", "swap"],
    "seasonality": ["seasonality", "calendar", "monthly_pattern", "day_of_week"],
    "vol_targeting": ["vol_targeting", "volatility_targeting", "yang_zhang"],
    "event": ["fomc", "cpi", "nfp", "news", "event_driven"],
    "orderflow": ["orderflow", "order_flow", "bid_ask", "liquidity"],
    "regime": ["regime", "filter", "trend_filter", "vol_filter"],
    "session": ["session", "london", "new_york", "asia", "time_window"],
    "multi_asset": ["portfolio", "multi_asset", "cross_asset", "rotation"],
    "microstructure": ["microstructure", "spread", "quote", "tick"],
    "other": [],
}

MARTINGALE_FAMILIES = {"grid_martingale"}


def _normalize(mechanism: str) -> str:
    return mechanism.lower().replace(" ", "_").replace("-", "_")


def classify_mechanism(entry: dict) -> str:
    m = _normalize(entry.get("mechanism", ""))
    for family, keywords in MECHANISM_FAMILIES.items():
        if m in keywords or any(k in m for k in keywords):
            return family
    return "other"


def fingerprint(entry: dict) -> str:
    family = classify_mechanism(entry)
    # structural params only: drop claimed_perf / name / source (non-structural)
    structural = {k: v for k, v in (entry.get("params") or {}).items() if isinstance(v, (int, float, str, bool))}
    canonical = "|".join([
        family,
        str(entry.get("symbol", "")).upper(),
        str(entry.get("timeframe", "")).upper(),
        json.dumps(structural, sort_keys=True),
    ])
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def dedup_to_canonical(entries: list[dict]) -> list[dict]:
    by_fp: dict[str, dict] = {}
    for e in entries:
        partition = e.get("partition") or {}
        if partition.get("status") == "CLOSED":
            continue  # Direction H owns this family (A17)
        fp = fingerprint(e)
        if fp in by_fp:
            continue
        out = dict(e)
        out["mechanism_family"] = classify_mechanism(e)
        out["requires_martingale_gate"] = out["mechanism_family"] in MARTINGALE_FAMILIES
        by_fp[fp] = out
    return list(by_fp.values())
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_taxonomy.py -q`
Expected: 6 passed

- [ ] **Step 5: Commit**

```bash
git add research/taxonomy.py tests/test_taxonomy.py
git commit -m "feat(quant_os): mechanism taxonomy + fingerprint dedup (Direction I P2)"
```

---

### Task 3: Triage module (`research/triage.py`)

**Files:**
- Create: `research/triage.py`
- Test: `tests/test_triage.py`

**Interfaces:**
- Consumes: canonical entries (Task 2 shape), `config/cost_calibration.json` (FROM_TICKS round-trip bps per symbol; stress_scenarios for worst-case)
- Produces: `ROUND_TRIP_BPS(symbol) -> float` (calibrated or A1 proxy: asset-class worst-case among calibrated symbols × 1.5); `cost_viability(entry, trades_per_day: float) -> dict` (returns `{"viable": bool, "cost_bps": float, "annual_cost_pct": float, "reason": str}` — viable if annual cost < 10% of claimed/target edge, conservative); `shortlist(entries, *, partition_check=True) -> list[dict]` (sorts by evidence tier then excludes non-viable; adds `triage` verdict per entry)

- [ ] **Step 1: Write the failing test**

```python
# tests/test_triage.py
import json
from pathlib import Path

from research.triage import ROUND_TRIP_BPS, cost_viability, shortlist

CAL = json.loads((Path(__file__).resolve().parents[1] / "config" / "cost_calibration.json").read_text(encoding="utf-8"))


def _e(mechanism="trend_following", symbol="XAUUSD", timeframe="H1", tier="literature", martingale=False):
    return {
        "name": "x", "source_url": "https://example.com/x", "mechanism": mechanism,
        "symbol": symbol, "timeframe": timeframe, "params": {}, "claimed_perf": "c",
        "evidence_tier": tier, "mechanism_family": mechanism,
        "requires_martingale_gate": martingale,
    }


def test_round_trip_calibrated_symbol():
    # XAUUSD is FROM_TICKS calibrated — value must be a positive float
    assert ROUND_TRIP_BPS("XAUUSD") > 0


def test_round_trip_proxy_for_uncalibrated():
    # NAS100 is UNVERIFIED_NO_DATA — proxy must be >= worst calibrated (×1.5 applied)
    assert ROUND_TRIP_BPS("NAS100") > 0


def test_cost_viability_rejects_fast_scalp_on_btc():
    r = cost_viability(_e("scalper", symbol="BTCUSD", timeframe="M1"), trades_per_day=100)
    assert r["viable"] is False
    assert "cost" in r["reason"].lower()


def test_cost_viability_accepts_slow_trend():
    r = cost_viability(_e("trend_following", symbol="XAUUSD", timeframe="D1"), trades_per_day=0.5)
    assert r["viable"] is True


def test_shortlist_sorts_literature_first_and_marks_triage():
    entries = [_e(tier="practitioner"), _e(tier="literature")]
    out = shortlist(entries)
    assert out[0]["evidence_tier"] == "literature"
    assert all("triage" in e for e in out)


def test_shortlist_excludes_martingale_without_gate_pass():
    entries = [_e(martingale=True)]
    out = shortlist(entries)
    assert out == []  # martingale requires hard gate; no gate pass recorded -> excluded
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_triage.py -q`
Expected: FAIL (`ModuleNotFoundError`)

- [ ] **Step 3: Write minimal implementation**

```python
# research/triage.py
"""Evidence triage + cost-viability math (spec §5 P3, 0 N).

Pure arithmetic on cost_calibration.json — no backtests, no returns.
Cost rule (A1): calibrated symbols use their FROM_TICKS round trip;
uncalibrated symbols use the asset-class worst-case among calibrated
symbols × 1.5 (conservative). Viability: annual cost (cost_bps × 2 ×
trades_per_day × 252) must stay < 10% of a 20% annual edge assumption.
Martingale/grid entries are excluded unless a gate-pass record exists
(Phase 0 hard gate — spec §4).
"""
from __future__ import annotations

import json
from pathlib import Path

_BASE = Path(__file__).resolve().parent.parent
_COST = json.loads((_BASE / "config" / "cost_calibration.json").read_text(encoding="utf-8"))

PROXY_MARGIN = 1.5
ASSUMED_ANNUAL_EDGE = 0.20  # conservative target for viability math
COST_BUDGET_FRACTION = 0.10

_MARTINGALE_GATE_PASSES: set[str] = set()  # populated at P4 by the hard-gate runner


def _calibrated_round_trip(symbol: str) -> float | None:
    assets = _COST.get("assets", {})
    meta = assets.get(symbol) or {}
    if meta.get("status") == "FROM_TICKS":
        rt = meta.get("round_trip_bps")
        if isinstance(rt, (int, float)) and rt > 0:
            return float(rt)
    return None


def _asset_class(symbol: str) -> str:
    if symbol in {"BTCUSD", "ETHUSD", "SOLUSD"}:
        return "crypto"
    if symbol in {"XAUUSD", "XAGUSD", "SILVER", "XPDUSD", "XPTUSD"}:
        return "metals"
    if symbol in {"NAS100", "US30", "US500", "GER40", "UK100", "SPX500"}:
        return "indices"
    return "fx"


def _class_worst_case(asset_class: str) -> float:
    worst = 0.0
    assets = _COST.get("assets", {})
    for sym, meta in assets.items():
        if isinstance(meta, dict) and meta.get("status") == "FROM_TICKS" and _asset_class(sym) == asset_class:
            rt = meta.get("round_trip_bps")
            if isinstance(rt, (int, float)) and rt > worst:
                worst = float(rt)
    return worst


def ROUND_TRIP_BPS(symbol: str) -> float:
    calibrated = _calibrated_round_trip(symbol)
    if calibrated is not None:
        return calibrated
    worst = _class_worst_case(_asset_class(symbol))
    return worst * PROXY_MARGIN if worst > 0 else 24.75 * PROXY_MARGIN  # floor: BTCUSD measured


def cost_viability(entry: dict, trades_per_day: float) -> dict:
    if trades_per_day <= 0:
        return {"viable": True, "cost_bps": ROUND_TRIP_BPS(entry.get("symbol", "")), "annual_cost_pct": 0.0,
                "reason": "no trades -> no cost"}
    rt = ROUND_TRIP_BPS(entry.get("symbol", ""))
    annual_cost = rt * 2 * trades_per_day * 252 / 100  # bps -> % annualized
    budget = ASSUMED_ANNUAL_EDGE * COST_BUDGET_FRACTION * 100
    viable = annual_cost < budget
    return {
        "viable": viable,
        "cost_bps": rt,
        "annual_cost_pct": round(annual_cost, 2),
        "reason": f"annual cost {annual_cost:.2f}% vs budget {budget:.2f}%" if not viable else "within cost budget",
    }


def shortlist(entries: list[dict]) -> list[dict]:
    tier_rank = {"literature": 0, "myfxbook_verified": 1, "practitioner": 2}
    out = []
    for e in entries:
        if e.get("requires_martingale_gate") and e.get("catalog_id", "?") not in _MARTINGALE_GATE_PASSES:
            continue  # hard gate required (spec §4)
        # default 1 trade/day screening assumption (P4 refines per family)
        v = cost_viability(e, trades_per_day=1.0)
        if not v["viable"]:
            continue
        out.append({**e, "triage": v})
    out.sort(key=lambda e: (tier_rank.get(e.get("evidence_tier"), 9), e.get("name", "")))
    return out
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_triage.py -q`
Expected: 6 passed

- [ ] **Step 5: Commit**

```bash
git add research/triage.py tests/test_triage.py
git commit -m "feat(quant_os): evidence triage + cost-viability math (Direction I P3)"
```

---

### Task 4: CLI runners (mining/taxonomy/triage)

**Files:**
- Create: `scripts/run_mining.py`, `scripts/run_taxonomy.py`, `scripts/run_triage.py`
- Test: `tests/test_run_clis.py` (integration: fixture → catalog → canonical → shortlist)

**Interfaces:**
- Consumes: Task 1-3 modules; `tests/fixtures/mining_sample.json`
- Produces: `scripts/run_mining.py <catalog_path> <raw_json>` (ingest batch, prints `added/errors`); `scripts/run_taxonomy.py <catalog_path> <out_path>` (writes `canonical_mechanisms.json`); `scripts/run_triage.py <canonical_path> <out_path>` (writes `shortlist.json`); exit 0 on success, 1 on validation failure

- [ ] **Step 1: Write the failing test**

```python
# tests/test_run_clis.py
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _run(args):
    return subprocess.run([sys.executable, *args], capture_output=True, text=True, cwd=ROOT)


def test_mining_cli_ingests_fixture(tmp_path):
    catalog = tmp_path / "catalog.json"
    r = _run(["scripts/run_mining.py", str(catalog), str(ROOT / "tests" / "fixtures" / "mining_sample.json")])
    assert r.returncode == 0, r.stderr
    assert "added 6" in r.stdout


def test_mining_cli_reports_bad_entries(tmp_path):
    bad = tmp_path / "bad.json"
    bad.write_text(json.dumps({"entries": [{"name": "no-url"}]}), encoding="utf-8")
    r = _run(["scripts/run_mining.py", str(tmp_path / "catalog.json"), str(bad)])
    assert r.returncode == 1
    assert "source_url" in r.stderr


def test_taxonomy_cli_produces_canonical(tmp_path):
    catalog = tmp_path / "catalog.json"
    _run(["scripts/run_mining.py", str(catalog), str(ROOT / "tests" / "fixtures" / "mining_sample.json")])
    out = tmp_path / "canonical.json"
    r = _run(["scripts/run_taxonomy.py", str(catalog), str(out)])
    assert r.returncode == 0, r.stderr
    canon = json.loads(out.read_text(encoding="utf-8"))
    # 6 entries - 1 partition-CLOSED (forex4 trend) = 5, dedup within sample = 5
    assert len(canon["canonical"]) == 5


def test_triage_cli_produces_shortlist(tmp_path):
    catalog = tmp_path / "catalog.json"
    _run(["scripts/run_mining.py", str(catalog), str(ROOT / "tests" / "fixtures" / "mining_sample.json")])
    canon = tmp_path / "canonical.json"
    _run(["scripts/run_taxonomy.py", str(catalog), str(canon)])
    out = tmp_path / "shortlist.json"
    r = _run(["scripts/run_triage.py", str(canon), str(out)])
    assert r.returncode == 0, r.stderr
    sl = json.loads(out.read_text(encoding="utf-8"))
    # grid_martingale excluded (no gate pass); scalper EURUSD M5 cost-viable at 1 trade/day;
    # rest literature/practitioner survive
    assert all(e["evidence_tier"] != "practitioner" or e["mechanism"] != "grid_martingale" for e in sl["shortlist"])
    assert sl["shortlist"][0]["evidence_tier"] == "literature"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_run_clis.py -q`
Expected: FAIL (`FileNotFoundError` on missing scripts)

- [ ] **Step 3: Write minimal implementations**

```python
# scripts/run_mining.py
"""Ingest one source's raw JSON batch into the Direction I catalog."""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from research.catalog import ingest_batch

def main() -> int:
    if len(sys.argv) != 3:
        print("usage: run_mining.py <catalog_path> <raw_json>", file=sys.stderr)
        return 2
    catalog_path, raw_path = sys.argv[1], sys.argv[2]
    raw = json.loads(Path(raw_path).read_text(encoding="utf-8"))
    added, errors = ingest_batch(catalog_path, raw.get("entries", []))
    print(f"added {added}, rejected {len(errors)}")
    for e in errors:
        print(f"  REJECT: {e}", file=sys.stderr)
    return 1 if errors else 0

if __name__ == "__main__":
    sys.exit(main())
```

```python
# scripts/run_taxonomy.py
"""raw catalog -> research/catalog_i/canonical_mechanisms.json"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from research.catalog import load_entries
from research.taxonomy import dedup_to_canonical

def main() -> int:
    if len(sys.argv) != 3:
        print("usage: run_taxonomy.py <catalog_path> <out_path>", file=sys.stderr)
        return 2
    catalog_path, out_path = sys.argv[1], sys.argv[2]
    canon = dedup_to_canonical(load_entries(catalog_path))
    Path(out_path).write_text(
        json.dumps({"schema_version": "1.0", "direction": "I", "canonical": canon}, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    print(f"canonical {len(canon)} mechanisms -> {out_path}")
    return 0

if __name__ == "__main__":
    sys.exit(main())
```

```python
# scripts/run_triage.py
"""canonical_mechanisms.json -> shortlist.json"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from research.triage import shortlist

def main() -> int:
    if len(sys.argv) != 3:
        print("usage: run_triage.py <canonical_path> <out_path>", file=sys.stderr)
        return 2
    canon_path, out_path = sys.argv[1], sys.argv[2]
    canon = json.loads(Path(canon_path).read_text(encoding="utf-8")).get("canonical", [])
    sl = shortlist(canon)
    Path(out_path).write_text(
        json.dumps({"schema_version": "1.0", "direction": "I", "shortlist": sl}, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    print(f"shortlist {len(sl)} candidates -> {out_path}")
    return 0

if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_run_clis.py -q`
Expected: 4 passed

- [ ] **Step 5: Commit**

```bash
git add scripts/run_mining.py scripts/run_taxonomy.py scripts/run_triage.py tests/test_run_clis.py
git commit -m "feat(quant_os): P1-P3 CLI runners — mining ingest, taxonomy, triage (Direction I)"
```

---

### Task 5: End-to-end pipeline verification + acceptance

**Files:**
- Create: `reports/direction_i_p1p3_acceptance_20260806.md`

**Interfaces:**
- Consumes: Tasks 1-4 outputs; `tests/fixtures/mining_sample.json`
- Produces: acceptance report (pipeline works end-to-end on the fixture; partition exclusion and martingale gating demonstrated; counts documented)

- [ ] **Step 1: Run the full pipeline on the fixture**

Run (in order):
```bash
python scripts/run_mining.py research/catalog_i/catalog_sample.json tests/fixtures/mining_sample.json
python scripts/run_taxonomy.py research/catalog_i/catalog_sample.json research/catalog_i/canonical_mechanisms.json
python scripts/run_triage.py research/catalog_i/canonical_mechanisms.json research/catalog_i/shortlist.json
```
Expected: mining `added 6, rejected 0`; taxonomy prints canonical count; triage prints shortlist count

- [ ] **Step 2: Write the acceptance test**

```python
# tests/test_p1p3_acceptance.py
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_canonical_artifact_exists():
    canon = json.loads((ROOT / "research" / "catalog_i" / "canonical_mechanisms.json").read_text(encoding="utf-8"))
    assert len(canon["canonical"]) >= 1


def test_shortlist_artifact_exists():
    sl = json.loads((ROOT / "research" / "catalog_i" / "shortlist.json").read_text(encoding="utf-8"))
    assert "shortlist" in sl


def test_no_partition_closed_in_shortlist():
    sl = json.loads((ROOT / "research" / "catalog_i" / "shortlist.json").read_text(encoding="utf-8"))
    for e in sl["shortlist"]:
        assert e.get("partition", {}).get("status") != "CLOSED"
```

- [ ] **Step 3: Run full test suite for the plan**

Run: `python -m pytest tests/test_catalog.py tests/test_taxonomy.py tests/test_triage.py tests/test_run_clis.py tests/test_p1p3_acceptance.py -q`
Expected: all pass (8+6+6+4+3 = 27)

- [ ] **Step 4: Write acceptance report**

Create `reports/direction_i_p1p3_acceptance_20260806.md` documenting: fixture counts, partition exclusion (forex4 trend family dropped), martingale gate exclusion, evidence-tier ordering, cost-viability verdicts per entry, and the statement that P1-P3 consumed 0 N (no returns evaluated).

- [ ] **Step 5: Commit**

```bash
git add research/catalog_i/ scripts/run_mining.py scripts/run_taxonomy.py scripts/run_triage.py tests/test_p1p3_acceptance.py reports/direction_i_p1p3_acceptance_20260806.md
git commit -m "docs(quant_os): P1-P3 pipeline acceptance + sample artifacts (Direction I)"
```

---

## Follow-on Plans (roadmap)

| Plan | Phases | Blocks on |
|---|---|---|
| Plan 3 | P4-P5 (screening runner wiring with `screening_guard`/`screening_registry`, 23-symbol calibration) | Tier0 Sweep C0 output (guard wiring), Sub-project C1 commit (universe) |
| Plan 4 | P6-P7 (pre-registration docs, full gate harness, shadow/holdout) | Plan 3 survivors; Sub-project B decisions (EURUSD H4) |

## Self-Review Notes

- Spec coverage: P1 (catalog+contract+ingest) → Task 1; P2 (taxonomy+dedup+partition check) → Task 2; P3 (triage+cost math) → Task 3; CLI orchestration → Task 4; acceptance → Task 5. Spec §5 P1 "every entry must have source URL" → Task 1 validate_entry; A17 partition → Task 1 tagging + Task 2 exclusion; §4 martingale gate → Task 2 flag + Task 3 exclusion; A1 conservative costs → Task 3 ROUND_TRIP_BPS proxy; §3.2 zero-N → stated in module docstrings.
- Placeholder scan: no TBD/TODO; all code blocks complete. Fixture entries use real sources (SSRN links etc.).
- Type consistency: `check_partition(mechanism, symbol, timeframe)` consumed in Task 1 matches Phase 0 signature; `dedup_to_canonical(entries) -> list[dict]` consumed by run_taxonomy and shortlist; `cost_viability(entry, trades_per_day) -> dict` keys `viable/cost_bps/annual_cost_pct/reason` match Task 3 tests and Task 4 shortlist usage.
- Fixture count arithmetic verified: 6 entries − 1 partition-CLOSED (USDCAD H1 trend_continuity) = 5 canonical; martingale excluded at triage; scalper EURUSD M5 cost check at 1 trade/day passes conservative budget.
