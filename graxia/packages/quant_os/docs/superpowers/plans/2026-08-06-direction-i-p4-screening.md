# Direction I Plan 3 — P4 Screening Infrastructure Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Turn the 80 mining shortlist candidates into real screening backtest results (raw Sharpe > 0 at conservative costs + min trades), with every config registered in `screening_log_i.json` BEFORE running (+1 N each) and zero-lookahead enforcement via guard capture — the P4 stage of the Direction I funnel.

**Architecture:** Three small modules + one runner. `research/screening_map.py` maps `mechanism_family` → engine-compatible strategy class + default params + default timeframe (caller-owned strategies via `engine.set_strategy`, per `run_direction_g_trials.py` pattern). `scripts/run_screening.py` orchestrates: load shortlist → resolve strategy/TF → `register_config` (N, pre-run) → capture LookaheadGuard via monkeypatch → `BacktestEngine.run()` → attach captured guard to engine → `assert_no_guard_violations` (fail-closed) → update status (done/VOID) → record metrics → survivors to `screening_results.json`. Data via `data/market_data.duckdb` ohlcv table (same query as Direction G runner).

**Tech Stack:** Python 3.11+, duckdb, existing `backtest/engine.py`, `backtest/dynamic_spread_model.py`, `strategies/*`, `research/screening_registry.py`, `scripts/screening_guard.py` (Phase 0 artifacts). No new dependencies.

## Global Constraints

