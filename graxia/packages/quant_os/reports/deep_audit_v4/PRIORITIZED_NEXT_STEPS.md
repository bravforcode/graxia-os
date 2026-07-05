# PRIORITIZED NEXT STEPS
**Phase 27 | 2026-07-05 | TIER 1**

---

## P0 — HARD BLOCKER (System must not run until resolved)

### ITEM 1: Fix KNOWN_LIMITATIONS.md R20 Contradiction
- **Priority:** P0
- **Triggered by:** Phase 0.11 finding
- **Current state:** Document says "MT5 gateway is read-only stub" — false for canonical adapter
- **Required state:** Document accurately reflects that `execution/adapters/mt5.py` is live-capable
- **Concrete next action:** Open `KNOWN_LIMITATIONS.md`, line 1. Change to: "MT5 gateway (`broker/mt5_gateway.py`) is read-only. The canonical adapter (`execution/adapters/mt5.py:MT5Adapter`) is live-capable when `config.live_trading_enabled=True`."
- **Falsification:** Read the file and confirm it matches code reality
- **Estimated complexity:** Low (5 min)

### ITEM 2: Fix Ensemble _consensus_levels() Returns (None, None)
- **Priority:** P0
- **Triggered by:** Phase 14.7 finding
- **Current state:** `strategies/ensemble.py:432-433` returns `(None, None)` for SL/TP
- **Required state:** Returns valid SL/TP levels derived from sub-strategy signals
- **Concrete next action:** Open `strategies/ensemble.py`, implement `_consensus_levels()` to compute weighted-average SL/TP from votes. Minimum: use the SL/TP from the highest-weighted winning vote.
- **Falsification:** Unit test that calls `_consensus_levels()` with real votes and asserts non-None SL/TP
- **Estimated complexity:** Medium (1-2 hours)

### ITEM 3: Fix Hardcoded 2350.0 in Walk-Forward Cost Calculation
- **Priority:** P0
- **Triggered by:** Phase 3.8 finding
- **Current state:** `scripts/walk_forward.py:88` has `price_mult = 2350.0` used in cost calc
- **Required state:** Cost calculation uses actual close prices
- **Concrete next action:** Open `scripts/walk_forward.py`, line 88. Remove `price_mult = 2350.0` and change line 91 to: `cost_per_dollars = (spread_cost + slippage_p90) * np.mean(closes_masked)` (or use per-bar close prices for cost)
- **Falsification:** Run walk-forward on XAUUSD and EURUSD; verify costs scale with actual price
- **Estimated complexity:** Low (30 min)

### ITEM 4: Remove Credentials File from Repo
- **Priority:** P0
- **Triggered by:** Phase 20.1 finding
- **Current state:** `Meta/pepperstone_creds.txt` exists in repo (185 bytes)
- **Required state:** File removed, credentials rotated, .gitignore updated
- **Concrete next action:**
  1. `git rm Meta/pepperstone_creds.txt`
  2. Add `Meta/pepperstone_creds.txt` to `.gitignore`
  3. Rotate Pepperstone credentials (change password on broker portal)
  4. Check git history for any previously committed secrets
- **Falsification:** `git log --all --full-history -- Meta/pepperstone_creds.txt` shows no accessible content
- **Estimated complexity:** Medium (30 min + broker portal)

---

## P1 — PAPER TRADING BLOCKER

### ITEM 5: Wire Swap Cost Module into Backtest Pipeline
- **Priority:** P1
- **Triggered by:** Phase 0.10 (orphaned module), Phase 9.9
- **Current state:** `core/risk/swap_cost.py` exists but never called from backtest
- **Required state:** Backtest subtracts swap costs for overnight positions
- **Concrete next action:** In `backtest/engine.py:_close_position()`, import and call `get_swap_cost_for_trade()` for positions held past 21:00 UTC
- **Falsification:** Run backtest with a strategy that holds overnight; verify swap cost appears in trade fees
- **Estimated complexity:** Medium (2-3 hours)

### ITEM 6: Collect Sufficient M1 Historical Data
- **Priority:** P1
- **Triggered by:** Phase 0.13
- **Current state:** All instruments have ~5,000 M1 rows (3-6 days)
- **Required state:** Minimum 6 months (~75,000 bars) per instrument for ML training
- **Concrete next action:** Run `scripts/download_mt5.py` or equivalent to pull 6+ months of M1 data for all 15 instruments
- **Falsification:** `wc -l data/*_M1.csv` shows >75,000 for each instrument
- **Estimated complexity:** Medium (data download + storage)

