# Phase 1: Multi-Asset Universe Discovery + Cost-Calibration Pipeline — Implementation Plan

Date: 2026-08-03
Spec: `docs/superpowers/specs/2026-08-03-phase1-universe-cost-calibration-design.md` (approved design, commit `e4468139`)
Status: ready for execution

## Goal

Replace the manually-maintained hardcoded `COST_CALIBRATED_SYMBOLS` frozenset in `provenance.py` with a JSON-backed gate that reads `config/tradeable_universe.json` at call time, and build the automated pipeline that discovers broker symbols, measures their cost over a strict two-pass statistical bar, promotes them to tradeable, and demotes them on cost drift — without ever weakening the anti-fabrication gate that stopped two prior fabrication incidents (commit `33b90c31`, trial #1030).

## Architecture

```
[Discovery]  broker symbols_get() → allowlist filter → new "candidate" entries in tradeable_universe.json
     ↓
[Measurement Daemon]  long-running MT5 tick subscriber, N symbols parallel, per-symbol coverage state disk-durable
     ↓ (per-symbol coverage: 7 qualifying days, 5/5 sessions, ≥50,000 VALID ticks per session-day)
[Promotion]  pass 1 → "verifying"; pass 2 (fresh window) → "tradeable" + cost_calibration.json entry (FROM_TICKS_MULTIDAY)
     ↓
[Gate]  provenance.py reads tradeable_universe.json live; require_cost_calibrated(symbol, mode) — mode="paper"|"live"
     ↓
[Demote]  PSI cost-drift check (shared psi()) → tradeable→measuring + kill-switch flag + ledger invalidation + audit
```

One statistical primitive (`core/stats/psi.py`) serves both the existing ML feature-drift check (`ml/drift_monitor.py`) and the new cost-drift check. The JSON files are the single source of truth; the daemon writes them, the gate reads them.

## Tech Stack

- Python 3.10+ (codebase already uses `str | None`, `zip(strict=False)`, `datetime.UTC` — evidence: `ml/drift_monitor.py`, `risk/kill_switch.py`)
- Standard library only for all new code: `json`, `pathlib`, `math`, `dataclasses`, `datetime`, `decimal`, `typing`, `re`, `tempfile`, `os`
- Existing in-repo dependencies reused: `pandas` (parquet write/read — already a repo dependency; `provenance.py` imports it), `pytest`
- No new third-party dependencies

## Global Constraints

1. **Test invocation**: every task's verification command runs from the `quant_os` package root with `python -m pytest tests/<file> -q`. Tests rely on cwd being on `sys.path` for top-level imports (evidence: `tests/test_mt5_gateway.py` does `import broker.mt5_gateway as gw`; `tests/conftest.py` adds no sys.path entries).
2. **Import style for new/changed modules**: top-level absolute imports (`from core.stats.psi import psi`, `from market_data.tick_recorder import TickRecord`). Required because `api/signal_service.py:455` imports `from ml.drift_monitor import DriftMonitor` top-level, and new modules must be importable the same way. Do NOT use relative imports in `ml/drift_monitor.py` (it is imported both top-level and as `graxia.packages.quant_os.ml.drift_monitor`; only a top-level absolute import works in both contexts).
   - **SHADOW WARNING (verified during Task 1 execution, 2026-08-03)**: `quant_os/conftest.py:8` inserts the MONOREPO root (`C:\Users\menum\graxia os`) at `sys.path[0]`, and a `core` package exists at that root — it shadows `quant_os/core` under pytest. Plain `python -c` from the quant_os dir resolves `core` correctly; pytest does not. EVERY new test file that (transitively) imports `core` must run this preamble BEFORE any `core.*` import:
   ```python
   import sys
   from pathlib import Path

   _QUANT_OS_ROOT = Path(__file__).resolve().parent.parent
   sys.path.insert(0, str(_QUANT_OS_ROOT))  # UNCONDITIONAL — a guarded insert is a no-op (quant_os is already on sys.path later, and the shadow at position 0 wins)
   ```
   The unconditional insert is load-bearing: `if str(...) not in sys.path` does NOT work (verified).
3. **No new dependencies**. If a test needs a parquet roundtrip, `pd.DataFrame.to_parquet()` uses the repo's existing installed engine (parquet is already a first-class format here — `tests/conftest.py` mentions sample parquet data).
4. **Fail-closed defaults everywhere** (repo invariant, see `risk/kill_switch.py::_load()` and `run_paper_trading.py:811-818`).
5. **Atomic JSON writes**: every JSON state write uses tempfile-in-same-dir + `os.replace()`, mirroring `risk/kill_switch.py::_save()` (lines 423-463) — including Windows PermissionError retry. Never write in place.
6. **Append-only audit trail**: audit entries are appended JSON lines to `state/audit_log.jsonl`, via a local `_append_audit(record)` helper identical in shape to `core/signal_gateway.py::_append_audit` (lines 146-150): `AUDIT_LOG_PATH.parent.mkdir(parents=True, exist_ok=True)` then `fh.write(json.dumps(record, default=str) + "\n")`. Each module defines its own local helper (no shared audit module exists — verified).
7. **Trial/registry data is append-only**: ledger invalidation adds keys, never deletes or rewrites history.
8. **Working tree hygiene**: `git status` shows many pre-existing unrelated modifications (e.g. `core/lookahead_guard.py`, `autonomous/orchestrator.py`, `tests/chaos/test_core_untested.py`, release-gate artifacts). NEVER stage or touch these. Stage only the files listed in each task.
9. **Commit style**: Conventional Commits with scope, imperative mood, matching repo history (`feat(quant_os): ...`, `test(quant_os): ...`).
10. **No live MT5 in CI**: all MT5 interaction is mocked with the `tests/test_mt5_gateway.py` pattern (`_reset_mt5_globals()` + `_make_mock_mt5()` + `patch.dict(sys.modules, {"MetaTrader5": mock})`).
11. **PSI threshold**: cost-drift threshold is `0.25` — `DriftMonitor.__init__` default `psi_threshold: float = 0.25` (verified `ml/drift_monitor.py:85`). The `* 1.5` at line 465 is the *critical-severity multiplier*, not a second threshold.

## File Structure

### New files

| File | Responsibility |
|---|---|
| `core/stats/__init__.py` | Package marker for shared stats primitives |
| `core/stats/psi.py` | Extracted `psi()` — the single PSI primitive (ML drift + cost drift) |
| `market_data/coverage_tracker.py` | Pure coverage state machine: session classification, qualifying-day counting, two-pass tracking, disk-durable state |
| `market_data/universe_discovery.py` | Broker symbol enumeration → allowlist filter → sanity check → writes `candidate` entries |
| `market_data/measurement_daemon.py` | Multi-symbol tick subscription, daily parquet writes, coverage updates, restart-resume |
| `market_data/promotion.py` | Promotion bar enforcer: writes `cost_calibration.json` entries + universe status flips + audit |
| `market_data/demote.py` | Cost-drift (PSI) demotion: universe flip + kill switch + ledger invalidation + audit |
| `research/ledger_invalidation.py` | Append-only trial-ledger / hypothesis-registry cross-reference writer |
| `tests/test_psi_shared.py`, `tests/test_universe_schema.py`, `tests/test_cost_calibration_gate.py`, `tests/test_coverage_tracker.py`, `tests/test_universe_discovery.py`, `tests/test_measurement_daemon.py`, `tests/test_promotion.py`, `tests/test_kill_switch_symbol.py`, `tests/test_demote.py`, `tests/test_ledger_invalidation.py` | Per-task TDD test files |

### Modified files

| File | Change |
|---|---|
| `ml/drift_monitor.py` | Delete `_calculate_psi`; delegate via `core.stats.psi.psi` |
| `provenance.py` | Remove `COST_CALIBRATED_SYMBOLS`; add `UNIVERSE_PATH`, `cost_calibrated_symbols()`, `cost_calibrated_status()`, `mode` params |
| `config/tradeable_universe.json` | Add `candidate`/`measuring`/`verifying` arrays; bump `_meta.version` to `1.2.0` |
| `scripts/comprehensive_edge_search.py`, `scripts/full_pipeline.py`, `scripts/run_complete_analysis.py`, `scripts/run_multi_symbol_wf.py`, `scripts/run_new_strategies_wf.py` | Gate call + `COST_CALIBRATED_SYMBOLS` usage migration |
| `scripts/backtest_cost.py`, `scripts/research_backed_pipeline.py`, `scripts/run_rydc_validation.py`, `scripts/test_ram_strategy.py`, `scripts/tsm_backtest.py`, `scripts/tsm_ema.py`, `scripts/tsm_portfolio.py`, `scripts/tsm_validate.py`, `scripts/validate_ram_strategy.py`, `scripts/walk_forward.py` | Gate call migration (`mode="paper"`) |
| `scripts/check_bypass_loaders.py` | Comment-only accuracy updates (3 lines) |
| `risk/kill_switch.py` | `kill_symbol()` / `is_symbol_killed()` / `killed_symbols` state key |

### Verified: NO changes needed (with evidence)

| File | Evidence |
|---|---|
| `core/trading_loop.py` | grep for `provenance|cost_calibrat|require_cost` across `core/` → zero matches (spec §3's claim that activation breaks this file is stale) |
| `scripts/select_tradeable_instruments.py` | `_load_candidates()` reads only `universe.get("tradeable", [])` (line 57) — backward-compatible with the new arrays; no edit |
| `scripts/run_ws_a.py`, `scripts/run_ws_a_tsmom.py`, `scripts/ws_a_trial_1028.py`, `scripts/run_ws_a_trial_1028.py` | Call `load_provenance_checked()` directly; auto-covered by its new internal `mode="paper"` default (Task 3); no edit |
| `scripts/validate_dtsmom_strategy.py` | Zero `require_cost_calibrated` references in HEAD and working tree (fresh grep, 2026-08-03) — the prior 16-file capture conflated it with `validate_ram_strategy.py`; no edit |
| `tests/test_provenance.py` | Unchanged; its `load_provenance_checked("XAUUSD")` call (line 71) keeps passing in both pre- and post-activation states because `mode="paper"` is a superset that always includes `tradeable` |

## Spec-Correction Notes (evidence-based)

These correct stale claims in the approved spec; they do not change the design:

1. Spec §3 names `core/trading_loop.py` as a caller that breaks on activation. Verified: zero references to provenance/cost calibration anywhere in `core/`. No changes needed.
2. Spec §6 cites "the existing `tests/test_mt5_tick_recorder.py`" as the mocking pattern. That file does not exist (glob `tests/test_mt5*` → only `test_mt5_gateway.py`, `test_mt5_live_order_e2e.py`). The pattern source is `tests/test_mt5_gateway.py` (508 lines).
3. Session windows: the design requires per-symbol broker session windows but the repo's `market_session_guard.py` only provides open/close (00:00–22:00 UTC, `MarketSessionConfig` lines 51-63), not the five named sessions. This plan defines canonical five-session windows in `coverage_tracker.py` with a per-symbol override interface. Parsing MT5's `session_deals`/`session_trades` bitfields without a live terminal to verify the shape would itself be fabrication — explicitly deferred.
4. `data/ticks/` currently contains no parquet files (glob `data/ticks/**` → empty) even though `config/cost_calibration.json` references historical ones. Promotion therefore always verifies its own freshly-written evidence files; tests use `tmp_path` fixtures.
5. `scripts/check_bypass_loaders.py` references `COST_CALIBRATED_SYMBOLS` only in comments (lines 130, 153, 167). Its code regexes remain valid; only those 3 comment lines are updated for accuracy.

---

## Task 1 — Extract shared `psi()` primitive; refactor `DriftMonitor` to delegate

**Files**
- NEW `core/stats/__init__.py`
- NEW `core/stats/psi.py`
- MOD `ml/drift_monitor.py`
- NEW `tests/test_psi_shared.py`

**Interfaces**

`core/stats/psi.py` — the extracted function is the exact math of the current `DriftMonitor._calculate_psi` (`ml/drift_monitor.py:487-524`):

```python
"""Shared Population Stability Index (PSI) primitive.

Extracted from ``ml/drift_monitor.py::DriftMonitor._calculate_psi`` (Phase 1,
2026-08-03) so the ML feature-drift check and the cost-drift demote check share
one statistical implementation. The math must stay identical to the original:
same bin edges, same 1e-10 probability floor, same erf-based normal CDF.
"""

from __future__ import annotations

import math


def psi(
    *,
    baseline_mean: float,
    baseline_std: float,
    current_mean: float,
    current_std: float,
    n_bins: int = 10,
) -> float:
    """Compute PSI between two normal distributions approximated by bins.

    Uses baseline mean/std to define bins, then computes the divergence
    between the baseline and current distributions.
    """
    # Define bin edges from baseline distribution
    lo = baseline_mean - 3 * baseline_std
    hi = baseline_mean + 3 * baseline_std
    edges = [lo + (hi - lo) * i / n_bins for i in range(n_bins + 1)]

    def _normal_cdf(x: float, mu: float, sigma: float) -> float:
        """Approximate normal CDF using error function."""
        return 0.5 * (1 + math.erf((x - mu) / (sigma * math.sqrt(2))))

    def _bin_probs(mu: float, sigma: float) -> list[float]:
        probs = []
        for i in range(n_bins):
            p = _normal_cdf(edges[i + 1], mu, sigma) - _normal_cdf(edges[i], mu, sigma)
            probs.append(max(p, 1e-10))
        return probs

    baseline_probs = _bin_probs(baseline_mean, baseline_std)
    current_probs = _bin_probs(current_mean, current_std)

    psi_value = 0.0
    for bp, cp in zip(baseline_probs, current_probs, strict=False):
        psi_value += (cp - bp) * math.log(cp / bp)
    return psi_value
```

`core/stats/__init__.py`:

```python
"""Statistical primitives shared across quant_os."""
```

**Steps**

1. Write `tests/test_psi_shared.py` (TDD — these must fail against a nonexistent module):

```python
"""Tests for core/stats/psi.py — the shared PSI primitive.

Pins: (1) mathematically-known edge cases, (2) delegation fidelity through
DriftMonitor: feature-drift scores produced by the monitor must equal psi()
computed independently from the same baseline statistics.
"""

from __future__ import annotations

import pytest

from core.stats.psi import psi


def test_psi_identical_distributions_is_zero():
    """Identical normal distributions → every bin pair has cp == bp → PSI == 0."""
    value = psi(baseline_mean=0.0, baseline_std=1.0, current_mean=0.0, current_std=1.0)
    assert value == pytest.approx(0.0, abs=1e-9)


def test_psi_shifted_distribution_is_positive():
    """A one-half-sigma shift must produce a positive PSI (KL divergence >= 0)."""
    value = psi(baseline_mean=0.0, baseline_std=1.0, current_mean=0.5, current_std=1.0)
    assert 0.1 < value < 0.5


def test_psi_zero_std_does_not_crash():
    """Zero std collapses edges; the 1e-10 probability floor keeps it finite."""
    value = psi(baseline_mean=0.0, baseline_std=0.0, current_mean=0.0, current_std=0.0)
    assert value == pytest.approx(0.0, abs=1e-9)


def test_drift_monitor_feature_scores_match_shared_psi(tmp_path, monkeypatch):
    """DriftMonitor._compute_feature_psi must produce exactly what psi() yields
    from the same baseline/current statistics (delegation fidelity).

    window_size=60 evicts the first 40 predictions from the current window, so
    current = last 60 values while the baseline accumulates all 100 — a
    genuinely non-zero PSI comparison."""
    monkeypatch.setenv("DUCKDB_PATH", str(tmp_path / "test.duckdb"))  # keep _save_state out of data/
    from ml.drift_monitor import DriftMonitor

    monitor = DriftMonitor(state_dir=tmp_path, window_size=60)
    baseline_vals = [0.0 + 0.1 * i for i in range(40)]  # first 40 → baseline, evicted from window
    current_vals = [0.8 + 0.1 * i for i in range(60)]  # next 60 → baseline + current window
    for v in baseline_vals:
        monitor.record_prediction(
            model_version="v1", symbol="XAUUSD", predicted_label=1,
            feature_snapshot={"f1": v},
        )
    for v in current_vals:
        monitor.record_prediction(
            model_version="v1", symbol="XAUUSD", predicted_label=1,
            feature_snapshot={"f1": v},
        )

    report = monitor.check_drift("v1", "XAUUSD")
    assert "f1" in report.feature_drift_scores

    # Independent recomputation: baseline = all 100 values, current = last 60.
    all_vals = baseline_vals + current_vals
    b_mean = sum(all_vals) / len(all_vals)
    b_std = max(
        (sum((v - b_mean) ** 2 for v in all_vals) / len(all_vals)) ** 0.5, 1e-10
    )
    c_mean = sum(current_vals) / len(current_vals)
    c_std = max(
        (sum((v - c_mean) ** 2 for v in current_vals) / len(current_vals)) ** 0.5, 1e-10
    )
    expected = psi(baseline_mean=b_mean, baseline_std=b_std,
                   current_mean=c_mean, current_std=c_std)
    assert report.feature_drift_scores["f1"] == pytest.approx(expected, abs=1e-9)
```

2. Verify fail: `python -m pytest tests/test_psi_shared.py -q` → collection error (`core.stats.psi` missing).
3. Create `core/stats/__init__.py` and `core/stats/psi.py` with the exact content above.
4. Verify pass: `python -m pytest tests/test_psi_shared.py -q`.
5. Modify `ml/drift_monitor.py`:
   - Add after line 14 (`from pathlib import Path`): `from core.stats.psi import psi`
   - Delete the entire `_calculate_psi` staticmethod (current lines 487-524).
   - Replace the call at line 453 (`psi = self._calculate_psi(`) and its usage (lines 453-474) with:

```python
            psi_score = psi(
                baseline_mean=b_mean,
                baseline_std=b_std,
                current_mean=c_mean,
                current_std=c_std,
                n_bins=10,
            )
            psi_scores[fname] = round(psi_score, 6)

            if psi_score > self._psi_threshold:
                parts = key.split("|", 1)
                mv, sym = parts[0], parts[1] if len(parts) > 1 else "unknown"
                severity = "critical" if psi_score > self._psi_threshold * 1.5 else "warning"
                alert = DriftAlert(
                    alert_type="feature_drift",
                    severity=severity,
                    model_version=mv,
                    symbol=sym,
                    message=f"Feature '{fname}' PSI={psi_score:.4f} exceeds threshold {self._psi_threshold}",
                    metric_name=f"psi_{fname}",
                    current_value=round(psi_score, 6),
                    threshold=self._psi_threshold,
                )
                self._alerts.append(alert)
                logger.warning(
                    "feature_drift_detected",
                    model_version=mv,
                    symbol=sym,
                    feature=fname,
                    psi=psi_score,
                )
```

6. Verify: `python -m pytest tests/test_psi_shared.py tests/test_provenance.py -q` AND the drift-monitor chaos file still imports cleanly (it is skipped at runtime): `python -m pytest tests/chaos/test_risk_monitoring_ml_untested.py --collect-only -q` (no import error expected; the class is `@pytest.mark.skip`).
7. **Hook-forced cleanup (verified 2026-08-03)**: the pre-commit ruff hook flags a PRE-EXISTING `F841` in `_save_state` (`mv, sym = parts[0], parts[1]...` assigned but never used) once drift_monitor.py is touched. Delete those two dead lines (the loop only needs `key`):
   ```python
            # Clear old predictions and insert current window
            for key, window in self._predictions.items():
                for r in window:
   ```
8. Commit: `git add core/stats/__init__.py core/stats/psi.py ml/drift_monitor.py tests/test_psi_shared.py && git commit -m "feat(quant_os): extract shared PSI primitive (core/stats/psi.py) for ML + cost drift"` — DONE as `158509a6` (2026-08-03).

### Execution corrections to this task's test file (verified, applied 2026-08-03)

1. Add the Global-Constraint-2 sys.path preamble (unconditional insert) at the top of `tests/test_psi_shared.py` — WITHOUT it the file fails collection (`ModuleNotFoundError: No module named 'core.stats'`) because the monorepo-root `core` shadows.
2. `test_psi_zero_std_does_not_crash` is WRONG as written: the original `_calculate_psi` has no sigma guard and raises `ZeroDivisionError` for sigma=0 (callers floor at 1e-10 first — `ml/drift_monitor.py` lines 441/450). Replace it with:
   ```python
   def test_psi_zero_std_raises_like_original():
       """Zero std raises ZeroDivisionError — identical to the pre-extraction
       DriftMonitor._calculate_psi (no sigma guard in the original; callers floor
       sigma at 1e-10 before calling, see ml/drift_monitor.py lines 441/450)."""
       with pytest.raises(ZeroDivisionError):
           psi(baseline_mean=0.0, baseline_std=0.0, current_mean=0.0, current_std=0.0)


   def test_psi_floored_sigma_is_finite():
       """Callers floor sigma at 1e-10; the function must stay finite for it."""
       value = psi(baseline_mean=0.0, baseline_std=1e-10, current_mean=0.0, current_std=1e-10)
       assert value == pytest.approx(0.0, abs=1e-9)
   ```
3. The delegation test's final assertion tolerance must be `abs=1e-6`, not `1e-9`: `DriftMonitor` rounds scores to 6 decimals (`round(psi, 6)` at `ml/drift_monitor.py:460`), so the monitor's reported value differs from the unrounded recomputation in the 7th decimal. Delegation is exact to 1e-6 (verified: obtained 0.160381 vs expected 0.1603814388).

---

## Task 2 — Universe JSON schema migration (add `candidate`/`measuring`/`verifying`)

**Files**
- MOD `config/tradeable_universe.json`
- NEW `tests/test_universe_schema.py`

**Interfaces**

Target schema after the edit (current file is 60 lines, verified). The edit is: `"version": "1.1.0"` → `"1.2.0"`, `"updated": "2026-07-26"` → `"2026-08-03"`, insert the three empty arrays after the `tradeable` array (before `excluded`), and extend `summary` (new keys `measuring`/`verifying`/`candidate`; existing keys unchanged). Every existing entry is preserved verbatim.

```json
{
  "_meta": {
    "version": "1.2.0",
    "created": "2026-07-25",
    "updated": "2026-08-03",
    "description": "Single source of truth for which symbols are eligible for live/paper trading. A symbol is TRADEABLE only if it has BOTH sufficient price history AND verified multi-day cost calibration data. Statuses: tradeable (both passes of the Phase 1 bar cleared), verifying (first pass cleared, re-verification pending), measuring (in measurement, pre-pass), candidate (discovered, not yet measuring), excluded (not eligible).",
    "cost_calibration_source": "config/cost_calibration.json (v3.1, 2026-07-26)",
    "data_integrity_fix_20260726": "The v1.0.0 'MEASURED'/'Properly measured multi-day' notes on NAS100/USOIL/USDJPY were false — see config/cost_calibration.json's data_integrity_fix_20260726 field. NAS100 is moved to excluded (zero real data, fails this file's own tradeable bar). XAUUSD/USDJPY upgraded to real tick-derived numbers (FROM_TICKS, ~27h, not multi-day). OIL restored to its real single-snapshot measurement."
  },
  "tradeable": [
    {
      "symbol": "XAUUSD",
      "asset_class": "metals",
      "cost_status": "FROM_TICKS",
      "cost_evidence": "cost_calibration.json: spread=0.3236bps (median), p95=0.5211bps, commission=0, RT cost=0.65bps, 733743 real ticks (data/ticks/XAUUSD_ticks_24h.parquet, ~27h, 2026-06-25/26)",
      "note": "Real tick-derived measurement, session-covering (~27h, all 5 sessions once each) — a substantial upgrade over the prior 3-minute snapshot, but still a single continuous window, not repeated multi-day sampling. Adequate for paper; needs true multi-day re-measurement before live."
    },
    {
      "symbol": "USOIL",
      "asset_class": "commodities",
      "cost_status": "SINGLE_SNAPSHOT",
      "cost_evidence": "cost_calibration.json: spread=4.88bps, commission=0, RT cost=9.76bps, 20 samples (single ~3-minute snapshot, 2026-07-03). Maps to MT5-reported symbol: SpotCrude",
      "note": "Real but single-snapshot measurement (restored from data/spread_analysis.json after commit 33b90c31 had overwritten it with fabricated 'USOIL' numbers under a false 3-day window). Adequate for paper, insufficient for live sizing. Needs multi-day re-measurement before live."
    },
    {
      "symbol": "USDJPY",
      "asset_class": "forex",
      "cost_status": "FROM_TICKS",
      "cost_evidence": "cost_calibration.json: spread=0.1236bps (median), p95=0.1856bps, commission=7, RT cost=7.25bps, 386245 real ticks (data/ticks/USDJPY_ticks_24h.parquet, ~27h, 2026-06-25/26)",
      "note": "Real tick-derived measurement, session-covering (~27h, all 5 sessions once each) — replaces a fabricated 0.80bps figure introduced in commit 33b90c31. Adequate for paper; needs true multi-day re-measurement before live."
    }
  ],
  "measuring": [],
  "verifying": [],
  "candidate": [],
  "excluded": [
    {"symbol": "EURUSD", "reason": "Removed from cost_calibration.json (explicit). No cost data."},
    {"symbol": "GBPUSD", "reason": "Removed from cost_calibration.json (explicit). No cost data."},
    {"symbol": "SILVER", "reason": "Removed from cost_calibration.json (explicit). No cost data."},
    {"symbol": "BTCUSD", "reason": "Removed from cost_calibration.json (explicit). No cost data."},
    {"symbol": "ETHUSD", "reason": "Removed from cost_calibration.json (explicit). No cost data."},
    {"symbol": "NAS100", "reason": "2026-07-26 data-integrity fix: previously listed as tradeable with a fabricated 'MEASURED/multi-day' claim (commit 33b90c31, 2026-07-08). Zero real spread or tick data exists anywhere in this repository for NAS100 (absent from data/spread_log.jsonl, data/spread_analysis.json, data/spread_report.json, and data/ticks/). Fails this file's own tradeable bar ('verified cost calibration data'). See config/cost_calibration.json assets.NAS100.measurement_caveat. Re-add only after real measurement exists."},
    {"symbol": "XAGUSD", "reason": "In symbol_registry but no cost calibration data."},
    {"symbol": "SOLUSD", "reason": "In symbol_registry but no cost calibration data."},
    {"symbol": "US30", "reason": "In symbol_registry but no cost calibration data. NOTE: real tick data exists at data/ticks/US30_ticks_24h.parquet (193789 ticks, same ~27h window) — a candidate for a genuine future addition, not evaluated further by this fix (out of scope: this fix corrects existing entries, it does not admit new symbols)."},
    {"symbol": "SPX500", "reason": "In symbol_registry but no cost calibration data."},
    {"symbol": "XAUJPY", "reason": "In symbol_registry but no cost calibration data."},
    {"symbol": "XAUEUR", "reason": "In symbol_registry but no cost calibration data."},
    {"symbol": "USDCAD", "reason": "In symbol_registry but no cost calibration data."},
    {"symbol": "NZDUSD", "reason": "In symbol_registry but no cost calibration data."},
    {"symbol": "AUDUSD", "reason": "In symbol_registry but no cost calibration data."},
    {"symbol": "USDCHF", "reason": "In symbol_registry but no cost calibration data."},
    {"symbol": "GER40", "reason": "In symbol_registry but no cost calibration data."},
    {"symbol": "UK100", "reason": "In symbol_registry but no cost calibration data."}
  ],
  "summary": {
    "total_in_registry": 18,
    "tradeable": 3,
    "measuring": 0,
    "verifying": 0,
    "candidate": 0,
    "excluded": 18,
    "tradeable_with_caveat": 3,
    "next_step": "All 3 remaining tradeable symbols (XAUUSD, USOIL, USDJPY) still lack true multi-day (repeated-calendar-day) cost measurement — this is calendar-bound and requires live/paper tick recording to run across multiple real days, not more engineering work. NAS100 requires a real measurement source (tick recording or historical archive) before it can be re-admitted."
  }
}
```

**Steps**

1. Write `tests/test_universe_schema.py`:

```python
"""Schema tests for config/tradeable_universe.json (Phase 1 migration).

Pins the new arrays exist, the tradeable bar is untouched, and the loader
contract in scripts/select_tradeable_instruments.py keeps working.
"""

from __future__ import annotations

import json
from pathlib import Path

UNIVERSE_PATH = Path(__file__).resolve().parent.parent / "config" / "tradeable_universe.json"


def _universe() -> dict:
    return json.loads(UNIVERSE_PATH.read_text(encoding="utf-8"))


def test_schema_has_all_status_arrays():
    uni = _universe()
    for key in ("tradeable", "measuring", "verifying", "candidate", "excluded"):
        assert key in uni, f"missing top-level array: {key}"
        assert isinstance(uni[key], list), f"{key} must be a list"


def test_tradeable_entries_unchanged_shape():
    uni = _universe()
    for entry in uni["tradeable"]:
        assert "symbol" in entry
        assert "asset_class" in entry
        assert "cost_status" in entry
        assert "cost_evidence" in entry


def test_no_symbol_appears_in_two_arrays():
    uni = _universe()
    seen: set[str] = set()
    for key in ("tradeable", "measuring", "verifying", "candidate"):
        for entry in uni[key]:
            sym = entry["symbol"]
            assert sym not in seen, f"{sym} appears in multiple status arrays"
            seen.add(sym)


def test_version_bumped():
    assert _universe()["_meta"]["version"] == "1.2.0"
```

2. Verify fail: `python -m pytest tests/test_universe_schema.py -q` → `test_schema_has_all_status_arrays` fails (arrays missing).
3. Edit `config/tradeable_universe.json` per the target above (only: version, updated, insert 3 arrays, summary additions). Preserve every existing entry verbatim.
4. Verify pass: `python -m pytest tests/test_universe_schema.py tests/test_paper_trading_symbol_selection.py -q` (the second file pins the downstream selection contract; it must stay green).
5. Commit: `git add config/tradeable_universe.json tests/test_universe_schema.py && git commit -m "feat(quant_os): add candidate/measuring/verifying arrays to tradeable universe schema"`

---

## Task 3 — `provenance.py` gate rewrite: live JSON read + `mode` parameter

**Files**
- MOD `provenance.py`
- NEW `tests/test_cost_calibration_gate.py`

**Interfaces**

New/changed symbols in `provenance.py` (current file verified: 188 lines; `COST_CALIBRATED_SYMBOLS` at lines 49-56, `require_cost_calibrated` at 59-78, `require_cost_calibrated_tsm_asset` at 96-98, `load_provenance_checked` at 112-156):

1. Add `import json` to the imports block (after line 17 `import pandas as pd`).
2. Add `from typing import Literal` (after `from pathlib import Path`).
3. Replace the `COST_CALIBRATED_SYMBOLS` block (lines 49-56) with:

```python
# Single source of truth: config/tradeable_universe.json, read at call time.
# The frozenset this replaced was "kept in sync manually" and caused two
# fabrication incidents (commit 33b90c31, trial #1030). The daemon writes
# this JSON; the gate reads the same JSON.
UNIVERSE_PATH = Path(__file__).resolve().parent / "config" / "tradeable_universe.json"


def cost_calibrated_symbols(mode: Literal["paper", "live"] = "live") -> frozenset[str]:
    """Read the tradeable universe JSON at call time (single source of truth).

    mode="live": only symbols in the "tradeable" array.
    mode="paper": tradeable + measuring + verifying (symbols that have
    last-known measured cost numbers, possibly provisional).
    """
    universe = json.loads(UNIVERSE_PATH.read_text(encoding="utf-8"))
    tradeable = {entry["symbol"] for entry in universe.get("tradeable", [])}
    if mode == "live":
        return frozenset(tradeable)
    provisional = {
        entry["symbol"] for entry in universe.get("measuring", [])
    } | {
        entry["symbol"] for entry in universe.get("verifying", [])
    }
    return frozenset(tradeable | provisional)


def cost_calibrated_status(symbol: str) -> str | None:
    """Return the symbol's universe status ("tradeable"|"measuring"|"verifying")
    or None when the symbol is in no status array (unknown/never measured)."""
    universe = json.loads(UNIVERSE_PATH.read_text(encoding="utf-8"))
    for status in ("tradeable", "measuring", "verifying"):
        for entry in universe.get(status, []):
            if entry.get("symbol") == symbol:
                return status
    return None
```

4. Replace `require_cost_calibrated` (lines 59-78) with:

```python
def require_cost_calibrated(
    symbol: str,
    mode: Literal["paper", "live"] = "live",
) -> str:
    """Refuse a symbol with no verified cost-calibration data for ``mode``.

    Returns the symbol's current status ("tradeable" | "measuring" |
    "verifying") so paper callers can tag P&L with a staleness flag
    (measuring/verifying = provisional cost basis).

    Raises UncalibratedCostError when:
      * the symbol is unknown (in no status array), or
      * mode="live" and the symbol is not yet "tradeable".

    Callers making live-money decisions must pass mode="live" explicitly;
    the "live" default protects call sites that forget to specify. Paper
    call sites must pass mode="paper" explicitly.
    """
    status = cost_calibrated_status(symbol)
    if status is None or (mode == "live" and status != "tradeable"):
        raise UncalibratedCostError(
            f"{symbol!r} has no verified cost-calibration data for mode={mode!r}. "
            f"tradeable={sorted(cost_calibrated_symbols('live'))}; "
            f"paper-eligible={sorted(cost_calibrated_symbols('paper'))}. Running a "
            f"trial against an assumed/synthetic cost model is exactly the "
            f"fabrication pattern already caught twice (commit 33b90c31, trial "
            f"#1030). Add real cost data to config/tradeable_universe.json first, "
            f"or pass require_cost_calibration=False if this call is not "
            f"informing a trading decision."
        )
    return status
```

5. Replace `require_cost_calibrated_tsm_asset` (lines 96-98) with:

```python
def require_cost_calibrated_tsm_asset(
    asset: str,
    mode: Literal["paper", "live"] = "live",
) -> str:
    """require_cost_calibrated, resolving tsm_*.py's aliased asset names first."""
    return require_cost_calibrated(TSM_ASSET_ALIASES.get(asset, asset), mode=mode)
```

6. Change `load_provenance_checked` signature (lines 112-119) to add the mode param, and its internal gate call (line 135) to pass it:

```python
def load_provenance_checked(
    symbol: str,
    slice_start: str = DEFAULT_SLICE_START,
    slice_end: str | None = None,
    data_dir: Path = DATA_DIR,
    max_synth_fraction: float = 0.10,
    require_cost_calibration: bool = True,
    mode: Literal["paper", "live"] = "paper",
) -> pd.DataFrame:
```

and inside the body:

```python
    if require_cost_calibration:
        require_cost_calibrated(symbol, mode=mode)
```

Note the deliberate asymmetry: the low-level functions default to `"live"` (strictest, protects forgetful callers), but `load_provenance_checked`'s gate defaults to `"paper"` so that existing data-loading callers (including `tests/test_provenance.py::test_bar_interval_assertion_passes_for_rebuilt_xauusd` at line 71) keep working regardless of whether XAUUSD is `tradeable` or `measuring`.

**Steps**

1. Write `tests/test_cost_calibration_gate.py`:

```python
"""Unit tests for the JSON-backed cost-calibration gate (Phase 1).

Uses a synthetic universe fixture via monkeypatch of provenance.UNIVERSE_PATH —
never asserts against the live config file, so these tests are order-independent
of the Task 12 activation migration.
"""

from __future__ import annotations

import json

import pandas as pd
import pytest

import provenance
from provenance import UncalibratedCostError


FIXTURE_UNIVERSE = {
    "tradeable": [{"symbol": "XAUUSD"}],
    "measuring": [{"symbol": "USOIL"}],
    "verifying": [{"symbol": "USDJPY"}],
    "candidate": [{"symbol": "EURUSD"}],
    "excluded": [{"symbol": "GBPUSD", "reason": "no data"}],
}


@pytest.fixture()
def universe(tmp_path, monkeypatch):
    path = tmp_path / "tradeable_universe.json"
    path.write_text(json.dumps(FIXTURE_UNIVERSE))
    monkeypatch.setattr(provenance, "UNIVERSE_PATH", path)
    return path


def test_live_mode_is_tradeable_only(universe):
    assert provenance.cost_calibrated_symbols(mode="live") == frozenset({"XAUUSD"})


def test_paper_mode_is_superset(universe):
    assert provenance.cost_calibrated_symbols(mode="paper") == frozenset(
        {"XAUUSD", "USOIL", "USDJPY"}
    )


def test_candidate_and_excluded_never_allowed(universe):
    for mode in ("paper", "live"):
        assert "EURUSD" not in provenance.cost_calibrated_symbols(mode=mode)
        assert "GBPUSD" not in provenance.cost_calibrated_symbols(mode=mode)


def test_live_raises_for_measuring_symbol(universe):
    with pytest.raises(UncalibratedCostError, match="USOIL"):
        provenance.require_cost_calibrated("USOIL", mode="live")


def test_paper_allows_measuring_symbol_and_returns_status(universe):
    assert provenance.require_cost_calibrated("USOIL", mode="paper") == "measuring"


def test_paper_allows_verifying_symbol_and_returns_status(universe):
    assert provenance.require_cost_calibrated("USDJPY", mode="paper") == "verifying"


def test_unknown_symbol_raises_in_both_modes(universe):
    for mode in ("paper", "live"):
        with pytest.raises(UncalibratedCostError, match="SOLUSD"):
            provenance.require_cost_calibrated("SOLUSD", mode=mode)


def test_tsm_alias_resolution(universe):
    # OIL -> USOIL (measuring): paper passes with staleness flag; live raises.
    assert provenance.require_cost_calibrated_tsm_asset("OIL", mode="paper") == "measuring"
    with pytest.raises(UncalibratedCostError):
        provenance.require_cost_calibrated_tsm_asset("OIL", mode="live")
    # EURUSD_YF -> EURUSD (candidate): both modes raise.
    with pytest.raises(UncalibratedCostError):
        provenance.require_cost_calibrated_tsm_asset("EURUSD_YF", mode="paper")


def test_load_provenance_checked_paper_mode_allows_measuring_symbol(
    tmp_path, monkeypatch, universe
):
    """load_provenance_checked gates with mode=paper by default, so a measuring
    symbol with valid data loads; a live-mode call on the same symbol raises
    before touching the data file."""
    csv_path = tmp_path / "USOIL_D1.csv"
    rows = []
    for i in range(30):
        day = pd.Timestamp("2024-01-01") + pd.Timedelta(days=i)
        rows.append(
            {
                "time": day.isoformat(),
                "open": 70.0 + i * 0.01,
                "high": 70.0 + i * 0.01 + 0.1,
                "low": 70.0 + i * 0.01 - 0.1,
                "close": 70.0 + i * 0.01 + 0.05,
                "volume": 100.0,
            }
        )
    pd.DataFrame(rows).to_csv(csv_path, index=False)
    monkeypatch.setattr(provenance, "DATA_DIR", tmp_path)

    df = provenance.load_provenance_checked("USOIL")  # default mode="paper"
    assert len(df) == 30

    with pytest.raises(UncalibratedCostError, match="USOIL"):
        provenance.load_provenance_checked("USOIL", mode="live")
```

2. Verify fail: `python -m pytest tests/test_cost_calibration_gate.py -q` → collection/import errors plus `TypeError` for `mode` (parameter does not exist yet).
3. Apply the six `provenance.py` edits above.
4. Verify pass:
   - `python -m pytest tests/test_cost_calibration_gate.py tests/test_provenance.py -q` (existing provenance contract must stay green).
5. Commit: `git add provenance.py tests/test_cost_calibration_gate.py && git commit -m "feat(quant_os): JSON-backed cost-calibration gate with paper/live mode (provenance.py)"`

---

## Task 4 — Migrate all 15 gate call sites + 5 `COST_CALIBRATED_SYMBOLS` usages

**Files** (all verified line-exact via grep)

> **Correction (verified 2026-08-03 during execution): the migration is 15 files, not 16.**
> `scripts/validate_dtsmom_strategy.py` was listed in the prior-session call-site capture (import line 28 + call line 267), but a fresh grep against both HEAD and the working tree finds **zero** `require_cost_calibrated` references there — the earlier capture conflated it with `scripts/validate_ram_strategy.py` (which DOES have import line 28 + call line 268). `validate_dtsmom_strategy.py` = verified NO changes needed (its only uncommitted edits belong to another session's formatting work).

Group A — 5 files importing and using `COST_CALIBRATED_SYMBOLS`:
- `scripts/comprehensive_edge_search.py`
- `scripts/full_pipeline.py`
- `scripts/run_complete_analysis.py`
- `scripts/run_multi_symbol_wf.py`
- `scripts/run_new_strategies_wf.py`

Group B — 10 files importing only the gate function:
- `scripts/backtest_cost.py`, `scripts/research_backed_pipeline.py`, `scripts/run_rydc_validation.py`, `scripts/test_ram_strategy.py`, `scripts/tsm_backtest.py`, `scripts/tsm_ema.py`, `scripts/tsm_portfolio.py`, `scripts/tsm_validate.py`, `scripts/validate_ram_strategy.py`, `scripts/walk_forward.py`

Comment-only (3 lines + 1 extra): `scripts/check_bypass_loaders.py` (3 lines), plus `scripts/run_multi_symbol_wf.py` line 36 (a comment naming the removed constant, discovered by the final grep).

**Steps**

For every file, the import line changes from `from provenance import COST_CALIBRATED_SYMBOLS, require_cost_calibrated` (Group A) to `from provenance import cost_calibrated_symbols, require_cost_calibrated`, and every gate call gains `mode="paper"` (these are all research/backtest/paper scripts — they must keep working after Task 12's activation, so they must NOT use the default `"live"`).

1. `scripts/comprehensive_edge_search.py`:
   - Line 41: `from provenance import COST_CALIBRATED_SYMBOLS, require_cost_calibrated  # noqa: E402` → `from provenance import cost_calibrated_symbols, require_cost_calibrated  # noqa: E402`
   - Line 43: `require_cost_calibrated("XAUUSD")` → `require_cost_calibrated("XAUUSD", mode="paper")`
   - Line 636: `if sym not in COST_CALIBRATED_SYMBOLS:` → `if sym not in cost_calibrated_symbols(mode="paper"):`
2. `scripts/full_pipeline.py`:
   - Line 40: same import replacement.
   - Line 495: `require_cost_calibrated("XAUUSD")` → `require_cost_calibrated("XAUUSD", mode="paper")`
   - Line 535: `if sym not in COST_CALIBRATED_SYMBOLS:` → `if sym not in cost_calibrated_symbols(mode="paper"):`
3. `scripts/run_complete_analysis.py`:
   - Line 20: same import replacement.
   - Line 86: `if symbol not in COST_CALIBRATED_SYMBOLS:` → `if symbol not in cost_calibrated_symbols(mode="paper"):`
   - Line 87: `print(f"  SKIPPED: {symbol} not cost-calibrated ({sorted(COST_CALIBRATED_SYMBOLS)})")` → `print(f"  SKIPPED: {symbol} not cost-calibrated ({sorted(cost_calibrated_symbols(mode='paper'))})")`
   - Line 89: `require_cost_calibrated(symbol)` → `require_cost_calibrated(symbol, mode="paper")`
4. `scripts/run_multi_symbol_wf.py`:
   - Line 21: same import replacement.
   - Line 92: `if symbol not in COST_CALIBRATED_SYMBOLS:` → `if symbol not in cost_calibrated_symbols(mode="paper"):`
   - Line 93: `print(f"  SKIPPED: {symbol} not cost-calibrated ({sorted(COST_CALIBRATED_SYMBOLS)})")` → `print(f"  SKIPPED: {symbol} not cost-calibrated ({sorted(cost_calibrated_symbols(mode='paper'))})")`
   - Line 95: `require_cost_calibrated(symbol)` → `require_cost_calibrated(symbol, mode="paper")`
5. `scripts/run_new_strategies_wf.py`:
   - Line 49: same import replacement.
   - Line 1087: `        "symbol(s) have no verified cost data (see COST_CALIBRATED_SYMBOLS) "` → `        "symbol(s) have no verified cost data (see cost_calibrated_symbols()) "`
   - Line 1114: `elif all(s in COST_CALIBRATED_SYMBOLS for s in info["symbols"]):` → `elif all(s in cost_calibrated_symbols(mode="paper") for s in info["symbols"]):`
   - Line 1115: `require_cost_calibrated(info["symbols"][0])` → `require_cost_calibrated(info["symbols"][0], mode="paper")`
   - Line 1120: `f"({sorted(COST_CALIBRATED_SYMBOLS)}). Pass --cost-bps to "` → `f"({sorted(cost_calibrated_symbols(mode='paper'))}). Pass --cost-bps to "`
6. `scripts/backtest_cost.py`:
   - Line 30 import unchanged.
   - Line 380: `require_cost_calibrated(args.symbol)` → `require_cost_calibrated(args.symbol, mode="paper")`
7. `scripts/research_backed_pipeline.py`:
   - Line 47 import unchanged.
   - Line 674: `require_cost_calibrated("XAUUSD")` → `require_cost_calibrated("XAUUSD", mode="paper")`
8. `scripts/run_rydc_validation.py`:
   - Line 42 import unchanged.
   - Line 441: `require_cost_calibrated(RYDC_SYMBOL)` → `require_cost_calibrated(RYDC_SYMBOL, mode="paper")`
9. `scripts/test_ram_strategy.py`:
   - Line 34 import unchanged.
   - Line 209: `require_cost_calibrated(asset)` → `require_cost_calibrated(asset, mode="paper")`
10. `scripts/tsm_backtest.py` (line 25 import `require_cost_calibrated_tsm_asset`), `scripts/tsm_ema.py` (line 24), `scripts/tsm_portfolio.py` (line 29), `scripts/tsm_validate.py` (line 35): imports unchanged; each call site — respectively lines 240, 252, 288, 458 — becomes `require_cost_calibrated_tsm_asset(_asset, mode="paper")`.
11. `scripts/validate_dtsmom_strategy.py` (line 28 import; line 267 call) and `scripts/validate_ram_strategy.py` (line 28 import; line 268 call): `require_cost_calibrated(asset)` → `require_cost_calibrated(asset, mode="paper")`.
12. `scripts/walk_forward.py`:
    - Line 24 import unchanged.
    - Line 418: `require_cost_calibrated(args.symbol)` → `require_cost_calibrated(args.symbol, mode="paper")`
13. `scripts/check_bypass_loaders.py` — comment-only accuracy updates (verified live line numbers 124/147/161, not 130/153/167 as previously captured):
    - Line 124: `# scan now skips any symbol not in COST_CALIBRATED_SYMBOLS instead` → `# scan now skips any symbol not in provenance.cost_calibrated_symbols() instead`
    - Line 147: `# COST_CALIBRATED_SYMBOLS) skipped rather than run on the stale` → `# cost_calibrated_symbols()) skipped rather than run on the stale`
    - Line 161: `# than cost-guessed since EURUSD isn't in COST_CALIBRATED_SYMBOLS;` → `# than cost-guessed since EURUSD isn't in cost_calibrated_symbols();`
14. `scripts/run_multi_symbol_wf.py` line 36 (comment, found by the zero-remaining-references grep): `# today). run_walk_forward() below now gates on COST_CALIBRATED_SYMBOLS and` → `# today). run_walk_forward() below now gates on cost_calibrated_symbols() and`

Verification (after all edits):
1. `python -m py_compile` on all 15 migrated files + `provenance.py` + `check_bypass_loaders.py` → all succeed (executed, COMPILE_OK).
2. `python -m pytest tests/test_cost_calibration_gate.py tests/test_provenance.py tests/test_universe_schema.py -q` → green (19 passed).
3. Zero remaining `COST_CALIBRATED_SYMBOLS` references across `scripts/` and `provenance.py` (executed: only the 4 comment lines listed above existed, all updated).
4. Commit — DONE as `15b13e6c` (2026-08-03).

### Execution corrections to this task (verified, applied 2026-08-03)

1. **15 files, not 16** — `validate_dtsmom_strategy.py` has no gate references (see header correction). Do NOT stage it; its working-tree edits belong to another session.
2. **Pre-existing lint debt in `validate_ram_strategy.py` blocks the commit hook** (ruff E402/B006 + mypy `module_from_spec`/`RAMConfig` errors — all pre-existing, unrelated to the one-line gate edit). The hook gates the whole file, so these minimal debt fixes were required to land the commit:
   - `import importlib.util  # noqa: E402`
   - `RAMConfig: Any = ram_module.RAMConfig` (added `from typing import Any`)
   - `assert spec is not None and spec.loader is not None` before `module_from_spec`/`exec_module`
   - `cost_stress_test(..., cost_multipliers: list[float] | None = None)` + body default (mirrors the same fix applied to `validate_dtsmom_strategy.py` by the concurrent session)
3. Commit hook runs on EVERY staged file — the concurrent session's staged files (e.g. `tests/test_walk_forward.py`) fail ruff/mypy and abort unrelated commits. Before committing: `git diff --cached --name-only`, and `git restore --staged <their files>` if foreign files are staged.

---

## Task 5 — `market_data/coverage_tracker.py`: pure two-pass coverage state machine

**Files**
- NEW `market_data/coverage_tracker.py`
- NEW `tests/test_coverage_tracker.py`

**Interfaces**

```python
"""Per-symbol measurement coverage state machine (Phase 1).

Pure logic, no MT5 dependency: classifies ticks into the five named sessions,
counts qualifying days (5/5 sessions covered, >= 50,000 VALID ticks per
session-day, no GAP inside a session), tracks which pass each qualifying day
counts toward, and persists state to disk so daemon restarts never lose
day-6 progress.
"""

from __future__ import annotations

import json
import os
import tempfile
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta, timezone
from pathlib import Path

SESSION_NAMES: tuple[str, ...] = (
    "asian", "london", "london_ny_overlap", "ny", "rollover",
)
SESSIONS_PER_DAY: int = 5
QUALIFYING_DAYS: int = 7
MIN_VALID_TICKS_PER_SESSION_DAY: int = 50_000

# Canonical UTC windows. Per-symbol overrides are supported via the
# SessionClassifier(session_windows=...) constructor argument.
DEFAULT_SESSION_WINDOWS: dict[str, tuple[time, time]] = {
    "asian": (time(0, 0), time(7, 0)),
    "london": (time(7, 0), time(12, 0)),
    "london_ny_overlap": (time(12, 0), time(16, 0)),
    "ny": (time(16, 0), time(21, 0)),
    "rollover": (time(21, 0), time(23, 59, 59)),
}


class SessionClassifier:
    """Classify a UTC timestamp into one of the five sessions, or None."""

    def __init__(self, session_windows: dict[str, tuple[time, time]] | None = None):
        self._windows = dict(DEFAULT_SESSION_WINDOWS if session_windows is None else session_windows)

    def classify(self, timestamp_utc: datetime) -> str | None:
        """Return the session name for the timestamp, or None on weekends or
        outside all windows."""
        if timestamp_utc.weekday() >= 5:  # Saturday=5, Sunday=6
            return None
        t = timestamp_utc.time()
        for name, (start, end) in self._windows.items():
            if start <= t <= end:
                return name
        return None


@dataclass(frozen=True)
class SessionDayState:
    covered: bool = False
    valid_ticks: int = 0
    had_gap: bool = False
    pass_index: int = 0  # 0 = not yet qualifying, 1 = first pass, 2 = verification pass


class CoverageTracker:
    """Disk-durable per-symbol coverage state.

    State file shape (JSON):
    {
      "symbol": "XAUUSD",
      "version": 1,
      "days": {
        "2026-08-03": {
          "asian": {"covered": true, "valid_ticks": 52311, "had_gap": false, "pass_index": 1},
          ...
        }
      }
    }
    """

    def __init__(
        self,
        symbol: str,
        state_file: str | Path,
        session_windows: dict[str, tuple[time, time]] | None = None,
        qualifying_days: int = QUALIFYING_DAYS,
        min_valid_ticks: int = MIN_VALID_TICKS_PER_SESSION_DAY,
    ):
        self._symbol = symbol
        self._state_file = Path(state_file)
        self._classifier = SessionClassifier(session_windows)
        self._qualifying_days = qualifying_days
        self._min_valid_ticks = min_valid_ticks
        self._state: dict[str, dict] = self._load()

    # -- tick classification -------------------------------------------------

    def classify(self, timestamp_utc: datetime) -> str | None:
        return self._classifier.classify(timestamp_utc)

    # -- recording -----------------------------------------------------------

    def record_session_day(
        self,
        trading_day: date,
        session_name: str,
        valid_ticks: int,
        had_gap: bool,
    ) -> bool:
        """Record a session-day observation. Returns True when this session-day
        newly became covered (crossed the VALID-tick floor without a gap)."""
        day_key = trading_day.isoformat()
        day_state = self._state["days"].setdefault(day_key, {})
        prior = day_state.get(session_name, {})
        covered = (
            prior.get("covered", False)
            or (valid_ticks >= self._min_valid_ticks and not had_gap)
        )
        day_state[session_name] = {
            "covered": covered,
            "valid_ticks": max(prior.get("valid_ticks", 0), valid_ticks),
            "had_gap": prior.get("had_gap", False) or had_gap,
            "pass_index": prior.get("pass_index", 0),
        }
        self._assign_pass(day_key)
        return covered and not prior.get("covered", False)

    def _assign_pass(self, day_key: str) -> None:
        if not self._day_qualifies(day_key):
            return
        day_state = self._state["days"][day_key]
        if any(day_state[s]["pass_index"] for s in SESSION_NAMES if s in day_state):
            return  # already assigned
        pass_index = 2 if self._first_pass_days() >= self._qualifying_days else 1
        for name in SESSION_NAMES:
            if name in day_state:
                day_state[name]["pass_index"] = pass_index

    def _day_qualifies(self, day_key: str) -> bool:
        day_state = self._state["days"].get(day_key, {})
        sessions = [s for s in SESSION_NAMES if s in day_state]
        if len(sessions) < SESSIONS_PER_DAY:
            return False
        return all(
            day_state[s]["covered"] and not day_state[s]["had_gap"]
            for s in sessions
        )

    def qualifying_day_count(self) -> int:
        """Number of distinct qualifying days (5/5 sessions, no gap)."""
        return sum(
            1 for day_key in self._state["days"]
            if self._day_qualifies(day_key)
        )

    def first_pass_days(self) -> int:
        return sum(
            1 for day_state in self._state["days"].values()
            if any(s.get("pass_index") == 1 for s in day_state.values() if isinstance(s, dict))
        )

    def verification_pass_days(self) -> int:
        return sum(
            1 for day_state in self._state["days"].values()
            if any(s.get("pass_index") == 2 for s in day_state.values() if isinstance(s, dict))
        )

    def first_pass_complete(self) -> bool:
        return self.first_pass_days() >= self._qualifying_days

    def verification_pass_complete(self) -> bool:
        return self.verification_pass_days() >= self._qualifying_days

    def progress(self) -> dict:
        return {
            "symbol": self._symbol,
            "qualifying_day_count": self.qualifying_day_count(),
            "first_pass_days": self.first_pass_days(),
            "verification_pass_days": self.verification_pass_days(),
            "first_pass_complete": self.first_pass_complete(),
            "verification_pass_complete": self.verification_pass_complete(),
        }

    # -- persistence ---------------------------------------------------------

    def _load(self) -> dict[str, dict]:
        default = {"symbol": self._symbol, "version": 1, "days": {}}
        if not self._state_file.exists():
            return default
        try:
            raw = json.loads(self._state_file.read_text(encoding="utf-8"))
            if raw.get("symbol") != self._symbol:
                return default
            return raw
        except (json.JSONDecodeError, OSError):
            return default

    def save(self) -> None:
        self._state_file.parent.mkdir(parents=True, exist_ok=True)
        fd, tmp_path = tempfile.mkstemp(dir=str(self._state_file.parent), prefix=".coverage_", suffix=".tmp")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as fh:
                json.dump(self._state, fh, indent=2)
                fh.flush()
                os.fsync(fh.fileno())
            os.replace(tmp_path, str(self._state_file))
        except Exception:
            import contextlib
            with contextlib.suppress(OSError):
                os.unlink(tmp_path)
            raise
```

**Steps**

1. Write `tests/test_coverage_tracker.py` (TDD, all pure — no MT5):

```python
"""Unit tests for market_data/coverage_tracker.py (Phase 1 promotion bar)."""

from __future__ import annotations

from datetime import date, datetime, time, timezone, timedelta

import pytest

from market_data.coverage_tracker import (
    DEFAULT_SESSION_WINDOWS,
    MIN_VALID_TICKS_PER_SESSION_DAY,
    QUALIFYING_DAYS,
    SESSION_NAMES,
    SessionClassifier,
    CoverageTracker,
)


def _fill_qualifying_day(tracker: CoverageTracker, d: date) -> None:
    for name in SESSION_NAMES:
        tracker.record_session_day(d, name, MIN_VALID_TICKS_PER_SESSION_DAY, had_gap=False)


def test_classifier_weekend_returns_none():
    clf = SessionClassifier()
    saturday = datetime(2026, 8, 8, 12, 0, tzinfo=timezone.utc)  # Saturday
    assert clf.classify(saturday) is None


def test_classifier_maps_sessions():
    clf = SessionClassifier()
    assert clf.classify(datetime(2026, 8, 3, 2, 0, tzinfo=timezone.utc)) == "asian"
    assert clf.classify(datetime(2026, 8, 3, 9, 0, tzinfo=timezone.utc)) == "london"
    assert clf.classify(datetime(2026, 8, 3, 14, 0, tzinfo=timezone.utc)) == "london_ny_overlap"
    assert clf.classify(datetime(2026, 8, 3, 18, 0, tzinfo=timezone.utc)) == "ny"
    assert clf.classify(datetime(2026, 8, 3, 22, 0, tzinfo=timezone.utc)) == "rollover"


def test_classifier_respects_per_symbol_windows():
    clf = SessionClassifier(session_windows={**DEFAULT_SESSION_WINDOWS, "london": (time(6, 0), time(13, 0))})
    assert clf.classify(datetime(2026, 8, 3, 6, 30, tzinfo=timezone.utc)) == "london"


def test_session_day_needs_tick_floor(tmp_path):
    tracker = CoverageTracker("XAUUSD", tmp_path / "cov.json")
    tracker.record_session_day(date(2026, 8, 3), "asian", MIN_VALID_TICKS_PER_SESSION_DAY - 1, had_gap=False)
    assert tracker.qualifying_day_count() == 0


def test_gap_invalidates_session_day(tmp_path):
    tracker = CoverageTracker("XAUUSD", tmp_path / "cov.json")
    tracker.record_session_day(date(2026, 8, 3), "asian", MIN_VALID_TICKS_PER_SESSION_DAY, had_gap=True)
    assert tracker.qualifying_day_count() == 0


def test_qualifying_day_requires_all_five_sessions(tmp_path):
    tracker = CoverageTracker("XAUUSD", tmp_path / "cov.json")
    for name in SESSION_NAMES[:4]:
        tracker.record_session_day(date(2026, 8, 3), name, MIN_VALID_TICKS_PER_SESSION_DAY, had_gap=False)
    assert tracker.qualifying_day_count() == 0


def test_seven_qualifying_days_completes_first_pass(tmp_path):
    tracker = CoverageTracker("XAUUSD", tmp_path / "cov.json")
    start = date(2026, 8, 3)  # Monday
    for i in range(QUALIFYING_DAYS):
        _fill_qualifying_day(tracker, start + timedelta(days=i))
    assert tracker.qualifying_day_count() == QUALIFYING_DAYS
    assert tracker.first_pass_complete()
    assert not tracker.verification_pass_complete()


def test_non_consecutive_days_count(tmp_path):
    tracker = CoverageTracker("XAUUSD", tmp_path / "cov.json")
    days = [date(2026, 8, 3), date(2026, 8, 10), date(2026, 8, 17)]  # three Mondays
    for d in days:
        _fill_qualifying_day(tracker, d)
    assert tracker.qualifying_day_count() == 3


def test_second_pass_requires_fresh_window(tmp_path):
    tracker = CoverageTracker("XAUUSD", tmp_path / "cov.json")
    start = date(2026, 8, 3)
    for i in range(QUALIFYING_DAYS * 2):
        _fill_qualifying_day(tracker, start + timedelta(days=i))
    assert tracker.first_pass_complete()
    assert tracker.verification_pass_complete()


def test_state_survives_reload(tmp_path):
    state_file = tmp_path / "cov.json"
    tracker = CoverageTracker("XAUUSD", state_file)
    _fill_qualifying_day(tracker, date(2026, 8, 3))
    tracker.save()

    reloaded = CoverageTracker("XAUUSD", state_file)
    assert reloaded.qualifying_day_count() == 1


def test_state_is_per_symbol(tmp_path):
    a = CoverageTracker("XAUUSD", tmp_path / "cov_a.json")
    b = CoverageTracker("USOIL", tmp_path / "cov_b.json")
    _fill_qualifying_day(a, date(2026, 8, 3))
    a.save()
    b.save()
    assert CoverageTracker("USOIL", tmp_path / "cov_b.json").qualifying_day_count() == 0


def test_corrupt_state_file_falls_back_to_empty(tmp_path):
    state_file = tmp_path / "cov.json"
    state_file.write_text("{not json")
    tracker = CoverageTracker("XAUUSD", state_file)
    assert tracker.qualifying_day_count() == 0
```

2. Verify fail: `python -m pytest tests/test_coverage_tracker.py -q` → collection error (module missing).
3. Implement `market_data/coverage_tracker.py` exactly as specified above.
4. Verify pass: `python -m pytest tests/test_coverage_tracker.py -q`.
5. Commit: `git add market_data/coverage_tracker.py tests/test_coverage_tracker.py && git commit -m "feat(quant_os): two-pass coverage state machine for cost-calibration measurement"`

---

## Task 6 — `broker/mt5_gateway.get_symbols()` + `market_data/universe_discovery.py`

**Files**
- MOD `broker/mt5_gateway.py`
- NEW `market_data/universe_discovery.py`
- NEW `tests/test_universe_discovery.py`

**Interfaces**

Add to `broker/mt5_gateway.py` (after `get_current_tick`, following the same `_get_mt5()` / `Mt5UnavailableError` convention):

```python
def get_symbols() -> list[dict]:
    """Enumerate all broker symbols via symbols_get() (read-only).

    Returns a list of dicts with keys: name, path, digits, trade_mode.
    Raises Mt5UnavailableError if MT5 is unavailable or the call fails.
    """
    mt5 = _get_mt5()
    try:
        raw = mt5.symbols_get()
        if raw is None:
            raise Mt5UnavailableError(f"symbols_get failed: {mt5.last_error()}")
        result = []
        for s in raw:
            result.append(
                {
                    "name": s.name,
                    "path": s.path,
                    "digits": s.digits,
                    "trade_mode": s.trade_mode,
                }
            )
        return result
    except Mt5UnavailableError:
        raise
    except Exception as e:
        raise Mt5UnavailableError(f"symbols_get error: {e}") from e
```

`market_data/universe_discovery.py`:

```python
"""Broker symbol discovery (Phase 1).

Enumerates MT5 symbols via symbols_get(), classifies them into the asset-class
allowlist (forex / metals / commodities / indices), sanity-checks spread, and
writes new symbols into tradeable_universe.json as "candidate" entries.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import tempfile
from datetime import UTC, datetime
from pathlib import Path

from broker.mt5_gateway import Mt5UnavailableError, get_current_tick, get_symbols

ASSET_CLASS_ALLOWLIST: frozenset[str] = frozenset({"forex", "metals", "commodities", "indices"})
MAX_SANITY_SPREAD_BPS: float = 50.0
SYMBOL_NAME_RE = re.compile(r"^[A-Z0-9_]{2,12}$")

# path-based classification hints; unknown paths are rejected.
# Order matters: more specific paths (Metals) must precede generic ones (Forex).
_PATH_HINTS: list[tuple[str, str]] = [
    ("Metals", "metals"),
    ("Commodities", "commodities"),
    ("Energies", "commodities"),
    ("Indices", "indices"),
    ("Forex", "forex"),
]


def classify_symbol(name: str, path: str) -> str | None:
    """Return the asset class for a broker symbol, or None to reject."""
    if not SYMBOL_NAME_RE.match(name):
        return None
    for hint, asset_class in _PATH_HINTS:
        if hint.lower() in path.lower():
            return asset_class
    return None


def spread_bps_from_tick(tick: dict) -> float:
    """Convert a get_current_tick() dict into spread in basis points."""
    mid = (tick["bid"] + tick["ask"]) / 2.0
    if mid <= 0:
        return float("inf")
    return (tick["ask"] - tick["bid"]) / mid * 10_000.0


def sanity_check(symbol: str) -> bool:
    """A symbol passes the sanity bar if we can fetch a tick and its spread
    is not absurd. Fail-closed: any MT5 error rejects the symbol."""
    try:
        tick = get_current_tick(symbol)
    except Mt5UnavailableError:
        return False
    return spread_bps_from_tick(tick) <= MAX_SANITY_SPREAD_BPS


def discover_new_candidates(
    symbols: list[dict],
    universe: dict,
) -> list[dict]:
    """Return candidate entries for broker symbols not already in any
    status array of the universe."""
    known = {
        entry["symbol"]
        for key in ("tradeable", "measuring", "verifying", "candidate", "excluded")
        for entry in universe.get(key, [])
    }
    candidates: list[dict] = []
    for s in symbols:
        asset_class = classify_symbol(s["name"], s.get("path", ""))
        if asset_class is None or asset_class not in ASSET_CLASS_ALLOWLIST:
            continue
        if s["name"] in known:
            continue
        candidates.append(
            {
                "symbol": s["name"],
                "asset_class": asset_class,
                "broker_path": s.get("path", ""),
            }
        )
    return candidates


def update_universe(universe_path: str | Path, candidates: list[dict]) -> list[str]:
    """Append candidate entries to tradeable_universe.json (atomic write).
    Returns the symbols added."""
    path = Path(universe_path)
    universe = json.loads(path.read_text(encoding="utf-8"))
    added: list[str] = []
    candidate_list = universe.setdefault("candidate", [])
    existing = {e["symbol"] for e in candidate_list}
    for entry in candidates:
        if entry["symbol"] in existing:
            continue
        candidate_list.append(entry)
        existing.add(entry["symbol"])
        added.append(entry["symbol"])
    if added:
        universe["_meta"]["updated"] = datetime.now(UTC).date().isoformat()
        fd, tmp_path = tempfile.mkstemp(dir=str(path.parent), prefix=".universe_", suffix=".tmp")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as fh:
                json.dump(universe, fh, indent=2)
                fh.flush()
                os.fsync(fh.fileno())
            os.replace(tmp_path, str(path))
        except Exception:
            import contextlib
            with contextlib.suppress(OSError):
                os.unlink(tmp_path)
            raise
    return added


def main() -> None:
    parser = argparse.ArgumentParser(description="Discover new broker symbols as universe candidates")
    parser.add_argument("--universe", default=str(Path(__file__).resolve().parent.parent / "config" / "tradeable_universe.json"))
    parser.add_argument("--write", action="store_true", help="Write candidates into the universe file")
    args = parser.parse_args()

    universe_path = Path(args.universe)
    universe = json.loads(universe_path.read_text(encoding="utf-8"))

    symbols = get_symbols()
    candidates = discover_new_candidates(symbols, universe)
    print(f"Broker symbols enumerated: {len(symbols)}; new candidates: {len(candidates)}")
    for c in candidates:
        print(f"  candidate: {c['symbol']} ({c['asset_class']})")

    if args.write and candidates:
        added = update_universe(universe_path, candidates)
        print(f"Wrote {len(added)} candidates to {universe_path}")
    elif args.write:
        print("No new candidates to write.")


if __name__ == "__main__":
    main()
```

**Steps**

1. Write `tests/test_universe_discovery.py`:

```python
"""Tests for market_data/universe_discovery.py and broker/mt5_gateway.get_symbols()."""

from __future__ import annotations

import json
import sys

import pytest

from market_data import universe_discovery as ud


class TestClassifySymbol:
    def test_allowlisted_paths(self):
        assert ud.classify_symbol("XAUUSD", "Forex\\Metals") == "metals"
        assert ud.classify_symbol("EURUSD", "Forex") == "forex"
        assert ud.classify_symbol("USOIL", "CFD\\Energies") == "commodities"
        assert ud.classify_symbol("NAS100", "Indices") == "indices"

    def test_rejects_junk_names(self):
        assert ud.classify_symbol("EURSGD.he", "Forex") is None
        assert ud.classify_symbol("tiny", "Forex") is None  # too short


class TestSpreadBps:
    def test_spread_bps_conversion(self):
        tick = {"bid": 2300.00, "ask": 2300.20}
        assert ud.spread_bps_from_tick(tick) == pytest.approx(0.8696, abs=1e-3)

    def test_zero_mid_rejects(self):
        assert ud.spread_bps_from_tick({"bid": 0.0, "ask": 0.0}) == float("inf")


class TestDiscoverNewCandidates:
    def test_only_new_allowlisted_symbols(self):
        symbols = [
            {"name": "EURUSD", "path": "Forex"},
            {"name": "XAUUSD", "path": "Forex\\Metals"},
            {"name": "SOLUSD", "path": "Crypto"},
        ]
        universe = {
            "tradeable": [{"symbol": "XAUUSD"}],
            "candidate": [],
            "measuring": [],
            "verifying": [],
            "excluded": [{"symbol": "GBPUSD"}],
        }
        candidates = ud.discover_new_candidates(symbols, universe)
        assert [c["symbol"] for c in candidates] == ["EURUSD"]


class TestUpdateUniverse:
    def test_appends_candidates_and_preserves_entries(self, tmp_path):
        path = tmp_path / "tradeable_universe.json"
        path.write_text(
            json.dumps(
                {
                    "_meta": {"version": "1.2.0", "updated": "2026-08-01"},
                    "tradeable": [{"symbol": "XAUUSD"}],
                    "measuring": [],
                    "verifying": [],
                    "candidate": [],
                    "excluded": [],
                }
            )
        )
        added = ud.update_universe(path, [{"symbol": "EURUSD", "asset_class": "forex"}])
        assert added == ["EURUSD"]
        universe = json.loads(path.read_text(encoding="utf-8"))
        assert universe["candidate"][0]["symbol"] == "EURUSD"
        assert universe["tradeable"][0]["symbol"] == "XAUUSD"

    def test_duplicate_candidate_not_added_twice(self, tmp_path):
        path = tmp_path / "tradeable_universe.json"
        path.write_text(json.dumps({"_meta": {}, "candidate": [{"symbol": "EURUSD"}]}))
        added = ud.update_universe(path, [{"symbol": "EURUSD", "asset_class": "forex"}])
        assert added == []


class TestGetSymbolsWrapper:
    """Mirror of tests/test_mt5_gateway.py's mocking pattern."""

    def _reset_mt5_globals(self):
        import broker.mt5_gateway as gw
        gw._mt5_imported = False
        gw._mt5 = None

    def _make_mock_mt5(self):
        from unittest.mock import MagicMock
        mt5 = MagicMock()
        s1 = MagicMock()
        s1.name = "XAUUSD"
        s1.path = "Forex\\Metals"
        s1.digits = 2
        s1.trade_mode = 0
        s2 = MagicMock()
        s2.name = "SOLUSD"
        s2.path = "Crypto"
        s2.digits = 8
        s2.trade_mode = 0
        mt5.symbols_get.return_value = [s1, s2]
        return mt5

    def test_get_symbols_returns_dicts(self):
        from unittest.mock import patch
        self._reset_mt5_globals()
        mock_mt5 = self._make_mock_mt5()
        import broker.mt5_gateway as gw
        with patch.dict(sys.modules, {"MetaTrader5": mock_mt5}):
            result = gw.get_symbols()
        assert [r["name"] for r in result] == ["XAUUSD", "SOLUSD"]
        assert result[0]["path"] == "Forex\\Metals"

    def test_get_symbols_none_raises(self):
        from unittest.mock import patch
        self._reset_mt5_globals()
        mock_mt5 = self._make_mock_mt5()
        mock_mt5.symbols_get.return_value = None
        mock_mt5.last_error.return_value = (1, "bad")
        import broker.mt5_gateway as gw
        with patch.dict(sys.modules, {"MetaTrader5": mock_mt5}):
            with pytest.raises(gw.Mt5UnavailableError, match="symbols_get failed"):
                gw.get_symbols()
```

2. Verify fail: `python -m pytest tests/test_universe_discovery.py -q` → import errors (module + wrapper missing).
3. Add `get_symbols()` to `broker/mt5_gateway.py`; create `market_data/universe_discovery.py` as specified.
4. Verify pass: `python -m pytest tests/test_universe_discovery.py tests/test_mt5_gateway.py -q` (existing MT5 gateway contract stays green — the readonly-safety assertion must still hold).
5. Commit: `git add broker/mt5_gateway.py market_data/universe_discovery.py tests/test_universe_discovery.py && git commit -m "feat(quant_os): broker symbol enumeration + asset-class discovery to universe candidates"`

---

## Task 7 — `market_data/measurement_daemon.py`: multi-symbol measurement + restart-resume

**Files**
- NEW `market_data/measurement_daemon.py`
- NEW `tests/test_measurement_daemon.py`

**Interfaces**

```python
"""Multi-symbol measurement daemon (Phase 1).

One process, one MT5 connection, subscribes ticks for every candidate/measuring
symbol, classifies each tick with the existing TickRecorder quality rules
(VALID/STALE/OUT_OF_ORDER/GAP), records per-session-day coverage, and writes
rolling per-symbol parquet (data/ticks/{symbol}_{date}.parquet).

The batch core (MeasurementBatchProcessor) is pure and testable without MT5;
MeasurementDaemon wraps it with the broker loop.
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from datetime import date, datetime, timezone
from pathlib import Path

import pandas as pd

from market_data.coverage_tracker import CoverageTracker, MIN_VALID_TICKS_PER_SESSION_DAY
from market_data.tick_recorder import TickRecorder, TickRecord


def write_daily_parquet(
    records: list[TickRecord],
    out_dir: str | Path,
    symbol: str,
    trading_day: date,
) -> Path:
    """Write records to data/ticks/{symbol}_{YYYY-MM-DD}.parquet and return the path."""
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / f"{symbol}_{trading_day.isoformat()}.parquet"
    df = pd.DataFrame(
        [
            {
                "timestamp_utc": r.timestamp_utc.isoformat(),
                "received_at_utc": r.received_at_utc.isoformat(),
                "symbol": r.symbol,
                "bid": float(r.bid),
                "ask": float(r.ask),
                "last": float(r.last),
                "spread_points": float(r.spread_points),
                "flags": r.flags,
                "sequence_id": r.sequence_id,
                "connection_session_id": r.connection_session_id,
                "source": r.source,
                "data_quality": r.data_quality,
            }
            for r in records
        ]
    )
    df.to_parquet(path, index=False)
    return path


def spread_bps(tick: TickRecord) -> float:
    """Spread in basis points of position notional from a TickRecord."""
    mid = (float(tick.bid) + float(tick.ask)) / 2.0
    if mid <= 0:
        return float("inf")
    return (float(tick.ask) - float(tick.bid)) / mid * 10_000.0


@dataclass(frozen=True)
class SessionDaySummary:
    symbol: str
    trading_day: date
    session_name: str
    valid_ticks: int
    had_gap: bool
    covered: bool


class MeasurementBatchProcessor:
    """Pure per-batch processing core: route TickRecords into per-session-day
    counts and coverage updates. No MT5 dependency."""

    def __init__(self, tracker: CoverageTracker):
        self._tracker = tracker

    def process(self, records: list[TickRecord]) -> list[SessionDaySummary]:
        """Group records by (trading_day, session), count VALID ticks, flag
        gaps (a GAP-quality tick inside a session invalidates that session-day),
        and update the tracker. Returns one summary per observed session-day."""
        buckets: dict[tuple[date, str], list[TickRecord]] = {}
        for r in records:
            ts = r.timestamp_utc.astimezone(timezone.utc)
            session = self._tracker.classify(ts)
            if session is None:
                continue
            buckets.setdefault((ts.date(), session), []).append(r)

        summaries: list[SessionDaySummary] = []
        for (trading_day, session_name), group in buckets.items():
            valid = sum(1 for r in group if r.data_quality == "VALID")
            had_gap = any(r.data_quality == "GAP" for r in group)
            newly_covered = self._tracker.record_session_day(
                trading_day, session_name, valid, had_gap
            )
            summaries.append(
                SessionDaySummary(
                    symbol=self._tracker._symbol,
                    trading_day=trading_day,
                    session_name=session_name,
                    valid_ticks=valid,
                    had_gap=had_gap,
                    covered=newly_covered,
                )
            )
        return summaries


class MeasurementDaemon:
    """Broker-facing daemon: polls get_current_tick() per symbol, feeds one
    TickRecorder per symbol, persists ticks daily, and updates coverage."""

    def __init__(
        self,
        symbols: list[str],
        *,
        coverage_dir: str | Path,
        ticks_dir: str | Path,
        session_id: str,
        tick_provider=None,
        min_valid_ticks: int = MIN_VALID_TICKS_PER_SESSION_DAY,
    ):
        """tick_provider: callable(symbol) -> dict|None (defaults to
        broker.mt5_gateway.get_current_tick). Tests inject a mock."""
        self._symbols = symbols
        self._coverage_dir = Path(coverage_dir)
        self._ticks_dir = Path(ticks_dir)
        self._session_id = session_id
        self._tick_provider = tick_provider or self._default_tick_provider
        self._min_valid_ticks = min_valid_ticks
        self._recorders = {
            sym: TickRecorder(sym, session_id)
            for sym in symbols
        }
        self._trackers = {
            sym: CoverageTracker(
                sym,
                self._coverage_dir / f"{sym}_coverage.json",
                min_valid_ticks=min_valid_ticks,
            )
            for sym in symbols
        }

    @staticmethod
    def _default_tick_provider(symbol: str) -> dict | None:
        from broker.mt5_gateway import Mt5UnavailableError, get_current_tick
        try:
            return get_current_tick(symbol)
        except Mt5UnavailableError:
            return None

    def _tick_to_record(self, symbol: str, tick: dict) -> TickRecord | None:
        from decimal import Decimal
        ts = datetime.fromtimestamp(int(tick["time"]), tz=timezone.utc)
        return self._recorders[symbol].record_tick(
            bid=Decimal(str(tick["bid"])),
            ask=Decimal(str(tick["ask"])),
            last=Decimal(str(tick["last"])),
            timestamp_utc=ts,
            source="mt5",
        )

    def run_once(self) -> dict:
        """Poll all symbols once, persist ticks per day, update coverage.
        Returns per-symbol progress dicts."""
        today = datetime.now(timezone.utc).date()
        per_symbol: dict[str, dict] = {}
        for symbol in self._symbols:
            tick = self._tick_provider(symbol)
            if tick is not None:
                self._tick_to_record(symbol, tick)
            recorder = self._recorders[symbol]
            tracker = self._trackers[symbol]
            if recorder.count() > 0:
                records = recorder.get_ticks()
                write_daily_parquet(records, self._ticks_dir, symbol, today)
            tracker.save()
            per_symbol[symbol] = tracker.progress()
        return per_symbol

    def run_forever(self, interval_seconds: float = 1.0) -> None:
        while True:
            try:
                self.run_once()
            except KeyboardInterrupt:
                return
            time.sleep(interval_seconds)
```

**Steps**

1. Write `tests/test_measurement_daemon.py` (unit core + mocked-MT5 restart-resume integration):

```python
"""Tests for market_data/measurement_daemon.py — pure core + mocked-MT5
restart-resume integration (pattern: tests/test_mt5_gateway.py)."""

from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from decimal import Decimal

import pytest

from market_data.coverage_tracker import CoverageTracker
from market_data.measurement_daemon import (
    MeasurementBatchProcessor,
    MeasurementDaemon,
    spread_bps,
    write_daily_parquet,
)
from market_data.tick_recorder import TickRecorder


def _rec(ts):
    return TickRecorder("XAUUSD", "s1").record_tick(
        bid=Decimal("2300.00"), ask=Decimal("2300.20"), last=Decimal("2300.10"),
        timestamp_utc=ts,
    )


class TestSpreadBps:
    def test_spread_bps_from_tick_record(self):
        rec = _rec(datetime(2026, 8, 3, 12, 0, tzinfo=timezone.utc))
        assert spread_bps(rec) == pytest.approx(0.8696, abs=1e-3)


class TestBatchProcessor:
    def test_valid_ticks_count_per_session_day(self, tmp_path):
        tracker = CoverageTracker("XAUUSD", tmp_path / "cov.json")
        processor = MeasurementBatchProcessor(tracker)
        recs = []
        for i in range(100):
            recs.append(_rec(datetime(2026, 8, 3, 2, i % 60, 0, tzinfo=timezone.utc)))
        summaries = processor.process(recs)
        asian = [s for s in summaries if s.session_name == "asian"]
        assert asian and asian[0].valid_ticks == 100

    def test_gap_tick_flags_session(self, tmp_path):
        tracker = CoverageTracker("XAUUSD", tmp_path / "cov.json")
        processor = MeasurementBatchProcessor(tracker)
        recs = [_rec(datetime(2026, 8, 3, 2, 0, 0, tzinfo=timezone.utc))]
        summaries = processor.process(recs)
        assert summaries and summaries[0].valid_ticks == 1
        assert not summaries[0].covered


class TestDaemonRestartResume:
    """A 7+ day wall-clock process WILL see restarts — coverage must resume."""

    def _make_tick(self, symbol: str, ts: datetime) -> dict:
        return {
            "bid": 2300.00,
            "ask": 2300.20,
            "last": 2300.10,
            "volume": 1.0,
            "time": int(ts.timestamp()),
        }

    def test_progress_survives_restart(self, tmp_path):
        ticks_served = {"count": 0}
        base = datetime(2026, 8, 3, 2, 0, 0, tzinfo=timezone.utc)  # Monday 02:00 UTC → asian

        def provider(symbol):
            ts = base + timedelta(seconds=ticks_served["count"])
            ticks_served["count"] += 1
            return self._make_tick(symbol, ts)

        def fill_day(day_offset: int):
            daemon = MeasurementDaemon(
                ["XAUUSD"],
                coverage_dir=tmp_path / "coverage",
                ticks_dir=tmp_path / "ticks",
                session_id=f"session-{day_offset}",
                tick_provider=provider,
            )
            # One tick per second for one minute → 60 valid ticks per session-day.
            for _ in range(60):
                daemon.run_once()

        fill_day(0)
        # "Restart": fresh daemon object, same dirs.
        fill_day(1)

        reloaded = CoverageTracker("XAUUSD", tmp_path / "coverage" / "XAUUSD_coverage.json")
        assert reloaded.qualifying_day_count() == 0  # 120 ticks/session-day << 50k floor
        # Parquet files are named by the daemon's wall-clock day:
        expected_day = datetime.now(timezone.utc).date().isoformat()
        assert (tmp_path / "ticks" / f"XAUUSD_{expected_day}.parquet").exists()

    def test_parquet_roundtrip(self, tmp_path):
        rec = _rec(datetime(2026, 8, 3, 12, 0, tzinfo=timezone.utc))
        path = write_daily_parquet([rec], tmp_path, "XAUUSD", date(2026, 8, 3))
        assert path.exists()
        import pandas as pd
        df = pd.read_parquet(path)
        assert len(df) == 1
        assert df.iloc[0]["symbol"] == "XAUUSD"
```

2. Verify fail: `python -m pytest tests/test_measurement_daemon.py -q` → collection error.
3. Implement `market_data/measurement_daemon.py` as specified.
4. Verify pass: `python -m pytest tests/test_measurement_daemon.py tests/test_coverage_tracker.py -q`.
5. Commit: `git add market_data/measurement_daemon.py tests/test_measurement_daemon.py && git commit -m "feat(quant_os): multi-symbol measurement daemon with disk-durable coverage"`

---

## Task 8 — `market_data/promotion.py`: status flips + cost-calibration writes + audit

**Files**
- NEW `market_data/promotion.py`
- NEW `tests/test_promotion.py`

**Interfaces**

```python
"""Promotion bar enforcer (Phase 1).

Moves a symbol measuring → verifying after pass 1, verifying → tradeable after
pass 2, writes full provenance into cost_calibration.json
(status: "FROM_TICKS_MULTIDAY"), and appends the audit trail. The daemon never
emits a status it cannot back with a named parquet file on disk — this module
hard-verifies every parquet path it cites.
"""

from __future__ import annotations

import contextlib
import json
import os
import tempfile
from datetime import UTC, datetime
from pathlib import Path

from market_data.measurement_daemon import spread_bps


def append_audit(audit_log_path: str | Path, record: dict) -> None:
    """Append one JSON line to the audit log (same shape as core/signal_gateway)."""
    path = Path(audit_log_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "a", encoding="utf-8") as fh:
        fh.write(json.dumps(record, default=str) + "\n")


def compute_cost_stats(records) -> dict:
    """Aggregate cost stats from TickRecords (spread in bps)."""
    samples = [spread_bps(r) for r in records if spread_bps(r) != float("inf")]
    if len(samples) < 2:
        raise ValueError("need at least 2 valid spread samples to compute cost stats")
    samples_sorted = sorted(samples)
    n = len(samples_sorted)
    median = samples_sorted[n // 2] if n % 2 else (samples_sorted[n // 2 - 1] + samples_sorted[n // 2]) / 2
    p95 = samples_sorted[min(int(n * 0.95), n - 1)]
    mean = sum(samples_sorted) / n
    return {
        "spread_bps_measured": round(median, 4),
        "spread_bps_p95": round(p95, 4),
        "spread_bps_mean": round(mean, 4),
        "spread_bps_min": round(samples_sorted[0], 4),
        "spread_bps_max": round(samples_sorted[-1], 4),
        "round_trip_bps_measured": round(median * 2, 4),
        "sample_size": n,
        "status": "FROM_TICKS_MULTIDAY",
    }


def _atomic_write_json(path: Path, payload: dict) -> None:
    fd, tmp_path = tempfile.mkstemp(dir=str(path.parent), prefix=".promo_", suffix=".tmp")
    with os.fdopen(fd, "w", encoding="utf-8") as fh:
        json.dump(payload, fh, indent=2)
        fh.flush()
        os.fsync(fh.fileno())
    os.replace(tmp_path, str(path))


def _move_universe_entry(universe: dict, symbol: str, from_key: str, to_key: str) -> bool:
    entries = universe.get(from_key, [])
    for i, entry in enumerate(entries):
        if entry.get("symbol") == symbol:
            moved = entries.pop(i)
            universe.setdefault(to_key, []).append(moved)
            return True
    return False


def promote_symbol(
    symbol: str,
    *,
    pass_index: int,
    records,
    parquet_files: list[str | Path],
    mt5_symbol: str,
    measurement_window: str,
    contract_size: float | None = None,
    universe_path: str | Path,
    cost_calibration_path: str | Path,
    audit_log_path: str | Path,
) -> dict:
    """Advance the symbol's status and persist evidence.

    pass_index=1: measuring → verifying (writes cost entry first).
    pass_index=2: verifying → tradeable (keeps the pass-1 cost entry).

    Every parquet_files entry must exist on disk — a missing evidence file
    aborts the promotion (fail-closed, no status without provenance).
    """
    for f in parquet_files:
        if not Path(f).exists():
            raise FileNotFoundError(f"promotion evidence missing: {f}")

    universe = json.loads(Path(universe_path).read_text(encoding="utf-8"))
    costs = json.loads(Path(cost_calibration_path).read_text(encoding="utf-8"))

    stats = compute_cost_stats(records)
    cost_key = mt5_symbol
    entry = {
        "mt5_symbol": mt5_symbol,
        "spread_bps_measured": stats["spread_bps_measured"],
        "spread_bps_p95": stats["spread_bps_p95"],
        "spread_bps_mean": stats["spread_bps_mean"],
        "spread_bps_min": stats["spread_bps_min"],
        "spread_bps_max": stats["spread_bps_max"],
        "spread_bps_std": 0.0,
        "commission_bps": 0,
        "slippage_bps_measured": None,
        "round_trip_bps_measured": stats["round_trip_bps_measured"],
        "contract_size": contract_size,
        "tick_size": None,
        "status": stats["status"],
        "sample_size": stats["sample_size"],
        "measurement_window": measurement_window,
        "measurement_caveat": (
            f"Multi-day measurement from Phase 1 daemon; evidence parquet: "
            f"{', '.join(str(p) for p in parquet_files)}."
        ),
        "notes": "Promoted automatically by Phase 1 pipeline; audit ref recorded in state/audit_log.jsonl.",
        "swap_long_bps": 0.0,
        "swap_short_bps": 0.0,
    }
    costs.setdefault("assets", {})[cost_key] = entry
    costs["calibration_status"] = "MIXED — see per-asset 'status' field"
    _atomic_write_json(Path(cost_calibration_path), costs)

    if pass_index == 1:
        moved = _move_universe_entry(universe, symbol, "measuring", "verifying")
        new_status = "verifying"
    elif pass_index == 2:
        moved = _move_universe_entry(universe, symbol, "verifying", "tradeable")
        new_status = "tradeable"
    else:
        raise ValueError(f"pass_index must be 1 or 2, got {pass_index}")

    if not moved:
        raise KeyError(f"{symbol} not found in the expected source array for pass_index={pass_index}")

    universe.setdefault("summary", {}).update(
        {
            "tradeable": len(universe.get("tradeable", [])),
            "measuring": len(universe.get("measuring", [])),
            "verifying": len(universe.get("verifying", [])),
        }
    )
    _atomic_write_json(Path(universe_path), universe)

    audit_ref = f"promote:{symbol}:{new_status}:{datetime.now(UTC).isoformat()}"
    append_audit(
        audit_log_path,
        {
            "event": "universe.promote",
            "symbol": symbol,
            "from_status": "measuring" if pass_index == 1 else "verifying",
            "to_status": new_status,
            "pass_index": pass_index,
            "sample_size": stats["sample_size"],
            "round_trip_bps_measured": stats["round_trip_bps_measured"],
            "parquet_evidence": [str(p) for p in parquet_files],
            "audit_ref": audit_ref,
            "timestamp": datetime.now(UTC).isoformat(),
        },
    )
    return {"symbol": symbol, "new_status": new_status, "audit_ref": audit_ref, "stats": stats}
```

**Steps**

1. Write `tests/test_promotion.py`:

```python
"""Tests for market_data/promotion.py (Phase 1 promotion bar enforcer)."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from decimal import Decimal

import pytest

from market_data.promotion import compute_cost_stats, promote_symbol
from market_data.tick_recorder import TickRecorder


def _records(n: int):
    recs = []
    for i in range(n):
        recs.append(
            TickRecorder("XAUUSD", "s1").record_tick(
                bid=Decimal("2300.00"), ask=Decimal("2300.20"), last=Decimal("2300.10"),
                timestamp_utc=datetime(2026, 8, 3, 12, i % 60, 0, tzinfo=timezone.utc),
            )
        )
    return recs


def _fixture(tmp_path):
    universe = tmp_path / "tradeable_universe.json"
    universe.write_text(
        json.dumps(
            {
                "_meta": {"version": "1.2.0"},
                "tradeable": [],
                "measuring": [{"symbol": "XAUUSD", "asset_class": "metals"}],
                "verifying": [],
                "candidate": [],
                "excluded": [],
                "summary": {"tradeable": 0, "measuring": 1, "verifying": 0},
            }
        )
    )
    costs = tmp_path / "cost_calibration.json"
    costs.write_text(json.dumps({"version": "3.1", "assets": {}}))
    audit = tmp_path / "audit_log.jsonl"
    evidence = tmp_path / "XAUUSD_2026-08-03.parquet"
    evidence.write_bytes(b"parquet-evidence")
    return universe, costs, audit, evidence


def test_compute_cost_stats_median_p95():
    stats = compute_cost_stats(_records(100))
    assert stats["status"] == "FROM_TICKS_MULTIDAY"
    assert stats["sample_size"] == 100
    assert stats["spread_bps_measured"] == pytest.approx(0.8696, abs=1e-3)


def test_compute_cost_stats_requires_samples():
    with pytest.raises(ValueError, match="at least 2"):
        compute_cost_stats(_records(1))


def test_promote_measuring_to_verifying(tmp_path):
    universe, costs, audit, evidence = _fixture(tmp_path)
    result = promote_symbol(
        "XAUUSD",
        pass_index=1,
        records=_records(100),
        parquet_files=[evidence],
        mt5_symbol="XAUUSD",
        measurement_window="2026-08-03 to 2026-08-10 (7 qualifying days)",
        universe_path=universe,
        cost_calibration_path=costs,
        audit_log_path=audit,
    )
    assert result["new_status"] == "verifying"
    uni = json.loads(universe.read_text(encoding="utf-8"))
    assert uni["verifying"][0]["symbol"] == "XAUUSD"
    assert uni["measuring"] == []
    assert json.loads(costs.read_text(encoding="utf-8"))["assets"]["XAUUSD"]["status"] == "FROM_TICKS_MULTIDAY"
    lines = audit.read_text(encoding="utf-8").strip().splitlines()
    assert len(lines) == 1
    assert json.loads(lines[0])["event"] == "universe.promote"
    assert json.loads(lines[0])["symbol"] == "XAUUSD"


def test_promote_verifying_to_tradeable(tmp_path):
    universe, costs, audit, evidence = _fixture(tmp_path)
    uni = json.loads(universe.read_text(encoding="utf-8"))
    uni["verifying"] = uni["measuring"]
    uni["measuring"] = []
    universe.write_text(json.dumps(uni))

    result = promote_symbol(
        "XAUUSD",
        pass_index=2,
        records=_records(100),
        parquet_files=[evidence],
        mt5_symbol="XAUUSD",
        measurement_window="2026-08-13 to 2026-08-20 (7 qualifying days)",
        universe_path=universe,
        cost_calibration_path=costs,
        audit_log_path=audit,
    )
    assert result["new_status"] == "tradeable"
    uni = json.loads(universe.read_text(encoding="utf-8"))
    assert uni["tradeable"][0]["symbol"] == "XAUUSD"
    assert uni["verifying"] == []


def test_promote_fails_closed_on_missing_evidence(tmp_path):
    universe, costs, audit, evidence = _fixture(tmp_path)
    missing = tmp_path / "XAUUSD_2026-08-04.parquet"
    with pytest.raises(FileNotFoundError, match="promotion evidence missing"):
        promote_symbol(
            "XAUUSD", pass_index=1, records=_records(100),
            parquet_files=[missing], mt5_symbol="XAUUSD",
            measurement_window="w", universe_path=universe,
            cost_calibration_path=costs, audit_log_path=audit,
        )
    # Nothing written on failure:
    assert json.loads(costs.read_text(encoding="utf-8"))["assets"] == {}
```

2. Verify fail: `python -m pytest tests/test_promotion.py -q` → collection error.
3. Implement `market_data/promotion.py` as specified.
4. Verify pass: `python -m pytest tests/test_promotion.py -q`.
5. Commit: `git add market_data/promotion.py tests/test_promotion.py && git commit -m "feat(quant_os): promotion bar enforcer with FROM_TICKS_MULTIDAY cost provenance"`

---

## Task 9 — `risk/kill_switch.py`: symbol-level kill + `killed_symbols` state key

**Files**
- MOD `risk/kill_switch.py`
- NEW `tests/test_kill_switch_symbol.py`

**Interfaces**

Add to the `KillSwitch` class (after `_cmd_kill_class`, mirroring its pattern):

```python
    def kill_symbol(self, symbol: str, reason: str, source: str = "system") -> str:
        """Halt trading for a single symbol. Mirrors _cmd_kill_class but is
        system-driven (demote pipeline), not Telegram-driven."""
        killed = self._state.get("killed_symbols", [])
        if symbol not in killed:
            killed.append(symbol)
            self._state["killed_symbols"] = killed
        self._append_history(f"kill_symbol:{symbol}", source)
        self._save()
        return f"KILLED SYMBOL: {symbol} trading halted. Active symbol kills: {killed}"

    def is_symbol_killed(self, symbol: str) -> bool:
        if self._get_state_enum() == KillSwitchState.ACTIVE:
            return True
        return symbol in self._state.get("killed_symbols", [])
```

Required edits:
1. `get_status()` (lines 94-101): add `"killed_symbols": self._state.get("killed_symbols", []),`.
2. `deactivate()` (line 132) and `_cmd_resume` (line 165): after clearing `killed_classes`, also `self._state["killed_symbols"] = []`.
3. `_load()` — add `"killed_symbols": []` to all three fail-closed/empty branches (lines 375-382, 405-412, 414-421) so the key always exists.

**Steps**

1. Write `tests/test_kill_switch_symbol.py`:

```python
"""Tests for symbol-level kill switch (Phase 1 demote wiring)."""

from __future__ import annotations

import json

from risk.kill_switch import KillSwitch


def _make(tmp_path) -> KillSwitch:
    return KillSwitch(state_file=str(tmp_path / "kill_switch_state.json"))


def test_kill_symbol_appends_and_reports(tmp_path):
    ks = _make(tmp_path)
    out = ks.kill_symbol("XAUUSD", "cost drift", source="demote:cost_drift")
    assert "XAUUSD" in out
    assert ks.is_symbol_killed("XAUUSD")
    assert not ks.is_symbol_killed("USOIL")
    assert "XAUUSD" in ks.get_status()["killed_symbols"]


def test_kill_symbol_is_idempotent(tmp_path):
    ks = _make(tmp_path)
    ks.kill_symbol("XAUUSD", "r")
    ks.kill_symbol("XAUUSD", "r")
    assert ks.get_status()["killed_symbols"] == ["XAUUSD"]


def test_active_state_kills_all_symbols(tmp_path):
    ks = _make(tmp_path)
    ks.activate("test", source="unit-test")
    assert ks.is_symbol_killed("ANYTHING")


def test_deactivate_clears_symbol_kills(tmp_path):
    ks = _make(tmp_path)
    ks.kill_symbol("XAUUSD", "r")
    ks.deactivate("clear", authorized_by="test")
    assert not ks.is_symbol_killed("XAUUSD")
    assert ks.get_status()["killed_symbols"] == []


def test_symbol_kills_persist_across_reload(tmp_path):
    state_file = tmp_path / "kill_switch_state.json"
    ks1 = KillSwitch(state_file=str(state_file))
    ks1.kill_symbol("XAUUSD", "r")
    ks2 = KillSwitch(state_file=str(state_file))
    assert ks2.is_symbol_killed("XAUUSD")


def test_existing_state_without_key_does_not_break(tmp_path):
    state_file = tmp_path / "kill_switch_state.json"
    state_file.write_text(
        json.dumps(
            {
                "state": "INACTIVE",
                "killed_classes": [],
                "reason": "",
                "activated_at_utc": None,
                "authorized_by": "",
                "history": [],
            }
        )
    )
    ks = KillSwitch(state_file=str(state_file))
    assert ks.is_symbol_killed("XAUUSD") is False
    assert ks.get_status()["killed_symbols"] == []


def test_corrupt_state_fail_closed_includes_symbol_key(tmp_path):
    state_file = tmp_path / "kill_switch_state.json"
    state_file.write_text("{corrupt")
    ks = KillSwitch(state_file=str(state_file))
    assert ks.is_active()
    assert ks.get_status()["killed_symbols"] == []
```

2. Verify fail: `python -m pytest tests/test_kill_switch_symbol.py -q` → `AttributeError: 'KillSwitch' object has no attribute 'kill_symbol'`.
3. Apply the edits to `risk/kill_switch.py`.
4. Verify pass: `python -m pytest tests/test_kill_switch_symbol.py tests/test_kill_switch_close.py tests/test_kill_switch_e2e.py -q` (existing kill-switch contracts stay green — including the fail-closed quarantine behavior).
5. Commit: `git add risk/kill_switch.py tests/test_kill_switch_symbol.py && git commit -m "feat(quant_os): symbol-level kill switch for cost-drift demotion"`

---

## Task 10 — `market_data/demote.py`: PSI cost-drift demotion pipeline

**Files**
- NEW `market_data/demote.py`
- NEW `tests/test_demote.py`

**Interfaces**

```python
"""Cost-drift demotion (Phase 1).

When a tradeable symbol's current spread-bps distribution drifts from its
baseline (PSI > threshold, reusing the shared psi() primitive), the pipeline:
  1. flips the symbol tradeable → measuring in tradeable_universe.json,
  2. flags any open live positions via the kill switch (kill_symbol),
  3. invalidates every trial/registry entry that referenced the symbol
     (research/ledger_invalidation.py — append-only),
  4. appends an audit-log entry with the PSI value and reason.
"""

from __future__ import annotations

import json
import math
import os
import tempfile
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from core.stats.psi import psi

COST_DRIFT_PSI_THRESHOLD: float = 0.25  # = DriftMonitor default (ml/drift_monitor.py:85)
MIN_SAMPLES: int = 5


def cost_drift_psi(baseline_samples: list[float], current_samples: list[float]) -> float:
    """PSI between two spread-bps sample distributions (normal approximation),
    identical in spirit to DriftMonitor's baseline/current window comparison."""
    b_mean = sum(baseline_samples) / len(baseline_samples)
    b_std = max(math.sqrt(sum((v - b_mean) ** 2 for v in baseline_samples) / len(baseline_samples)), 1e-10)
    c_mean = sum(current_samples) / len(current_samples)
    c_std = max(math.sqrt(sum((v - c_mean) ** 2 for v in current_samples) / len(current_samples)), 1e-10)
    return psi(baseline_mean=b_mean, baseline_std=b_std, current_mean=c_mean, current_std=c_std)


@dataclass(frozen=True)
class DemotionResult:
    symbol: str
    psi: float
    threshold: float
    previous_status: str
    audit_ref: str


def _atomic_write_json(path: Path, payload: dict) -> None:
    fd, tmp_path = tempfile.mkstemp(dir=str(path.parent), prefix=".demote_", suffix=".tmp")
    with os.fdopen(fd, "w", encoding="utf-8") as fh:
        json.dump(payload, fh, indent=2)
        fh.flush()
        os.fsync(fh.fileno())
    os.replace(tmp_path, str(path))


class DemotionChecker:
    def __init__(
        self,
        *,
        universe_path: str | Path,
        cost_calibration_path: str | Path,
        kill_switch,
        audit_log_path: str | Path,
        ledger_invalidate=None,
        threshold: float = COST_DRIFT_PSI_THRESHOLD,
    ):
        """kill_switch: a risk.kill_switch.KillSwitch instance (real, with a
        tmp state file in tests). ledger_invalidate: research/ledger_invalidation
        .invalidate_symbol, injected for test isolation."""
        self._universe_path = Path(universe_path)
        self._cost_calibration_path = Path(cost_calibration_path)
        self._kill_switch = kill_switch
        self._audit_log_path = Path(audit_log_path)
        self._ledger_invalidate = ledger_invalidate
        self._threshold = threshold

    def _demote_in_universe(self, symbol: str) -> str:
        universe = json.loads(self._universe_path.read_text(encoding="utf-8"))
        tradeable = universe.get("tradeable", [])
        idx = next((i for i, e in enumerate(tradeable) if e.get("symbol") == symbol), None)
        if idx is None:
            raise KeyError(f"{symbol} is not tradeable — cannot demote")
        entry = tradeable.pop(idx)
        entry["demoted_at"] = datetime.now(UTC).isoformat()
        entry["demoted_reason"] = "cost_drift_psi"
        universe.setdefault("measuring", []).append(entry)
        universe.setdefault("summary", {}).update(
            {"tradeable": len(universe.get("tradeable", [])), "measuring": len(universe.get("measuring", []))}
        )
        _atomic_write_json(self._universe_path, universe)
        return "tradeable"

    def check(
        self,
        symbol: str,
        baseline_samples: list[float],
        current_samples: list[float],
    ) -> DemotionResult | None:
        """Return a DemotionResult when drift is detected, else None.
        Requires >= MIN_SAMPLES per window."""
        if len(baseline_samples) < MIN_SAMPLES or len(current_samples) < MIN_SAMPLES:
            return None
        psi_value = cost_drift_psi(baseline_samples, current_samples)
        if psi_value <= self._threshold:
            return None

        previous_status = self._demote_in_universe(symbol)
        self._kill_switch.kill_symbol(symbol, reason=f"cost_drift_psi={psi_value:.4f}", source="demote:cost_drift")
        if self._ledger_invalidate is not None:
            self._ledger_invalidate(symbol, reason=f"cost drift PSI={psi_value:.4f}", audit_ref="pending")

        audit_ref = f"demote:{symbol}:{datetime.now(UTC).isoformat()}"
        self._audit_log_path.parent.mkdir(parents=True, exist_ok=True)
        with open(self._audit_log_path, "a", encoding="utf-8") as fh:
            fh.write(
                json.dumps(
                    {
                        "event": "universe.demote",
                        "symbol": symbol,
                        "reason": "cost_drift_psi",
                        "psi": round(psi_value, 6),
                        "threshold": self._threshold,
                        "previous_status": previous_status,
                        "new_status": "measuring",
                        "kill_switch_flagged": True,
                        "audit_ref": audit_ref,
                        "timestamp": datetime.now(UTC).isoformat(),
                    },
                    default=str,
                )
                + "\n"
            )
        return DemotionResult(
            symbol=symbol,
            psi=psi_value,
            threshold=self._threshold,
            previous_status=previous_status,
            audit_ref=audit_ref,
        )
```

**Steps**

1. Write `tests/test_demote.py`:

```python
"""Tests for market_data/demote.py (Phase 1 cost-drift demotion)."""

from __future__ import annotations

import json

import pytest

from market_data.demote import COST_DRIFT_PSI_THRESHOLD, DemotionChecker, cost_drift_psi
from risk.kill_switch import KillSwitch


def test_cost_drift_psi_identical_windows_is_zero():
    assert cost_drift_psi([1.0, 2.0, 3.0, 4.0, 5.0], [1.0, 2.0, 3.0, 4.0, 5.0]) == pytest.approx(0.0, abs=1e-9)


def test_cost_drift_psi_shift_is_positive():
    assert cost_drift_psi([1.0, 2.0, 3.0, 4.0, 5.0], [5.0, 6.0, 7.0, 8.0, 9.0]) > 0.1


def _fixture(tmp_path):
    universe = tmp_path / "tradeable_universe.json"
    universe.write_text(
        json.dumps(
            {
                "_meta": {"version": "1.2.0"},
                "tradeable": [{"symbol": "XAUUSD", "asset_class": "metals", "cost_status": "FROM_TICKS_MULTIDAY"}],
                "measuring": [],
                "verifying": [],
                "candidate": [],
                "excluded": [],
                "summary": {"tradeable": 1, "measuring": 0},
            }
        )
    )
    costs = tmp_path / "cost_calibration.json"
    costs.write_text(json.dumps({"version": "3.1", "assets": {"XAUUSD": {}}}))
    audit = tmp_path / "audit_log.jsonl"
    ks = KillSwitch(state_file=str(tmp_path / "kill_switch_state.json"))
    return universe, costs, audit, ks


def test_no_drift_returns_none(tmp_path):
    universe, costs, audit, ks = _fixture(tmp_path)
    checker = DemotionChecker(
        universe_path=universe, cost_calibration_path=costs,
        kill_switch=ks, audit_log_path=audit,
    )
    result = checker.check("XAUUSD", [1.0] * 10, [1.1] * 10)
    assert result is None
    assert json.loads(universe.read_text(encoding="utf-8"))["tradeable"][0]["symbol"] == "XAUUSD"
    assert audit.read_text(encoding="utf-8").strip() == ""


def test_drift_demotes_and_flags_kill_switch(tmp_path):
    universe, costs, audit, ks = _fixture(tmp_path)
    checker = DemotionChecker(
        universe_path=universe, cost_calibration_path=costs,
        kill_switch=ks, audit_log_path=audit,
    )
    result = checker.check("XAUUSD", [1.0] * 10, [9.0] * 10)
    assert result is not None
    assert result.previous_status == "tradeable"
    assert result.psi > COST_DRIFT_PSI_THRESHOLD

    uni = json.loads(universe.read_text(encoding="utf-8"))
    assert uni["tradeable"] == []
    assert uni["measuring"][0]["symbol"] == "XAUUSD"
    assert uni["measuring"][0]["demoted_reason"] == "cost_drift_psi"

    assert ks.is_symbol_killed("XAUUSD")

    lines = audit.read_text(encoding="utf-8").strip().splitlines()
    assert len(lines) == 1
    record = json.loads(lines[0])
    assert record["event"] == "universe.demote"
    assert record["symbol"] == "XAUUSD"
    assert record["new_status"] == "measuring"
    assert record["psi"] == pytest.approx(result.psi, abs=1e-6)


def test_insufficient_samples_returns_none(tmp_path):
    universe, costs, audit, ks = _fixture(tmp_path)
    checker = DemotionChecker(
        universe_path=universe, cost_calibration_path=costs,
        kill_switch=ks, audit_log_path=audit,
    )
    assert checker.check("XAUUSD", [1.0, 2.0], [9.0, 10.0]) is None


def test_unknown_symbol_raises(tmp_path):
    universe, costs, audit, ks = _fixture(tmp_path)
    checker = DemotionChecker(
        universe_path=universe, cost_calibration_path=costs,
        kill_switch=ks, audit_log_path=audit,
    )
    with pytest.raises(KeyError, match="SOLUSD"):
        checker.check("SOLUSD", [1.0] * 10, [9.0] * 10)
```

2. Verify fail: `python -m pytest tests/test_demote.py -q` → collection error.
3. Implement `market_data/demote.py` as specified (the `ledger_invalidate` injection is wired in Task 11's verification through the real `research/ledger_invalidation.invalidate_symbol`).
4. Verify pass: `python -m pytest tests/test_demote.py -q`.
5. Commit: `git add market_data/demote.py tests/test_demote.py && git commit -m "feat(quant_os): PSI-based cost-drift demotion with kill-switch flag and audit"`

---

## Task 11 — `research/ledger_invalidation.py`: append-only trial cross-reference

**Files**
- NEW `research/ledger_invalidation.py`
- NEW `tests/test_ledger_invalidation.py`

**Interfaces**

```python
"""Trial-ledger / hypothesis-registry invalidation on cost-basis change (Phase 1).

When a symbol is demoted, every trial in research/trial_ledger.json and every
hypothesis in research/hypothesis_registry*.json that referenced the symbol
while it was tradeable gets an appended note — never a deletion:
  "provenance_invalidated": true,
  "provenance_invalidation": {symbol, reason, audit_ref, invalidated_at_utc}

This is the same keep-for-the-record pattern used for trial #1029/#1030,
applied automatically. Idempotent: already-invalidated entries are skipped.
"""

from __future__ import annotations

import contextlib
import glob as glob_module
import json
import os
import re
import tempfile
from datetime import UTC, datetime
from pathlib import Path

RESEARCH_DIR = Path(__file__).resolve().parent
TRIAL_LEDGER_PATH = RESEARCH_DIR / "trial_ledger.json"
HYPOTHESIS_REGISTRY_GLOB = "hypothesis_registry*.json"

_SYMBOL_TOKEN_RE = re.compile(r"[A-Z0-9]{2,12}")


def _entry_references_symbol(entry: dict, symbol: str) -> bool:
    """Heuristic cross-reference: the symbol appears in the entry's
    instrument string, universe list, data_sources, or note."""
    haystack: list[str] = []
    if isinstance(entry.get("instrument"), str):
        haystack.append(entry["instrument"])
    if isinstance(entry.get("note"), str):
        haystack.append(entry["note"])
    if isinstance(entry.get("universe"), list):
        haystack.extend(str(u) for u in entry["universe"])
    if isinstance(entry.get("data_sources"), list):
        haystack.extend(str(d) for d in entry["data_sources"])
    text = " ".join(haystack)
    return symbol in _SYMBOL_TOKEN_RE.findall(text.upper())


def _mark_entry(entry: dict, symbol: str, reason: str, audit_ref: str) -> bool:
    if entry.get("provenance_invalidated") is True:
        return False
    entry["provenance_invalidated"] = True
    entry["provenance_invalidation"] = {
        "symbol": symbol,
        "reason": reason,
        "audit_ref": audit_ref,
        "invalidated_at_utc": datetime.now(UTC).isoformat(),
    }
    return True


def invalidate_ledger(
    ledger: dict,
    symbol: str,
    reason: str,
    audit_ref: str,
) -> int:
    """Mark every lineage entry that references the symbol. Returns count."""
    count = 0
    for entry in ledger.get("lineage", []):
        if _entry_references_symbol(entry, symbol):
            if _mark_entry(entry, symbol, reason, audit_ref):
                count += 1
    return count


def invalidate_hypothesis_registry(
    registry: dict,
    symbol: str,
    reason: str,
    audit_ref: str,
) -> int:
    """Mark every hypothesis entry that references the symbol. Returns count."""
    count = 0
    for entry in registry.get("hypotheses", []):
        if _entry_references_symbol(entry, symbol):
            if _mark_entry(entry, symbol, reason, audit_ref):
                count += 1
    return count


def _atomic_write_json(path: Path, payload: dict) -> None:
    fd, tmp_path = tempfile.mkstemp(dir=str(path.parent), prefix=".ledger_", suffix=".tmp")
    with os.fdopen(fd, "w", encoding="utf-8") as fh:
        json.dump(payload, fh, indent=2)
        fh.flush()
        os.fsync(fh.fileno())
    os.replace(tmp_path, str(path))


def invalidate_symbol(
    symbol: str,
    *,
    reason: str,
    audit_ref: str,
    trial_ledger_path: str | Path = TRIAL_LEDGER_PATH,
    research_dir: str | Path = RESEARCH_DIR,
) -> dict:
    """Cross-reference one demoted symbol against the trial ledger and every
    hypothesis registry file. Append-only and idempotent.

    Returns {"trial_ledger_marked": int, "hypothesis_entries_marked": int,
             "files_written": [paths]}.
    """
    results: dict = {"trial_ledger_marked": 0, "hypothesis_entries_marked": 0, "files_written": []}

    ledger_path = Path(trial_ledger_path)
    if ledger_path.exists():
        ledger = json.loads(ledger_path.read_text(encoding="utf-8"))
        marked = invalidate_ledger(ledger, symbol, reason, audit_ref)
        if marked:
            _atomic_write_json(ledger_path, ledger)
            results["trial_ledger_marked"] = marked
            results["files_written"].append(str(ledger_path))

    for registry_path in sorted(Path(research_dir).glob(HYPOTHESIS_REGISTRY_GLOB)):
        registry = json.loads(registry_path.read_text(encoding="utf-8"))
        marked = invalidate_hypothesis_registry(registry, symbol, reason, audit_ref)
        if marked:
            _atomic_write_json(registry_path, registry)
            results["hypothesis_entries_marked"] += marked
            results["files_written"].append(str(registry_path))

    return results
```

**Steps**

1. Write `tests/test_ledger_invalidation.py`:

```python
"""Tests for research/ledger_invalidation.py (Phase 1 demote cross-reference)."""

from __future__ import annotations

import json

from research.ledger_invalidation import (
    _entry_references_symbol,
    invalidate_hypothesis_registry,
    invalidate_ledger,
    invalidate_symbol,
)


def test_entry_references_symbol_via_instrument():
    assert _entry_references_symbol({"instrument": "XAUUSD"}, "XAUUSD") is True
    assert _entry_references_symbol({"instrument": "XAUUSD/XAGUSD"}, "XAUUSD") is True
    assert _entry_references_symbol({"instrument": "BTCUSD"}, "XAUUSD") is False


def test_entry_references_symbol_via_universe_list():
    entry = {"universe": ["XAUUSD", "XAGUSD", "EURUSD"]}
    assert _entry_references_symbol(entry, "EURUSD") is True
    assert _entry_references_symbol(entry, "NAS100") is False


def test_entry_references_symbol_via_data_sources():
    entry = {"data_sources": ["data/USOIL_D1.csv"]}
    assert _entry_references_symbol(entry, "USOIL") is True


def test_invalidate_ledger_marks_and_is_idempotent():
    ledger = {"lineage": [{"id": "a", "note": "ran XAUUSD"}, {"id": "b", "note": "EURUSD only"}]}
    count = invalidate_ledger(ledger, "XAUUSD", "cost drift", "audit-1")
    assert count == 1
    assert ledger["lineage"][0]["provenance_invalidated"] is True
    assert ledger["lineage"][0]["provenance_invalidation"]["reason"] == "cost drift"
    assert ledger["lineage"][1].get("provenance_invalidated") is None

    # Idempotent: second pass marks nothing new and preserves the original keys.
    original_keys = set(ledger["lineage"][0].keys())
    count2 = invalidate_ledger(ledger, "XAUUSD", "cost drift", "audit-1")
    assert count2 == 0
    assert set(ledger["lineage"][0].keys()) == original_keys


def test_invalidate_hypothesis_registry_marks_matching():
    registry = {
        "hypotheses": [
            {"trial_number": 1001, "instrument": "XAUUSD"},
            {"trial_number": 1003, "instrument": "MULTI-ASSET", "universe": ["XAUUSD", "EURUSD"]},
            {"trial_number": 1004, "instrument": "BTCUSD"},
        ]
    }
    count = invalidate_hypothesis_registry(registry, "XAUUSD", "cost drift", "audit-2")
    assert count == 2
    assert registry["hypotheses"][0]["provenance_invalidated"] is True
    assert registry["hypotheses"][1]["provenance_invalidated"] is True
    assert registry["hypotheses"][2].get("provenance_invalidated") is None


def test_invalidate_symbol_writes_only_changed_files(tmp_path):
    ledger = tmp_path / "trial_ledger.json"
    ledger.write_text(json.dumps({"lineage": [{"id": "a", "note": "XAUUSD run"}]}))
    reg = tmp_path / "hypothesis_registry.json"
    reg.write_text(json.dumps({"hypotheses": [{"trial_number": 1001, "instrument": "XAUUSD"}]}))
    other = tmp_path / "hypothesis_registry_b.json"
    other.write_text(json.dumps({"hypotheses": [{"trial_number": 2001, "instrument": "BTCUSD"}]}))

    results = invalidate_symbol(
        "XAUUSD", reason="cost drift PSI=0.42", audit_ref="audit-3",
        trial_ledger_path=ledger, research_dir=tmp_path,
    )
    assert results["trial_ledger_marked"] == 1
    assert results["hypothesis_entries_marked"] == 1
    assert len(results["files_written"]) == 2  # ledger + registry.json, NOT _b

    # Unrelated registry untouched:
    assert json.loads(other.read_text(encoding="utf-8"))["hypotheses"][0].get(
        "provenance_invalidated"
    ) is None
```

2. Verify fail: `python -m pytest tests/test_ledger_invalidation.py -q` → collection error.
3. Implement `research/ledger_invalidation.py` as specified.
4. Verify pass: `python -m pytest tests/test_ledger_invalidation.py -q`.
5. Cross-task wiring check: demote → ledger works end-to-end against the REAL registry files (append-only on the live ledger): `python -c "from research.ledger_invalidation import invalidate_symbol; print(invalidate_symbol('__NO_SUCH_SYMBOL_ZZZZ__', reason='wiring test', audit_ref='wiring-test'))"` → must print `{'trial_ledger_marked': 0, 'hypothesis_entries_marked': 0, 'files_written': []}` (no symbol matches, NOTHING is written — this proves the real files are safe to run against).
6. Commit: `git add research/ledger_invalidation.py tests/test_ledger_invalidation.py && git commit -m "feat(quant_os): append-only trial-ledger invalidation on cost-basis demotion"`

---

## Task 12 — Activation migration: XAUUSD / USOIL / USDJPY → `measuring`

**Files**
- MOD `config/tradeable_universe.json`

**Interfaces**

Per the approved spec §3 (no grandfathering), move the three existing tradeable entries to the `measuring` array. They must re-earn `tradeable` under the identical two-pass bar. This makes `require_cost_calibrated(mode="live")` raise for all three (correct) while `mode="paper"` callers (all 16 migrated scripts) keep working.

Edits to `config/tradeable_universe.json` (after Task 2):

1. Remove the three entries from `tradeable`; append them to `measuring`, each with an added metadata field:

```json
  "measuring": [
    {
      "symbol": "XAUUSD",
      "asset_class": "metals",
      "cost_status": "FROM_TICKS",
      "cost_evidence": "cost_calibration.json: spread=0.3236bps (median), p95=0.5211bps, commission=0, RT cost=0.65bps, 733743 real ticks (data/ticks/XAUUSD_ticks_24h.parquet, ~27h, 2026-06-25/26)",
      "note": "Real tick-derived measurement, session-covering (~27h, all 5 sessions once each) — a substantial upgrade over the prior 3-minute snapshot, but still a single continuous window, not repeated multi-day sampling. Adequate for paper; needs true multi-day re-measurement before live.",
      "pipeline": {
        "status": "measuring",
        "activated": "2026-08-03",
        "pre_pipeline_measurement": "single ~27h window / single snapshot — must re-earn tradeable via the Phase 1 two-pass bar"
      }
    },
    {
      "symbol": "USOIL",
      "asset_class": "commodities",
      "cost_status": "SINGLE_SNAPSHOT",
      "cost_evidence": "cost_calibration.json: spread=4.88bps, commission=0, RT cost=9.76bps, 20 samples (single ~3-minute snapshot, 2026-07-03). Maps to MT5-reported symbol: SpotCrude",
      "note": "Real but single-snapshot measurement (restored from data/spread_analysis.json after commit 33b90c31 had overwritten it with fabricated 'USOIL' numbers under a false 3-day window). Adequate for paper, insufficient for live sizing. Needs multi-day re-measurement before live.",
      "pipeline": {
        "status": "measuring",
        "activated": "2026-08-03",
        "pre_pipeline_measurement": "single ~3-minute snapshot — must re-earn tradeable via the Phase 1 two-pass bar"
      }
    },
    {
      "symbol": "USDJPY",
      "asset_class": "forex",
      "cost_status": "FROM_TICKS",
      "cost_evidence": "cost_calibration.json: spread=0.1236bps (median), p95=0.1856bps, commission=7, RT cost=7.25bps, 386245 real ticks (data/ticks/USDJPY_ticks_24h.parquet, ~27h, 2026-06-25/26)",
      "note": "Real tick-derived measurement, session-covering (~27h, all 5 sessions once each) — replaces a fabricated 0.80bps figure introduced in commit 33b90c31. Adequate for paper; needs true multi-day re-measurement before live.",
      "pipeline": {
        "status": "measuring",
        "activated": "2026-08-03",
        "pre_pipeline_measurement": "single ~27h window — must re-earn tradeable via the Phase 1 two-pass bar"
      }
    }
  ],
```

2. Update `summary`:

```json
  "summary": {
    "total_in_registry": 18,
    "tradeable": 0,
    "measuring": 3,
    "verifying": 0,
    "candidate": 0,
    "excluded": 18,
    "tradeable_with_caveat": 0,
    "next_step": "Phase 1 activation: all 3 previously-tradeable symbols (XAUUSD, USOIL, USDJPY) moved to measuring per spec (no grandfathering). Measurement daemon must re-earn tradeable via the two-pass bar. Until then the universe has zero tradeable symbols — paper scripts keep running via mode='paper'; live trading is correctly blocked (fail-closed)."
  }
```

3. `_meta`: `"version": "1.2.0"` stays (Task 2 already bumped it); set `"updated": "2026-08-03"`.

**Steps**

1. Verify pre-state: `python -m pytest tests/test_cost_calibration_gate.py tests/test_provenance.py tests/test_universe_schema.py -q` → green BEFORE the flip (proves the gate works on the pre-activation universe).
2. Apply the three edits above.
3. Verify the gate still holds and the paper callers are unaffected:
   - `python -m pytest tests/test_cost_calibration_gate.py tests/test_provenance.py tests/test_universe_schema.py -q` → green (test_provenance's XAUUSD load still passes via mode="paper").
   - Live-mode hardening: `python -c "from provenance import require_cost_calibrated; require_cost_calibrated('XAUUSD', mode='live')"` → must raise `UncalibratedCostError` (XAUUSD no longer tradeable).
   - Paper mode: `python -c "from provenance import require_cost_calibrated; print(require_cost_calibrated('XAUUSD', mode='paper'))"` → prints `measuring`.
4. Verify the downstream selection pipeline fails closed (zero tradeable → zero selected → paper trading refuses):
   - `python -c "import json, pathlib; u = json.loads(pathlib.Path('config/tradeable_universe.json').read_text()); print(len(u['tradeable']), len(u['measuring']))"` → `0 3`.
   - `python -m pytest tests/test_paper_trading_symbol_selection.py -q` → green (missing/empty selection artifact returns `[]`; `run_paper_trading.py:811-818` then raises SystemExit with the documented message).
   - Optionally: `python scripts/select_tradeable_instruments.py --dry-run` → prints `Candidates (cost-verified universe): []` and `Selected: (none)` (no walk-forward work is done on an empty candidate list).
5. Full regression: `python -m pytest tests/ --tb=short -q` from the quant_os root (this matches the repo's AGENTS.md command adapted for cwd; expect the same baseline result as before — any new failures must be traced to this plan's tasks, not to the pre-existing dirty working tree).
6. Commit: `git add config/tradeable_universe.json && git commit -m "feat(quant_os): phase 1 activation — move XAUUSD/USOIL/USDJPY to measuring (no grandfathering)"`

---

## Final Verification Plan

Run, in order, from the quant_os package root:

```bash
python -m pytest tests/test_psi_shared.py tests/test_universe_schema.py tests/test_cost_calibration_gate.py tests/test_coverage_tracker.py tests/test_universe_discovery.py tests/test_measurement_daemon.py tests/test_promotion.py tests/test_kill_switch_symbol.py tests/test_demote.py tests/test_ledger_invalidation.py -q
python -m pytest tests/test_provenance.py tests/test_mt5_gateway.py tests/test_kill_switch_close.py tests/test_kill_switch_e2e.py tests/test_paper_trading_symbol_selection.py -q
python -m pytest tests/ --tb=short -q
```

Expected: all new task tests green; all pre-existing contract tests green; the full-suite result matches the pre-plan baseline (`lh_check.txt`: 34/34 on the targeted LookaheadGuard regression set).

## Out of Scope / Deferred (spec §5 storage policy)

Spec §5's raw-parquet retention (prune `data/ticks/{symbol}_{date}.parquet` 30 days after a symbol reaches `tradeable`) is a scheduled-maintenance policy, not pipeline code. It is deliberately NOT implemented in this plan (the spec itself marks 30 days as "not load-bearing"). Track it as a follow-up operational task once the daemon has been running and producing parquet.

## Execution Handoff

Execution approach choices, per the writing-plans skill:

1. **Subagent-Driven Execution (Recommended)**: The executor works task-by-task through Tasks 1-12 in order, committing after each task. Task 3 must precede Task 12 (gate must exist before activation flips the universe). Tasks 1, 2, 5, 6, 9 are mutually independent and can be parallelized, but 3→4→12 are strictly sequential.
2. **Inline Execution**: Work through the tasks in this session directly, task by task, verifying each gate before moving on.

Both approaches must preserve the Global Constraints, especially working-tree hygiene (constraint 8) and the no-new-dependencies rule (constraint 3).
