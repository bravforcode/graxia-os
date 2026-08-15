# ENGINE BUG — equity_curve never appended with Phase-4 pnl_tracker → sharpe/maxDD silently 0.0

**Status:** CONFIRMED + runner-side workaround (2026-08-06); engine-side fix REQUIRED
**Severity:** HIGH — silently corrupts risk-adjusted metrics for EVERY BacktestEngine run using default config
**Affects:** All engine.run() consumers (screening, trials, runners) when `_PHASE4_WIRING_AVAILABLE` is True

---

## 🚨 NOTICE TO PARALLEL SESSION (bravforcode)

This bug was introduced by the Phase-4 wiring (`RealTimePnLTracker` / `_PHASE4_WIRING_AVAILABLE` block). **Trial 9003 (EURUSD H4) and any Direction H/G trials run with current engine code may have sharpe/maxDD = 0.0 — verify before relying on those verdicts.** The runner-side workaround below is in `scripts/run_screening.py`; an engine-side fix (append equity in the tracker branch) is recommended before P6 trials.

---

## 1. Symptom

- `results["metrics"].sharpe_ratio == 0.0` AND `max_drawdown_pct == 0.0` EXACTLY, regardless of trade count or PnL
- Example (reproduced): XAUUSD M15, 2,440 trades, profit_factor 0.95, total_return **-36.6%** → sharpe 0.0, maxDD 0.0

## 2. Root cause (verified by source trace + runtime)

`backtest/engine.py` run() per-bar loop (Phase 4 section):
```python
unrealized = self._calculate_unrealized_pnl(float(bar_close))
if self._pnl_tracker:
    self._pnl_tracker.update_tick(Decimal(str(unrealized)), float(i))
    self.equity = self._pnl_tracker.equity
else:
    self._update_equity(float(bar_close), current_time)   # ← ONLY branch that appends equity_curve
```
- `self.equity_curve.append(EquityPoint(...))` exists ONLY inside `_update_equity()` (engine.py ~59068)
- `_pnl_tracker` is set in run()'s reset block (engine.py ~27093): `if _PHASE4_WIRING_AVAILABLE: ... self._pnl_tracker = RealTimePnLTracker(...)` — **re-created on every run(), so any pre-run assignment is wiped**
- `_PHASE4_WIRING_AVAILABLE = True` whenever `risk/realtime_pnl.py` + `validation/regime_detector.py` + `execution/margin_simulator.py` import cleanly (they do)
- Result: tracker branch always taken → `equity_curve` stays `[]` → `calculate_metrics` risk-adjusted block (`if equity_curve and len(equity_curve) > 1`) skipped → sharpe/sortino/max_drawdown_pct stay at dataclass defaults (0.0)
- Trade-derived metrics (total_trades, profit_factor, total_return_pct) are UNAFFECTED — which is why the corruption is silent

## 3. Evidence

| Check | Result |
|---|---|
| `engine.equity_curve` after run() | `len == 0` (trades: 2,440) |
| `vars(metrics)` keys | `sharpe_ratio`, `max_drawdown_pct` present, both 0.0 |
| `_extract_returns(equity_curve)` | never reached (empty input) |
| append call site | only in `_update_equity`, which is only reached via the `else` branch |
| `_pnl_tracker` re-creation | run() reset block, unconditional when `_PHASE4_WIRING_AVAILABLE` |

## 4. Runner-side workaround (applied, committed `39105ce3`)

`scripts/run_screening.py main()`:
```python
bt_engine._PHASE4_WIRING_AVAILABLE = False
```
Verified: XAUUSD D1 2y — sharpe **0.366** (was 0.0), maxDD **14.28%** (was 0.0), PF 1.235, survivor=True.

## 5. Recommended engine-side fix (owner: engine maintainers / parallel session)

In run() per-bar loop, append the EquityPoint in BOTH branches (or make `_update_equity` the single source and have the tracker path call it after updating self.equity). E.g.:
```python
if self._pnl_tracker:
    self._pnl_tracker.update_tick(...)
    self.equity = self._pnl_tracker.equity
self._update_equity(float(bar_close), current_time)   # always record
```
With regression test: run a strategy with >30 trades, assert `len(engine.equity_curve) > 0` and `metrics.sharpe_ratio != 0.0`.

## 6. Impact inventory (must-check before P6 trials)

- Direction G trials (8001-8003): verdicts reported non-zero Sharpe — verify they ran pre-Phase-4 or with the flag off; if not, re-check their metrics
- Direction H trial 9003 (EURUSD H4, current): **VERIFY sharpe/maxDD before relying on the verdict**
- All future P6 trials: MUST apply the workaround or the engine fix
- TSM jackknife rerun (17c199b4): used scripts/tsm_portfolio.py (own computation) — unaffected

## 7. Logged

- openwolf_buglog / ctx_knowledge: `bug-engine-equity-curve-pnl-tracker` (2026-08-06)
