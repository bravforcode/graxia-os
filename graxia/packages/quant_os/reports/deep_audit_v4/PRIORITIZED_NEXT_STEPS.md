# PRIORITIZED NEXT STEPS
**Phase 27 | 2026-07-06 | TIER 1 | [UPDATED — Post-13-Fix v4.0]**

Items that were completed in the v4.0 fix pass (2026-07-05 to 2026-07-06) are marked ✅ COMPLETED. Remaining items re-prioritized based on post-fix reality.

---

## ✅ COMPLETED (2026-07-05 to 2026-07-06)

| # | Item | Date | Evidence |
|---|------|------|----------|
| 4 | Remove credentials file from repo | 2026-07-05 | `Meta/pepperstone_creds.txt` deleted; `.gitignore` updated |
| 2 | Fix ensemble `_consensus_levels()` returns (None, None) | 2026-07-05 | `ensemble.py:441-496` — weighted-average SL/TP + ATR-based fallback |
| n/a | Add pre-trade gate SL check | 2026-07-05 | `pre_trade_risk.py:59` — rejects orders without stop-loss |
| n/a | Add execution manager defensive SL check | 2026-07-05 | `manager.py:276` — checks stop_price before broker submission |
| n/a | Fix portfolio exposure cap (3× combined risk) | 2026-07-05 | `position_sizer_v2.py:57-81` — `max_portfolio_exposure_pct` cap |
| n/a | Fix P&L unit bug (multiply by contract_size) | 2026-07-05 | `backtest/engine.py:1099-1103` — `* contract_size` in P&L calc |
| 3 | Fix hardcoded 2350.0 in walk_forward.py | 2026-07-05 | `walk_forward.py:108` — uses `np.mean(closes_masked)`; Sharpe × √(252×1440) |
| 5 | Wire swap_cost module into backtest pipeline | 2026-07-05 | `backtest/engine.py:1078-1140` — `_calculate_swap_cost()` integrated |
| n/a | Fix volume_max check | 2026-07-05 | `position_sizer_v2.py:190-194` — caps rounded volume at volume_max |
| n/a | Fix auto_retrain dummy evaluation | 2026-07-05 | `auto_retrain.py` — real model evaluation replaces hardcoded 1.0 |
| n/a | Fix n_jobs=-1 non-deterministic training | 2026-07-05 | All training scripts: `n_jobs=1`, `deterministic=True` |
| 1 | Fix KNOWN_LIMITATIONS.md R20 contradiction | 2026-07-05 | `KNOWN_LIMITATIONS.md:3` — clarifies deprecated vs. canonical adapter |
| n/a | Wire DriftMonitor into auto_retrain flow | 2026-07-05 | `auto_retrain.py:251-273` — DriftMonitor check before retrain |
| n/a | Delete `Meta/pepperstone_creds.txt.backup` | 2026-07-05 | Security cleanup |

---

## P0 — HARD BLOCKER (Must be resolved before ANY trading)

### ITEM 1: Compute Full-Pipeline Label Shuffling Test
- **Priority:** P0 (was P1 — elevated)
- **Triggered by:** Phase 13.1, 24.4
- **Current state:** `test_label_shuffling_actual_data.py` uses proxy `_compute_sharpe()` — not full backtest replay
- **Required state:** 100+ permutations through FULL pipeline: features → signals → backtest with fill/cost/sizing → Sharpe
- **Why P0:** Without this, we cannot rule out "all signal is noise." The single most important validation for any ML-based strategy.
- **Estimated complexity:** High (2-3 days)

### ITEM 2: Produce One Clean Walk-Forward Run on the Fixed Engine
- **Priority:** P0
- **Triggered by:** Phase 24.3, P&L fix, cost fix
- **Current state:** Prior walk-forward results are INVALID (wrong P&L, wrong costs, wrong SL/TP)
- **Required state:** A single walk-forward run on XAUUSD with the fixed engine producing: OOS Sharpe, DSR, PBO, 95% CI
- **Why P0:** This IS the evidence. Everything else is ceremony. If the fixed-engine walk-forward shows negative OOS Sharpe (as EXP-001 suggests), the project needs a strategy pivot.
- **Estimated complexity:** Medium (2-4 hours)

### ITEM 3: Delete `Meta/pepperstone_creds.txt.backup` and Rotate Password
- **Priority:** P0 (security)
- **Triggered by:** Phase 20.1
- **Current state:** Backup file still on disk; password `Graxia-12345` is compromised
- **Required state:** File deleted; credentials rotated on Pepperstone portal; stored ONLY in .env
- **Falsification:** No `pepperstone` or `Graxia-12345` in git history or filesystem
- **Estimated complexity:** Low (15 min)

---

## P0 — NEW (Discovered during v4.0 Audit)

### ITEM 4: Implement SPRT/CUSUM Live Performance Monitoring
- **Priority:** P0
- **Triggered by:** Phase 22.1
- **Current state:** No sequential testing; cannot distinguish drawdown from edge decay
- **Required state:** SPRT with H0: Sharpe ≤ 0, α=0.05, β=0.20 monitoring live P&L
- **Estimated complexity:** Medium (1 day)

### ITEM 5: Define Pre-Committed Live Stopping Rule
- **Priority:** P0
- **Triggered by:** Phase 22.2
- **Current state:** Risk gates exist (15% DD, 3 consecutive losses) but no statistical stopping rule
- **Required state:** Written rule: "After N trades with observed Sharpe < X at 90% CI, stop permanently"
- **Estimated complexity:** Low (requires agreeing on N and X — 30 min)