### ITEM 7: Run Label-Shuffling Test on Actual Strategy Data
- **Priority:** P1
- **Triggered by:** Phase 13.1
- **Current state:** `tests/test_label_shuffling.py` uses synthetic random data
- **Required state:** Test runs on actual MTM/MRB/MLB strategy features and labels
- **Concrete next action:** Modify test to load real feature data from `artifacts/features_v2/` and run 100+ permutations
- **Falsification:** Test output shows real Sharpe vs null distribution with p-value
- **Estimated complexity:** Medium (1-2 hours)

### ITEM 8: Fix Sharpe Annualization Factor
- **Priority:** P1
- **Triggered by:** Phase 3.3
- **Current state:** `walk_forward.py:109` uses `sqrt(252 * 390)` — equity market hours
- **Required state:** Use `sqrt(252 * 1440)` for FX (24h), or instrument-specific factor
- **Concrete next action:** Open `scripts/walk_forward.py`, line 109. Change to use configurable `bars_per_day` parameter.
- **Falsification:** Sharpe ratios are ~1.93× higher for FX instruments (conservative correction)
- **Estimated complexity:** Low (15 min)

---

## P2 — LIVE CAPITAL BLOCKER

### ITEM 9: Trace Ensemble Signal Through Live Execution Path
- **Priority:** P2
- **Triggered by:** Phase 14.7
- **Current state:** Unknown whether `SL=None` from ensemble results in order rejection or no-SL order
- **Required state:** Confirmed behavior — ideally order rejection
- **Concrete next action:** Trace `core/orchestrator.py` → `TradingLoop` → `OMS.submit_order()` and confirm what happens when `signal.stop_loss is None`
- **Falsification:** Code trace showing exact behavior
- **Estimated complexity:** Medium (1 hour)

### ITEM 10: Compute Walk-Forward for All 15 Instruments
- **Priority:** P2
- **Triggered by:** Phase 7.9
- **Current state:** Walk-forward only validated for XAUUSD/EURUSD
- **Required state:** OOS Sharpe with CI for all 15 instruments
- **Concrete next action:** Run `scripts/walk_forward.py --symbol <SYM>` for each unvalidated instrument
- **Falsification:** Table in `BACKTEST_VALIDATION_INTEGRITY.md` fully populated
- **Estimated complexity:** High (data collection + compute time)

### ITEM 11: Apply Multiple-Testing Correction
- **Priority:** P2
- **Triggered by:** Phase 5.3, Phase 24.1
- **Current state:** No Bonferroni/BH-FDR correction applied
- **Required state:** All reported p-values corrected for total hypothesis count
- **Concrete next action:** Count total hypotheses tested; apply BH-FDR to all p-values
- **Falsification:** Corrected p-values reported alongside raw
- **Estimated complexity:** Medium (requires hypothesis log)

---

## P3 — QUALITY IMPROVEMENT

### ITEM 12: Consolidate Broker Adapter Implementations
- **Priority:** P3
- **Current state:** Two implementations: `execution/broker_adapter.py` (deprecated, async) and `execution/adapters/` (canonical, sync)
- **Required state:** Single canonical implementation
- **Estimated complexity:** High

### ITEM 13: Wire Regime Detector into Live Path
- **Priority:** P3
- **Current state:** `core/regime_detector.py` wired in backtest only
- **Estimated complexity:** Medium

### ITEM 14: Implement Cross-Asset Correlation Matrix
- **Priority:** P3
- **Current state:** No correlation matrix for 15 instruments
- **Estimated complexity:** Medium

---

## NEW ITEMS DISCOVERED DURING AUDIT

1. **`scripts/research_approaches.py`** has 4 instances of `* 2350` hardcoded — same bug class as walk_forward
2. **`scripts/backtest_cost.py`** has 3 instances of 2350.0 fallback — needs same fix
3. **Walk-forward Sharpe factor** uses equity-market hours (390) instead of FX hours (1440)
4. **`config/telegram_config.toml`** likely contains bot tokens — needs secrets audit
5. **`data/kill_switch_corrupt_test.corrupt.*.json`** — test artifact in data directory, should be cleaned