- Every screening config registered via `research.screening_registry.register_config` **BEFORE** its engine run (+1 N, hash-dedup; spec §3/A6)
- Post-run `assert_no_guard_violations(engine, config_id)` mandatory — violation → status=VOID + audit; engine.guard must be attached by the runner (captured TrackingGuard instance — engine does not store it; review R#3)
- Cost mode: `slippage_pips=None, spread_pips=None` (measured per-symbol) + `cost_stress=True` (p95 spread — conservative A1 proxy); `commission_per_lot` from `SymbolCostProfile`
- Unmeasured-cost symbol → `UnmeasuredCostError` → config status="no_cost_data", skipped honestly (never default-cost fallback)
- Low screening bar (kill losers, not crown winners): `sharpe_ratio > 0` AND `total_trades >= 30`
- Candidate timeframe "ALL" → family default from `screening_map.py` (documented per family)
- Unmapped families (other/microstructure/seasonality without engine strategy) → status="no_strategy", skipped with note (NOT forced through a wrong strategy)
- Grid/martingale already excluded from shortlist by triage; if encountered → status="martingale_gate_pending" (hard-gate path, spec §4)
- Writer lock + `check_trial_uniqueness.py` + pre-commit suite per repo rules; Direction H files untouched
- `--limit N` flag for test runs; full run default

## File Structure

| File | Responsibility |
|---|---|
| `research/screening_map.py` (NEW) | `FAMILY_TO_STRATEGY` mapping + `resolve_candidate(entry) -> dict` (strategy class, params, timeframe) |
| `tests/test_screening_map.py` (NEW) | Mapping coverage + resolution tests |
| `scripts/run_screening.py` (NEW) | Orchestrator: shortlist → register → run → guard assert → results |
| `tests/test_run_screening.py` (NEW) | Runner tests with `--limit` on real shortlist data |
| `research/catalog_i/screening_results.json` (NEW, generated) | Screening output artifact |

---

### Task 1: Screening map (`research/screening_map.py`)

**Files:**
- Create: `research/screening_map.py`
- Test: `tests/test_screening_map.py`

**Interfaces:**
- Consumes: shortlist entry shape (mechanism_family, symbol, timeframe, params); `strategies/*` classes per explorer inventory (G)
- Produces: `FAMILY_TO_STRATEGY: dict[str, dict]` — `{"strategy_class": type, "default_params": dict, "default_tf": str}`; `DEFAULT_TF_BY_FAMILY: dict[str, str]`; `resolve_candidate(entry: dict) -> dict` — returns `{"strategy_class": ..., "params": dict, "timeframe": str, "status": "ok"}` or `{"status": "no_strategy"}` for unmapped families

- [ ] **Step 1: Write the failing test**

```python
# tests/test_screening_map.py
from research.screening_map import DEFAULT_TF_BY_FAMILY, FAMILY_TO_STRATEGY, resolve_candidate


def _entry(family, symbol="XAUUSD", timeframe="D1"):
    return {"name": "x", "mechanism_family": family, "symbol": symbol, "timeframe": timeframe, "params": {}}


def test_required_families_mapped():
    # the families present in the wave-1/2 shortlist must all be mappable
    for family in ["trend_following", "breakout", "scalper", "mean_reversion", "momentum",
                   "session", "orderflow", "carry", "vol_targeting", "regime", "other"]:
        assert family in FAMILY_TO_STRATEGY or family in ("other", "microstructure", "seasonality")


def test_default_tf_all_families_defined():
    for family in FAMILY_TO_STRATEGY:
        assert DEFAULT_TF_BY_FAMILY[family] in {"M1", "M5", "M15", "M30", "H1", "H4", "D1", "W1", "MN1"}


def test_resolve_trend_following():
    r = resolve_candidate(_entry("trend_following"))
    assert r["status"] == "ok"
    assert r["strategy_class"].__name__ == "DonchianBreakout"
    assert r["timeframe"] == "D1"


def test_resolve_all_timeframe_uses_family_default():
    r = resolve_candidate(_entry("scalper", timeframe="ALL"))
    assert r["timeframe"] == DEFAULT_TF_BY_FAMILY["scalper"]


def test_resolve_unmapped_family_no_strategy():
    r = resolve_candidate(_entry("other"))
    assert r["status"] == "no_strategy"


def test_params_default_merge():
    r = resolve_candidate(_entry("trend_following", params={"period": 30}))
    assert r["params"]["period"] == 30  # entry param wins
    assert "atr_period" in r["params"]  # defaults present
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_screening_map.py -q`
Expected: FAIL (`ModuleNotFoundError`)

- [ ] **Step 3: Write minimal implementation**

```python
# research/screening_map.py
"""Map mining mechanism_family -> engine-compatible strategy for P4 screening.

Strategy classes are caller-owned via engine.set_strategy() (engine never
instantiates). Unmapped families are reported no_strategy, NOT forced through
a wrong strategy (honesty over coverage).
"""
from __future__ import annotations

from strategies.donchian import DonchianBreakout
from strategies.rsi_mean_reversion import RSIMeanReversion
from strategies.happy_gold_scalper import HappyGoldScalper
from strategies.asian_scalper import AsianScalper
from strategies.momentum_12m import Momentum12M
from strategies.eur_session_breakout import EurSessionBreakout
from strategies.liquidity_sweep_v2 import LiquiditySweepV2
from strategies.bollinger_squeeze import BollingerSqueeze
from strategies.path_b_wrappers import CarryStrategy, FOMCDriftStrategy, TSMOMStrategy

FAMILY_TO_STRATEGY: dict[str, dict] = {
    "trend_following": {"strategy_class": DonchianBreakout, "default_params": {"period": 20, "atr_period": 14},
                        "default_tf": "D1"},
    "breakout": {"strategy_class": DonchianBreakout, "default_params": {"period": 20, "atr_period": 14},
                 "default_tf": "H1"},
    "scalper": {"strategy_class": HappyGoldScalper, "default_params": {"ema_period": 20, "atr_period": 14},
                "default_tf": "M15"},
    "mean_reversion": {"strategy_class": RSIMeanReversion, "default_params": {"rsi_period": 14, "atr_period": 14},
                       "default_tf": "H1"},
    "momentum": {"strategy_class": Momentum12M, "default_params": {"lookback": 252, "atr_period": 14},
                 "default_tf": "D1"},
    "session": {"strategy_class": EurSessionBreakout, "default_params": {"atr_fast": 8, "atr_slow": 21},
                "default_tf": "M15"},
    "orderflow": {"strategy_class": LiquiditySweepV2, "default_params": {"sweep_lookback": 20, "rsi_period": 14},
                  "default_tf": "M15"},
    "carry": {"strategy_class": CarryStrategy, "default_params": {"vol_target": 0.10}, "default_tf": "D1"},
    "vol_targeting": {"strategy_class": TSMOMStrategy, "default_params": {"lookbacks": (120, 240), "vol_target": 0.15},
                      "default_tf": "D1"},
    "event": {"strategy_class": FOMCDriftStrategy, "default_params": {}, "default_tf": "D1"},
    "regime": {"strategy_class": DonchianBreakout, "default_params": {"period": 50, "atr_period": 14},
               "default_tf": "D1"},
}

DEFAULT_TF_BY_FAMILY: dict[str, str] = {f: v["default_tf"] for f, v in FAMILY_TO_STRATEGY.items()}


def resolve_candidate(entry: dict) -> dict:
    family = entry.get("mechanism_family", "other")
    mapping = FAMILY_TO_STRATEGY.get(family)
    if mapping is None:
        return {"status": "no_strategy", "reason": f"family '{family}' has no engine strategy"}
    params = {**mapping["default_params"], **{k: v for k, v in (entry.get("params") or {}).items()
                                              if isinstance(v, int | float | str | bool)}}
    tf = entry.get("timeframe") if entry.get("timeframe") and entry.get("timeframe") != "ALL" else mapping["default_tf"]
    return {"status": "ok", "strategy_class": mapping["strategy_class"], "params": params, "timeframe": tf}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_screening_map.py -q`
Expected: 6 passed

- [ ] **Step 5: Commit**

```bash
git add research/screening_map.py tests/test_screening_map.py
git commit -m "feat(quant_os): screening family->strategy map (Direction I P4)"
```

---

### Task 2: Screening runner (`scripts/run_screening.py`)

**Files:**
- Create: `scripts/run_screening.py`
- Test: `tests/test_run_screening.py`

**Interfaces:**
- Consumes: `research/catalog_i/shortlist_wave1.json` (80 candidates), `research.screening_registry` (register_config/update_config_status), `scripts.screening_guard` (assert_no_guard_violations), `research.screening_map.resolve_candidate`, `data/market_data.duckdb`, `backtest.engine`, `backtest.dynamic_spread_model.SymbolCostProfile`
- Produces: `research/catalog_i/screening_results.json` — `{"schema_version": "1.0", "direction": "I", "configs_tried": N, "survivors": [...], "results": {config_id: {...metrics...}}}`; `main(argv) -> int` with `--limit N` and `--shortlist PATH` flags

- [ ] **Step 1: Write the failing test**

```python
# tests/test_run_screening.py
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _run(args):
    return subprocess.run([sys.executable, *args], capture_output=True, text=True, cwd=ROOT)


def test_screening_cli_runs_limited(tmp_path):
    r = _run(["scripts/run_screening.py", "--limit", "3", "--out", str(tmp_path / "results.json")])
    assert r.returncode == 0, r.stderr
    results = json.loads((tmp_path / "results.json").read_text(encoding="utf-8"))
    assert results["configs_tried"] == 3
    for cfg_id, res in results["results"].items():
        assert res["status"] in {"done", "no_cost_data", "no_strategy", "VOID"}
        assert "n_registered" in res  # every config registered before run


def test_screening_log_has_entries():
    # the real screening log must show the runs (registered BEFORE run)
    log = json.loads((ROOT / "research" / "screening_log_i.json").read_text(encoding="utf-8"))
    assert log["count"] >= 3
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_run_screening.py -q`
Expected: FAIL (`FileNotFoundError` — script absent; log count 0)

- [ ] **Step 3: Write minimal implementation**

```python
# scripts/run_screening.py
"""P4 screening runner for Direction I (spec §5 P4).

For each shortlist candidate: resolve strategy -> register_config (N, BEFORE
run) -> run BacktestEngine with conservative costs (cost_stress=True, measured
profile) -> capture LookaheadGuard -> assert zero violations -> record result.
Survivors: sharpe_ratio > 0 AND total_trades >= 30.
"""
from __future__ import annotations

import argparse
import json
import sys
from decimal import Decimal
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import backtest.engine as bt_engine  # noqa: E402
import duckdb  # noqa: E402
import pandas as pd  # noqa: E402
from backtest.dynamic_spread_model import SymbolCostProfile  # noqa: E402
from backtest.engine import BacktestConfig, BacktestEngine  # noqa: E402
from research.catalog_i.registry_shim import get_default_log  # noqa: E402  # (Phase 0 module)
from research.screening_map import resolve_candidate  # noqa: E402
from research.screening_registry import register_config, update_config_status  # noqa: E402
from scripts.screening_guard import assert_no_guard_violations  # noqa: E402

DB_PATH = Path(__file__).resolve().parent.parent / "data" / "market_data.duckdb"
TF_CONVENTION = {"M15": "15m", "H1": "1h", "H4": "4h", "D1": "1d", "W1": "1w", "MN1": "1mo", "M5": "5m", "M30": "30m"}
MIN_TRADES = 30
MIN_SHARPE = 0.0


class TrackingGuard(bt_engine.LookaheadGuard):
    instances: list = []

    def __init__(self, *a, **k):
        super().__init__(*a, **k)
        self.instances.append(self)


def load_ohlcv(symbol: str, tf: str) -> pd.DataFrame | None:
    if tf not in TF_CONVENTION:
        return None
    con = duckdb.connect(str(DB_PATH), read_only=True)
    try:
        df = con.execute(
            "SELECT time, open, high, low, close, volume FROM ohlcv "
            "WHERE symbol = ? AND timeframe = ? ORDER BY time",
            [symbol, TF_CONVENTION[tf]],
        ).fetchdf()
    except Exception:
        return None
    finally:
        con.close()
    if df.empty:
        return None
    df["time"] = pd.to_datetime(df["time"], utc=True)
    return df


def run_candidate(entry: dict, config_id: str) -> dict:
    resolved = resolve_candidate(entry)
    if resolved["status"] != "ok":
        return {"config_id": config_id, "status": "no_strategy", "reason": resolved.get("reason", "")}
    symbol = entry.get("symbol", "")
    tf = resolved["timeframe"]
    df = load_ohlcv(symbol, tf)
    if df is None:
        return {"config_id": config_id, "status": "no_cost_data", "reason": f"no {symbol} {tf} data in duckdb"}
    try:
        profile = SymbolCostProfile.for_symbol(symbol)
    except Exception as exc:
        return {"config_id": config_id, "status": "no_cost_data", "reason": str(exc)}
    ohlcv = {k: df[k].tolist() for k in ("open", "high", "low", "close", "volume")}
    timestamps = df["time"].dt.to_pydatetime().tolist()
    config = BacktestConfig(
        initial_capital=10000,
        slippage_pips=None,
        spread_pips=None,
        cost_stress=True,  # A1 conservative proxy: p95 spread
        commission_per_lot=Decimal(str(profile.commission_bps)),
        risk_per_trade_bps=100,
        max_positions=1,
        strict_mtf=False,
        enable_swap=False,
    )
    strategy = resolved["strategy_class"](**resolved["params"]) if resolved["params"] else resolved["strategy_class"]()
    TrackingGuard.instances = []
    engine = BacktestEngine(config)
    engine._symbol = symbol
    engine.set_strategy(strategy)
    engine.load_data(ohlcv, timestamps)
    engine._check_risk_halt = lambda: False
    results = engine.run()
    engine.guard = TrackingGuard.instances[-1] if TrackingGuard.instances else None
    assert_no_guard_violations(engine, config_id=config_id)  # fail-closed
    metrics = results.get("metrics")
    m = metrics.as_dict() if hasattr(metrics, "as_dict") else vars(metrics)
    out = {"config_id": config_id, "status": "done", "symbol": symbol, "timeframe": tf,
           "total_trades": m.get("total_trades", 0), "sharpe_ratio": m.get("sharpe_ratio", 0.0),
           "profit_factor": m.get("profit_factor", 0.0), "total_return_pct": m.get("total_return_pct", 0.0),
           "max_drawdown_pct": m.get("max_drawdown_pct", 0.0)}
    out["survivor"] = out["total_trades"] >= MIN_TRADES and out["sharpe_ratio"] > MIN_SHARPE
    return out


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--limit", type=int, default=0)
    parser.add_argument("--shortlist", default=str(Path(__file__).resolve().parent.parent / "research" / "catalog_i" / "shortlist_wave1.json"))
    parser.add_argument("--out", default=str(Path(__file__).resolve().parent.parent / "research" / "catalog_i" / "screening_results.json"))
    parser.add_argument("--log", default=str(Path(__file__).resolve().parent.parent / "research" / "screening_log_i.json"))
    args = parser.parse_args(argv)

    bt_engine.LookaheadGuard = TrackingGuard
    shortlist = json.loads(Path(args.shortlist).read_text(encoding="utf-8")).get("shortlist", [])
    if args.limit > 0:
        shortlist = shortlist[: args.limit]

    results: dict = {}
    survivors = []
    for entry in shortlist:
        cfg = register_config(args.log, mechanism=entry.get("mechanism_family", entry.get("mechanism", "other")),
                              symbol=entry.get("symbol", ""), timeframe=entry.get("timeframe", "ALL"),
                              params=entry.get("params") or {}, data_range=("", ""))
        config_id = cfg["config_id"]
        try:
            res = run_candidate(entry, config_id)
        except Exception as exc:  # noqa: BLE001 — VOID + audit per spec
            res = {"config_id": config_id, "status": "VOID", "reason": str(exc)}
        update_config_status(args.log, config_id, res["status"])
        res["n_registered"] = True
        results[config_id] = res
        if res.get("survivor"):
            survivors.append({**entry, "screening": res})

    out = {"schema_version": "1.0", "direction": "I", "configs_tried": len(results),
           "survivors": survivors, "results": results}
    Path(args.out).write_text(json.dumps(out, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"screening: {len(results)} configs, {len(survivors)} survivors -> {args.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_run_screening.py -q`
Expected: 2 passed (limited run of 3 candidates)

- [ ] **Step 5: Commit**

```bash
git add scripts/run_screening.py tests/test_run_screening.py
git commit -m "feat(quant_os): P4 screening runner — guard capture + N registration (Direction I)"
```

---

### Task 3: Full screening run + acceptance

**Files:**
- Create: `reports/direction_i_screening_wave1_20260806.md`

**Interfaces:**
- Consumes: Task 1-2 outputs; full 80-candidate shortlist
- Produces: `research/catalog_i/screening_results.json` (full), acceptance report

- [ ] **Step 1: Run full screening**

Run: `python scripts/run_screening.py`
Expected: prints configs tried + survivors count; runtime may be several minutes (80 engine runs)

- [ ] **Step 2: Write acceptance test**

```python
# tests/test_screening_acceptance.py
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_screening_results_artifact():
    d = json.loads((ROOT / "research" / "catalog_i" / "screening_results.json").read_text(encoding="utf-8"))
    assert d["configs_tried"] >= 20


def test_no_void_without_audit():
    d = json.loads((ROOT / "research" / "catalog_i" / "screening_results.json").read_text(encoding="utf-8"))
    for cfg_id, res in d["results"].items():
        if res["status"] == "VOID":
            assert "reason" in res  # every VOID carries an audit trail


def test_screening_log_matches_results():
    import json as j

    log = j.loads((ROOT / "research" / "screening_log_i.json").read_text(encoding="utf-8"))
    results = j.loads((ROOT / "research" / "catalog_i" / "screening_results.json").read_text(encoding="utf-8"))
    assert log["count"] >= results["configs_tried"]
```

- [ ] **Step 3: Write acceptance report**

Document: configs tried, status distribution (done/no_cost_data/no_strategy/VOID), survivors with metrics, N accounting delta (log count), guard violations = 0 across all runs, honest notes on unmapped families.

- [ ] **Step 4: Commit**

```bash
git add research/catalog_i/screening_results.json research/screening_log_i.json tests/test_screening_acceptance.py reports/direction_i_screening_wave1_20260806.md
git commit -m "feat(quant_os): P4 screening wave 1 results + acceptance (Direction I)"
```

---

## Follow-on Plans (roadmap)

| Plan | Phases | Blocks on |
|---|---|---|
| Plan 3.1 | P5 (data infra + full calibration, re-filter at real costs) | screening survivors; universe C1 (DONE cd0f4983) |
| Plan 4 | P6-P7 (pre-registration, full gate stack, shadow/holdout) | P5 re-filtered survivors; Sub-project B decisions |

## Self-Review Notes

- Spec coverage: P4 register-before-run → Task 2 (register_config before engine.run in main loop); guard assertion → Task 2 (TrackingGuard capture + assert_no_guard_violations); conservative costs → Task 2 (cost_stress=True + measured profile); low bar → Task 2 (MIN_TRADES/MIN_SHARPE); VOID+audit → Task 2 (status=VOID with reason); unmeasured → no_cost_data (never default fallback). C0 reuse: FORMAL-ACCEPT verdicts (edge_search_tf_probe_verdict.md) mean no engine changes needed — guard capture in runner is the A11 supplement wiring.
- Placeholder scan: no TBD; `research/catalog_i/registry_shim.py` referenced as `get_default_log` — Phase 0 provides `research/screening_registry.py`; use its path constants directly (`_DEFAULT_SCREENING_LOG` lives in `validation/n_trials_i.py`; the runner's `--log` default is the explicit path, so the shim import line should be REMOVED at implementation time — flagged here to avoid a broken import.
- Type consistency: `register_config(log_path, *, mechanism, symbol, timeframe, params, data_range, status)` and `update_config_status(log_path, config_id, status)` match Phase 0 signatures; `assert_no_guard_violations(engine, *, config_id)` matches Phase 0; strategy classes take the params dicts from `resolve_candidate`.