### ITEM 6: Create Pre-Start Checklist in RUNBOOK.md
- **Priority:** P0
- **Triggered by:** Phase 23.1
- **Current state:** RUNBOOK.md has start commands but no pre-flight checklist
- **Required state:** Checklist: (1) verify `live_trading_enabled=False`, (2) verify MT5 terminal running, (3) verify broker connection, (4) verify kill switch state is INACTIVE, (5) verify no existing positions
- **Estimated complexity:** Low (30 min)

### ITEM 7: Implement Instance Lock (pidfile)
- **Priority:** P0
- **Triggered by:** Phase 23.3
- **Current state:** No duplicate-bot prevention — two instances on same MT5 account = double orders
- **Required state:** pidfile or mutex that prevents second instance from starting
- **Estimated complexity:** Low (30 min)

---

## P1 — PAPER TRADING BLOCKER

### ITEM 8: Collect Sufficient M1 Historical Data (6+ months)
- **Priority:** P1
- **Triggered by:** Phase 0.13
- **Current state:** ~5,000 M1 rows (3-6 days) per instrument
- **Required state:** 75,000+ bars per instrument for ML training
- **Estimated complexity:** Medium (data download + storage)

### ITEM 9: Independent Feed Cross-Validation
- **Priority:** P1
- **Triggered by:** Phase 2
- **Current state:** Single data source (MT5)
- **Required state:** Compare MT5 OHLCV against a second source (e.g., Dukascopy, IB) for at least 1 instrument
- **Estimated complexity:** Medium (requires second data source)

### ITEM 10: Verify Feature Computation Parity (Backtest vs. Live)
- **Priority:** P1
- **Triggered by:** Phase 8.1
- **Current state:** Standard indicators diverge (batch in backtest, rolling in live); SMC detectors shared
- **Required state:** Unit test verifying same input vectors produce same feature values in both paths
- **Estimated complexity:** Medium

---

## P2 — LIVE CAPITAL BLOCKER

### ITEM 11: Apply Multiple-Testing Correction
- **Priority:** P2
- **Triggered by:** Phase 5.3, 24.1
- **Current state:** ~300 hypotheses, zero corrections
- **Required state:** BH-FDR applied to all p-values; corrected significance thresholds for all future tests
- **Estimated complexity:** Medium (requires hypothesis log)

### ITEM 12: Compute DSR/PBO
- **Priority:** P2
- **Triggered by:** Phase 7, 24
- **Current state:** DSR not computed
- **Required state:** Deflated Sharpe Ratio < 1.0 for all reported strategies (meaning results could be from noise)
- **Estimated complexity:** Medium

### ITEM 13: Run Tail-Event Stress Replay
- **Priority:** P2
- **Triggered by:** Phase 12
- **Current state:** SNB 2015, Brexit 2016 not in backtest window; no liquidity-vacuum scenario tested
- **Required state:** Replay 2+ tail events through complete pipeline; document drawdown
- **Estimated complexity:** High

### ITEM 14: Wire AlertEngine into Live Trading Loop
- **Priority:** P2
- **Triggered by:** Phase 21.3
- **Current state:** AlertEngine exists; not proven wired to `core/trading_loop.py`
- **Required state:** `check_alerts(system_state)` called per loop iteration
- **Estimated complexity:** Medium

### ITEM 15: Add NaN/Inf Guards in Strategy Indicators
- **Priority:** P2
- **Triggered by:** Phase 21.2
- **Current state:** `pandas_ta` can propagate NaN silently; no guard in `_calculate_indicators()`
- **Required state:** NaN/Inf detection with CRITICAL log + signal rejection
- **Estimated complexity:** Low (1 hour)

---

## P3 — QUALITY IMPROVEMENT

### ITEM 16: Consolidate Three Overlapping Heartbeat Systems
- **Priority:** P3
- **Current state:** `dead_mans_switch.py`, `health_check.py`, `heartbeat_monitor.py` — 3 different timeouts, 3 escalation paths
- **Required state:** One canonical heartbeat system
- **Estimated complexity:** Medium

### ITEM 17: Consolidate Broker Adapter Implementations
- **Priority:** P3
- **Current state:** `execution/broker_adapter.py` (deprecated) + `execution/adapters/mt5.py` (canonical)
- **Required state:** Delete deprecated adapter
- **Estimated complexity:** Medium

### ITEM 18: Wire ModelRegistry into Training Pipeline
- **Priority:** P3
- **Current state:** `ml/model_registry.py` (385 lines) exists but never called from any training script
- **Required state:** Training scripts call `ModelRegistry.register_model()` with content hash
- **Estimated complexity:** Medium

### ITEM 19: Clean Research Artifacts
- **Items discovered during audit:**
  1. `scripts/research_approaches.py` has 4 instances of `* 2350` hardcoded
  2. `scripts/backtest_cost.py` has 3 instances of 2350.0 fallback
  3. `data/kill_switch_corrupt_test.corrupt.*.json` — test artifact in data directory
  4. `docker-compose.yml` has default postgres password
  5. 37 unversioned model files in `ml/models/`

### ITEM 20: Extend RUNBOOK.md
- Add: pre-start checklist, crash-with-position-open procedure, credential rotation, dependency update, resource profile, weekend shutdown procedure

---

## Summary

| Priority | Count | Status |
|----------|-------|--------|
| ✅ COMPLETED | 14 | Fixed in v4.0 fix pass |
| P0 (remaining hard blocker) | 7 | 3 original, 4 new discoveries |
| P1 (paper trading blocker) | 3 | — |
| P2 (live capital blocker) | 5 | — |
| P3 (quality improvement) | 5 | — |

**The 13 P0 fixes eliminated the most dangerous code-level bugs. The remaining P0 items are methodology gaps: no verified edge, no statistical monitoring, no operational safety procedures. Every hour spent on code fixes that don't produce OOS evidence is an hour wasted — the SINGLE most important next step is ITEM #2: one clean walk-forward run.**
