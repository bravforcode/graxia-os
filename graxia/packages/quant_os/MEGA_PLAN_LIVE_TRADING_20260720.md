# MEGA PLAN — Quant OS Live Trading Readiness

**Date:** 2026-07-20 | **Version:** 1.0 | **Status:** `NO_GO` → `PASS_TO_NEXT_PHASE`
**Evidence Base:** 35+ audit documents, 6 parallel deep-dives, 3 trial ledgers
**Constitution:** INV-001 through INV-013 enforced throughout

---

## 🔴 EXECUTIVE VERDICT — NOT READY

| # | Blocker | Evidence | Severity |
|---|---------|----------|----------|
| 1 | No proven edge — All 33 trials REJECTED | `CONSTITUTION.md:98` | CRITICAL |
| 2 | STOPPING RULE triggered — 4 consecutive failures | `CONSTITUTION.md:98` | CRITICAL |
| 3 | 13 P0 infrastructure bugs | `AUDIT_INDEX.md:23-25` | CRITICAL |
| 4 | Cost baseline unreliable (33x disagreement) | `READINESS_VERIFIED.md:49-53` | CRITICAL |
| 5 | Paper trading not started (0/60 days) | `READINESS_VERIFIED.md:112` | CRITICAL |

---

## PLAN STRUCTURE

```
PHASE 0A (2 wks) → PHASE 0B (1 wk) → DECISION GATE → PHASE 1 (3 wks) → PHASE 2 (9 wks) → PHASE 3 (2 wks)
   Edge Disc.       Spread Meas.      GO/NO-GO       Fix P0 Blckrs    Paper Trading    Live Gates
```

**MUST stop at Decision Gate if edge not proven. No sunk-cost fallacy.**

---

## 📊 EVIDENCE BASELINE — Every Trial Ever Run

### Direction A — Single-Asset Technical (29 trials, ALL REJECTED)

| Trial | Strategy | Metric | Instrument | Verdict | Source |
|-------|----------|--------|------------|---------|--------|
| 1001 | RYDC Arm A | p=0.968 | XAUUSD | REJECTED | CONSTITUTION.md:92 |
| 1003 | Cross-Asset Momentum | p=0.598 | XAUUSD | REJECTED | CONSTITUTION.md:93 |
| 1004 | Session Pattern | p=0.934 | XAUUSD | REJECTED | CONSTITUTION.md:94 |
| 1005 | Macro Regime MR | p=0.244 | XAUUSD | REJECTED | CONSTITUTION.md:95 |
| 1006 | Gold-Silver Spread | p=0.505 | XAUUSD/XAGUSD | REJECTED | CONSTITUTION.md:96 |
| 1007 | BTC Vol Clustering | p=0.248 | BTCUSD | REJECTED | READINESS_VERIFIED.md:29 |
| 1008 | Cross Asset Vol Rank | p=0.610 | BTCUSD | REJECTED | READINESS_VERIFIED.md:30 |
| 1009-1021 | gold_ict_batch (13) | dk_t=0.52 | XAUUSD | REJECTED | trial_ledger.json |
| RSI_20_80 | RSI 20/80 | dk_t=-0.22 | Pooled 7 | REJECT | EDGE_SEARCH_FINAL:33 |
| RSI_30_70 | RSI 30/70 | dk_t=-0.36 | Pooled 7 | REJECT | EDGE_SEARCH_FINAL:34 |
| RSI_25_75 | RSI 25/75 | dk_t=-0.82 | Pooled 7 | REJECT | EDGE_SEARCH_FINAL:47 |
| Mom252 | Momentum12M_252 | dk_t=-0.39 | Pooled 7 | REJECT | EDGE_SEARCH_FINAL:35 |
| Mom126 | Momentum12M_126 | dk_t=-0.52 | Pooled 7 | REJECT | EDGE_SEARCH_FINAL:40 |
| HMR20 | HybridMomMR_20 | dk_t=-0.41 | Pooled 7 | REJECT | EDGE_SEARCH_FINAL:36 |
| HMR60 | HybridMomMR_60 | dk_t=-0.42 | Pooled 7 | REJECT | EDGE_SEARCH_FINAL:37 |
| DC10 | Donchian_10 | dk_t=-0.61 | Pooled 7 | REJECT | EDGE_SEARCH_FINAL:44 |
| DC20 | Donchian_20 | dk_t=-0.75 | Pooled 7 | REJECT | EDGE_SEARCH_FINAL:45 |
| DC55 | Donchian_55 | dk_t=-0.59 | Pooled 7 | REJECT | EDGE_SEARCH_FINAL:42 |
| DCAX | DonchianADX_10_25 | dk_t=-0.53 | Pooled 7 | REJECT | EDGE_SEARCH_FINAL:41 |
| BSQZ | BollingerSqueeze | dk_t=-0.60 | Pooled 7 | REJECT | EDGE_SEARCH_FINAL:43 |
| LS | LiquiditySweep | dk_t=-0.52 | Pooled 7 | REJECT | EDGE_SEARCH_FINAL:39 |
| VB15 | VolumeBreakout_1.5 | dk_t=-0.77 | Pooled 7 | REJECT | EDGE_SEARCH_FINAL:46 |
| VB20 | VolumeBreakout_2.0 | dk_t=-0.49 | Pooled 7 | REJECT | EDGE_SEARCH_FINAL:38 |
| MRB | MeanReversionBollinger | NO SIGNALS | — | UNTESTABLE | EDGE_SEARCH_FINAL:48 |
| MTM | MultiTimeframeMomentum | NO SIGNALS | — | UNTESTABLE | EDGE_SEARCH_FINAL:49 |

### Label-Shuffle Confirmation (Noise Proof)

| Case | OOS Sharpe | p-value | Verdict | Source |
|------|------------|---------|---------|--------|
| Donchian_10 XAUUSD | +0.14 | 0.375 | NO_EDGE | EDGE_SEARCH_FINAL:77 |
| Donchian_20 XAUUSD | +0.18 | 0.345 | NO_EDGE | EDGE_SEARCH_FINAL:78 |
| Donchian_55 NAS100 | -0.18 | 0.740 | NO_EDGE | EDGE_SEARCH_FINAL:79 |
| Momentum126 NAS100 | +0.48 | 0.255 | NO_EDGE | EDGE_SEARCH_FINAL:80 |
| Hybrid60 NAS100 | +0.33 | 0.295 | NO_EDGE | EDGE_SEARCH_FINAL:81 |

### Direction B — Path B: Macro/Cross-Asset (4 trials, ALL REJECTED)

| Trial | Strategy | dk_t | Pooled Sharpe | Verdict | Source |
|-------|----------|------|---------------|---------|--------|
| 3001 | PATHB-CARRY-XAUUSD | -0.977 | -0.869 | REJECTED | trial_ledger_b.json |
| 3002 | PATHB-VRP-XAUUSD | -1.101 | -0.979 | REJECTED | trial_ledger_b.json |
| 3003 | PATHB-CAM-XAUUSD | +0.057 | +0.051 | REJECTED | trial_ledger_b.json |
| 3004 | PATHB-DXY-DIV-XAUUSD | -1.433 | -1.275 | REJECTED | trial_ledger_b.json |

### Forex Investigation

| Symbol | Trades | Net PnL | t-stat | Verdict | Source |
|--------|--------|---------|--------|---------|--------|
| GBPUSD | 3,388 | -$1.42 | -8.77 | REJECT | FOREX_EDGE_INVESTIGATION:20 |
| USDJPY | 3,529 | -$161 | -8.57 | REJECT | FOREX_EDGE_INVESTIGATION:21 |
| USDCAD | 1,725 | -$0.11 | -1.69 | INCONCLUSIVE | FOREX_EDGE_INVESTIGATION:22 |
| USDCHF | 2,498 | -$0.10 | -1.12 | INCONCLUSIVE | FOREX_EDGE_INVESTIGATION:23 |
| AUDUSD | 5,281 | -$0.13 | -1.55 | INCONCLUSIVE | FOREX_EDGE_INVESTIGATION:24 |
| NZDUSD | 5,599 | -$0.04 | -0.53 | INCONCLUSIVE | FOREX_EDGE_INVESTIGATION:25 |

**Total: 33 trials, ALL REJECTED. ~25 trial IDs remaining.**

---

## 🔧 P0 BLOCKER INVENTORY (13 items)

| ID | Issue | File:Line | Live Block? |
|----|-------|-----------|-------------|
| P0-B1 | SL/TP uses bar midpoint, not high/low | execution/fill_model.py:67-87 | YES |
| P0-B2 | Swap costs NEVER applied in backtest | backtest/engine.py:890-905 | YES |
| P0-B3 | Kill switch resets on corrupt JSON | risk/kill_switch.py:149-151 | YES |
| P0-B4 | CORS wildcard on signal_service | api/signal_service.py | YES |
| P0-B5 | webhook_receiver imports non-existent module | api/webhook_receiver.py | YES |
| P0-B6 | 3 API keys hardcoded in source | multiple files | YES |
| P0-B7 | MT5 account number in git history | .git history | YES |
| P0-B8 | Real FRED key in .env.example | .env.example | YES |
| P0-B9 | AlertManager drops ALL alerts (empty routing) | monitoring/alerts.py | YES |
| P0-B10 | Pre-trade gate not wired to live orders | execution/manager.py | YES |
| P0-B11 | Crash recovery not wired | execution/position_reconciler.py | YES |
| P0-B12 | auto_retrain returns dummy metrics | scripts/auto_retrain.py | YES |
| P0-B13 | Signal path duplicated (port 8752) | api/signal_service.py | NO (arch) |

---

## PHASE 0A: CROSS-SECTIONAL MOMENTUM EDGE DISCOVERY (2 weeks)

**Goal:** Prove cross-sectional momentum edge with pre-registered parameters
**Hard Gate:** `dk_t > 2.0` AND `positive_sharpe >= 5` AND `label-shuffle p < 0.05`

### Rationale
- Academic evidence: Sharpe 0.45-1.05 (Jegadeesh & Titman 1993, Moskowitz & Grinblatt 1999, Baltas 2019)
- Different mechanism: rank assets relative to each other (not absolute direction)
- Lower cost sensitivity: rebalance every 5 bars vs every bar (weekly vs daily)
- Multi-asset diversification: long 2 winners, avoid 6 losers = natural risk management
- Code EXISTS: `strategies/momentum_factor_rotation.py` (Trial #1013 pre-registered, NOT backtested)

### Pre-registered Parameters (FROZEN from `momentum_factor_rotation.py:47-55`)

```python
lookbacks = (21, 63, 252)    # Multi-timeframe TSMOM (1M, 3M, 12M)
vol_target = 0.10             # Annualized vol scaling target
kappa = 2.0                   # Max vol scaling cap
top_n = 2                     # Long top N assets
bottom_n = 0                  # Long-only (no short)
rebalance_freq = 5            # Rebalance every 5 bars (D1 = weekly)
min_signal_strength = 0.3     # Minimum TSMOM strength to trade
```

### Pre-registered Universe
`XAUUSD, XAGUSD, EURUSD, GBPUSD, USDJPY, NAS100, US30` (7 assets, D1)

### Tasks

**Task 0A.1:** Create edge search script `scripts/edge_search_cross_sectional.py`
- Wire `momentum_factor_rotation.py` into pooled DK-test harness
- Use Pepperstone Razor spreads + $7/rt commission on FX pairs
- Output per-asset and pooled results to JSON

```bash
python scripts/edge_search_cross_sectional.py \
  --universe XAUUSD,XAGUSD,EURUSD,GBPUSD,USDJPY,NAS100,US30 \
  --cost-model pepperstone_razor \
  --dk-test pooled \
  --label-shuffle 200 \
  --output reports/edge_search_cross_sectional_20260720.json
```

**Task 0A.2:** Run edge search and record results

**Task 0A.3:** If GO, register Trial #2001 in `research/hypothesis_registry.json`

**Task 0A.4:** Run sacred holdout ONCE (only if GO on DK + label-shuffle both pass)
```bash
python scripts/holdout_validate.py \
  --trial 2001 \
  --holdout data/sacred_holdout/holdout_fresh_20260717.csv
```

### Acceptance Criteria (ALL must pass for GO)

| Criterion | Threshold | Method |
|-----------|-----------|--------|
| Pooled DK t-stat | > 2.0 | Welch t-test on daily returns vs null |
| Positive Sharpe count | >= 5 of 7 assets | Per-asset OOS Sharpe > 0 |
| Label-shuffle p-value | < 0.05 | 200 shuffles, OOS Sharpe percentile |
| Minimum trades | > 200 total | >= 1 trade per asset per year |
| Realistic costs applied | Pepperstone spread + $7/rt FX commission | Every trade in DK test |

### Evidence Artifacts
```
reports/edge_search_cross_sectional_20260720.json      (Full results)
reports/edge_search_cross_sectional_20260720.md        (Human-readable)
reports/label_shuffle_cross_sectional_20260720.json    (Label-shuffle)
reports/holdout_validation_2001_20260720.json           (Sacred holdout)
```

### Go / No-Go / Marginal Decision

| Result | Action |
|--------|--------|
| **GO** (all criteria met) | Register Trial #2001, proceed to Phase 0B |
| **MARGINAL** (dk_t 1.0-2.0, some criteria met) | Document as `INSUFFICIENT_SAMPLE`, do NOT burn holdout |
| **REJECT** (dk_t < 1.0) | `ARCHIVE_NO_EDGE` — STOP entire plan |

---

## PHASE 0B: SPREAD MEASUREMENT + COST BASELINE (1 week, parallel with 0A review)

**Goal:** Reliable multi-session spread baseline for XAUUSD (and other metals)

```bash
python scripts/measure_spread_continuous.py \
  --symbols XAUUSD \
  --duration-days 7 \
  --output-dir data/spread_measurements/
```

### Acceptance Criteria

| Criterion | Threshold |
|-----------|-----------|
| Sessions measured | >= 21 (3 sessions x 7 days) |
| Per-session samples | >= 50 |
| Source | Live Pepperstone MT5 (not yfinance/paper) |
| Statistics computed | min, p25, median, p75, p95, max per session |

### Update Cost Calibration

```bash
python scripts/update_cost_calibration.py \
  --from-spread-data data/spread_measurements/summary.json \
  --output config/cost_calibration_live.json
```

### Evidence Artifacts
```
data/spread_measurements/summary.json
config/cost_calibration_live.json
reports/spread_measurement_report.md
```

---

## PHASE 1: FIX ALL 13 P0 BLOCKERS (3 weeks)

**Prerequisite:** Phase 0A GO verdict
**Goal:** Zero P0 blockers remaining

### Task 1.1: Fix SL/TP Midpoint Bug (P0-B1)
- **File:** `execution/fill_model.py:67-87`
- **Bug:** `check_sl_tp_trigger()` uses `(high+low)/2` midpoint = inflates win rate
- **Fix:** Use `bar.high` for long TP, `bar.low` for long SL (inverse for short)
- **Test:** `python -m pytest tests/test_fill_model.py -v`

### Task 1.2: Wire Swap Costs (P0-B2)
- **Files:** `backtest/engine.py:890-905`, `execution/swap_model.py`
- **Bug:** `BacktestConfig.enable_swap=True` read nowhere in close path
- **Fix:** Add swap cost in `_close_position()`: `pnl -= swap_cost * holding_days`
- **Test:** `python -m pytest tests/test_swap.py -v`

### Task 1.3: Hardened Kill Switch (P0-B3)
- **File:** `risk/kill_switch.py:149-151`
- **Bug:** Corrupt JSON → silent reset to OFF = positions unprotected
- **Fix:** On JSONDecodeError/FileNotFoundError → emergency_kill("STATE_CORRUPTION")
- **Test:** `python -m pytest tests/test_kill_switch.py -v -k corrupt`

### Task 1.4: Fix AlertManager (P0-B9)
- **File:** `monitoring/alerts.py`
- **Bug:** `send_alert()` has empty routing blocks → ALL alerts silently dropped
- **Fix:** Implement: (1) file log, (2) Telegram if configured, (3) console fallback
- **Test:** `python -m pytest tests/test_alerts.py -v`

### Task 1.5: Fix webhook_receiver Import (P0-B5)
- **File:** `api/webhook_receiver.py`
- **Bug:** `import AssetClass, SignalSource from core.signal_gateway` → module doesn't exist
- **Fix:** Define inline enums or import from valid path

### Task 1.6: Secrets Rotation (P0-B6, B7, B8)
- **Bug:** 3 hardcoded API keys, MT5 account in git history, real FRED key in .env.example
- **Fix:** Replace all with `os.environ.get()`, git filter-branch history, rotate ALL keys
- **Verify:** `git grep -i "api.key|secret|token" -- "*.py" | grep -v "os.environ"` returns empty

### Task 1.7: Wire Pre-Trade Gate to Live Path (P0-B10)
- **File:** `execution/manager.py`
- **Bug:** Pre-trade risk gate not called before broker order (INV-009 violation)
- **Fix:** Call `pre_trade_gate.check(order)` BEFORE `oms.submit(order)`; reject if not approved

### Task 1.8: Wire Crash Recovery (P0-B11)
- **File:** `execution/position_reconciler.py`
- **Bug:** Position reconciler "not wired to real-time monitoring"
- **Fix:** Run reconciler on startup via `core/state_coordinator.py`; auto-close orphans

### Task 1.9: Fix auto_retrain Dummy Metrics (P0-B12)
- **File:** `scripts/auto_retrain.py`
- **Bug:** `evaluate_model()` returns hardcoded dummy values
- **Fix:** Replace with actual sklearn metrics: accuracy, precision, recall, f1

### Task 1.10: Unify Signal Path (P0-B13)
- **Files:** `api/main.py`, `api/signal_service.py`
- **Bug:** signal_service runs as separate FastAPI on port 8752, not in main.py
- **Fix:** Remove port 8752; route signals via `app.include_router(signal_router, prefix="/api/v1/signals")`

### Task 1.11: Remove CORS Wildcard (P0-B4)
- **File:** `api/signal_service.py`
- **Fix:** Allow specific origins only, not `*`

### Task 1.12: Fix pct_change fill_method Parity
- **File:** `backtest/engine.py`
- **Bug:** Backtest uses `fill_method="pad"`, paper bot uses `fill_method=None` → different returns
- **Fix:** Unify to `fill_method=None` for parity with paper bot

### Task 1.13: Wire Actual Spread+Commission
- **Files:** `core/cost_model.py`, `backtest/engine.py`
- **Fix:** Load costs from `cost_calibration_live.json` instead of hardcoded defaults

### Phase 1 Acceptance

- [ ] All 13 P0 blockers fixed with passing tests
- [ ] `git diff --staged` reviewed per INV-013
- [ ] Security scan: zero hardcoded secrets (`git grep` clean)
- [ ] Kill switch: corruption test passes
- [ ] AlertManager: end-to-end test passes
- [ ] Pre-trade gate: wired and blocking unapproved orders
- [ ] Crash recovery: startup reconciliation functional
- [ ] Full test suite: `python -m pytest tests/ -v --tb=short -q` — 0 failures

---

## 🚦 DECISION GATE — MANDATORY STOP POINT

**This gate cannot be bypassed. ALL items must be true before Phase 2.**

| # | Condition | Phase | Evidence |
|---|-----------|-------|----------|
| 1 | Cross-sectional DK t-stat > 2.0 | 0A | `edge_search_cross_sectional_*.json` |
| 2 | Positive Sharpe count >= 5 of 7 | 0A | Same artifact |
| 3 | Label-shuffle p-value < 0.05 | 0A | `label_shuffle_cross_sectional_*.json` |
| 4 | 7-day spread measurement complete | 0B | `data/spread_measurements/summary.json` |
| 5 | All 13 P0 blockers fixed + tested | 1 | `pytest` output + git diff |
| 6 | Sacred holdout NOT burned | 0A | Holdout file unchanged |
| 7 | Trial #2001 registered in `hypothesis_registry.json` | 0A | Registry file |
| 8 | Human approval signed | All | `CHANGE_CONTROL.md` |
| 9 | Sacred holdout validated | 0A | `holdout_validation_2001_*.json` |

**IF ALL PASS → Phase 2. IF ANY FAIL → ARCHIVE_NO_EDGE — STOP THE ENTIRE PLAN.**

---

## PHASE 2: PAPER TRADING CAMPAIGN (9 weeks)

**Prerequisite:** Decision Gate GO (all 9 conditions met)
**Minimum:** 60 trading days, 100 trades

### Setup

```bash
python -m paper_engine.engine \
  --strategy momentum_factor_rotation \
  --config config/paper_trade_config.json \
  --universe XAUUSD,XAGUSD,EURUSD,GBPUSD,USDJPY,NAS100,US30 \
  --broker-adapter paper \
  --cost-model config/cost_calibration_live.json \
  --output-dir reports/paper_trading/
```

### Paper Trade Config (`config/paper_trade_config.json`)

```json
{
  "strategy": "momentum_factor_rotation",
  "initial_capital": 100000,
  "risk_per_trade_pct": 1.0,
  "max_drawdown_pct": 20.0,
  "daily_loss_limit_pct": 5.0,
  "position_sizing": "vol_target",
  "vol_target": 0.10,
  "rebalance_freq": "weekly",
  "market_data_source": "mt5_csv",
  "trade_log": "reports/paper_trading/trades.jsonl",
  "equity_log": "reports/paper_trading/equity.jsonl"
}
```

### Acceptance Criteria

| Criterion | Minimum | Preferred |
|-----------|---------|-----------|
| Trading days | 60 | 90 |
| Total trades | 100 | 200 |
| Win rate | > 40% | > 50% |
| Profit factor | > 1.1 | > 1.3 |
| Sharpe ratio | > 0.5 | > 1.0 |
| Max drawdown | < 20% | < 15% |
| Daily VAR (95%) | < 3% | < 2% |
| PBO | < 0.5 | < 0.3 |
| Deflated Sharpe | > 0 | > 0.5 |

### Daily/Weekly Monitoring

```bash
python scripts/paper_trade_daily_check.py       # Daily health check
python scripts/paper_trade_weekly_report.py      # Weekly performance report
```

### Output

```
reports/paper_trading/trades.jsonl           # Every trade with timestamps
reports/paper_trading/equity.jsonl           # Daily equity curve
reports/paper_trading/weekly_report_*.md     # Weekly summaries
reports/paper_trading/final_report.md        # 60-day final report
reports/paper_trading/equity_curve.png       # Visualization
reports/paper_trading/drawdown_chart.png     # Drawdown visualization
```

---

## PHASE 3: LIVE READINESS GATES (2 weeks)

**Prerequisite:** Phase 2 PASS (all criteria met)

### 24-Hour Smoke Test

```bash
python -m live_readiness.smoke_test \
  --duration-hours 24 \
  --mt5-mode readonly \
  --paper-trades only \
  --monitor-all \
  --output reports/live_readiness/smoke_test_YYYYMMDD.json
```

### 20-Item Live Readiness Checklist

| # | Item | Evidence |
|---|------|----------|
| 1 | Secrets rotated | `git grep` report clean |
| 2 | MT5 connection verified | `broker_verification_report.md` |
| 3 | Kill switch tested (corrupt + normal) | Test output |
| 4 | Alert system end-to-end | Telegram capture + log |
| 5 | Pre-trade gate wired + blocking | Code review + test |
| 6 | Crash recovery tested | Simulated restart |
| 7 | Swap costs wired | Backtest comparison |
| 8 | SL/TP high/low verified | Test output |
| 9 | Cost model using measured spreads | `cost_calibration_live.json` |
| 10 | Paper trading 60+ days COMPLETE | `reports/paper_trading/final_report.md` |
| 11 | Paper trading all criteria met | Criteria table above |
| 12 | Sacred holdout validated | `reports/holdout_validation_*.json` |
| 13 | Human approval signed | `CHANGE_CONTROL.md` |
| 14 | PBO < 0.5 confirmed | Walk-forward output |
| 15 | Deflated Sharpe > 0 confirmed | Walk-forward output |
| 16 | Multiple testing correction applied | All trials accounted |
| 17 | Position reconciliation tested | Broker vs internal match |
| 18 | Circuit breaker tested | Simulated drawdown trigger |
| 19 | Data freshness verified | `data_watermark.py` output |
| 20 | No INV-012 violations in any document | Document review |

### Gradual Scale to Live

```bash
# Step 1: 1% capital, READ-ONLY mode (1 week)
python -m paper_engine.engine --mode live-readonly --capital-pct 1.0

# Step 2: 1% capital, LIVE EXECUTION with human approval (1 week)
python -m paper_engine.engine --mode live-execution --capital-pct 1.0 --require-human-approval

# Step 3: 5% capital (1 week + approval)
# Step 4: 10% capital (1 week + approval)
# Step 5: full allocation (after all prior steps pass)
# Each step: 1 week minimum + zero critical incidents + human sign-off
```

---

## ⚡ KILL SWITCH PROTOCOL

```
TRIGGER CONDITIONS:
├── Daily loss > 5% of capital → HARD KILL (close all positions, block orders)
├── Drawdown > 20% from peak → HARD KILL
├── 3 consecutive stop-loss hits within 1 hour → SOFT KILL (block new, keep existing)
├── Data feed stale > 60 seconds → SOFT KILL
├── MT5 connection lost > 30 seconds → SOFT KILL
├── Single position > 10% of capital → BLOCK ORDER (don't kill)
└── Manual /kill via Telegram → HARD KILL

RECOVERY:
├── Human review REQUIRED after HARD KILL
├── Automated resume after SOFT KILL if condition clears
├── STATE_CORRUPTION → PERMANENT KILL (require human + key rotation)
└── All kill events logged to file + Telegram + console (P0-B9 fix ensures this)
```

---

## 🎲 RISK REGISTER

| Risk | Probability | Impact | Mitigation |
|------|------------|--------|------------|
| Cross-sectional also REJECT | MEDIUM | HIGH | Stop at Decision Gate; `ARCHIVE_NO_EDGE` |
| MT5 connection unstable | LOW | HIGH | Paper adapter fallback; daily connectivity test |
| $7/rt commission kills CS edge | MEDIUM | MEDIUM | Test with + without costs; consider ECN broker |
| Overfitting in paper trading | LOW | MEDIUM | Sacred holdout preserved; pre-registered params |
| Cost model still inaccurate | MEDIUM | MEDIUM | 7-day continuous measurement; update monthly |
| Python/memory crash mid-trade | LOW | HIGH | Kill switch persist; crash recovery wired |
| Market regime shift during paper | MEDIUM | LOW | 7 assets diversification; vol targeting; 60+ day duration |

---

## 📜 CONSTITUTION COMPLIANCE MATRIX

| Invariant | Requirement | How Plan Complies |
|-----------|-------------|-------------------|
| INV-001 | Risk policy frozen | Configs are immutable JSON |
| INV-002 | Loss limits in bps | `daily_loss_limit_pct: 5.0` converted to bps internally |
| INV-003 | No `order_send` in backtest | P0-B1 fix uses fill_model, not direct send |
| INV-004 | Strict MTF | Cross-sectional uses D1 only (single timeframe) |
| INV-005 | Dataset manifests with SHA-256 | All datasets referenced via manifests |
| INV-008 | Kill switch persist | P0-B3 fix: corruption = KEEP KILLED (fail closed) |
| INV-009 | Pre-trade risk gate mandatory | P0-B10 fix: gate wired before every order |
| INV-010 | Invalid contract = fail closed | Phase 3 verification includes contract validation |
| INV-012 | Edge claims cite trial + p-value + artifact | Every claim in this plan fully cited |
| INV-013 | Diff matches intent | Every Phase 1 commit reviewed via `git diff --staged` |

### Required Phase Verdicts (per CONSTITUTION.md:9)

| Phase | Expected Verdict | Condition |
|-------|-----------------|-----------|
| Phase 0A | `PASS_TO_NEXT_PHASE` or `ARCHIVE_NO_EDGE` | Cross-sectional GO or REJECT |
| Phase 0B | `PASS_TO_NEXT_PHASE` | 7-day measurement complete |
| Phase 1 | `PASS_TO_NEXT_PHASE` | All 13 P0s fixed + tests pass |
| Phase 2 | `PASS_TO_NEXT_PHASE` | 60+ days, 100+ trades, all criteria met |
| Phase 3 | `PASS_TO_NEXT_PHASE` | All 20 checklist items verified |

---

## 🛑 STOPPING RULE

`CONSTITUTION.md:98` — STOPPING RULE triggered: 4 consecutive p-value failures.

**This plan resets the counter** via a NEW research direction (Cross-Sectional Momentum ≠ Technical Single-Asset). The reset is valid because:
1. Different mechanism (relative ranking vs absolute direction)
2. Different data requirement (multi-asset panel vs single-asset OHLCV)
3. Different academic foundation (cross-sectional momentum literature vs TA indicators)
4. Pre-registered parameters (frozen before testing)

**If Cross-Sectional Momentum is REJECTED:**
1. `ARCHIVE_NO_EDGE` — document all findings
2. Consider Path C — external edge import from peer-reviewed literature (e.g., TSMOM futures)
3. Consider asset-class pivot (crypto-only, commodities-only)
4. **DO NOT** re-run single-asset D1 TA (already proven no edge across 25+ strategies)
5. **DO NOT** tweak parameters after seeing results (p-hacking, forbidden by Constitution)
6. **DO NOT** ensemble REJECTED strategies (garbage × garbage = garbage)

---

## 🖥️ COMMAND QUICK REFERENCE

```bash
# Phase 0A: Cross-Sectional Edge Discovery
python scripts/edge_search_cross_sectional.py --universe XAUUSD,XAGUSD,EURUSD,GBPUSD,USDJPY,NAS100,US30 --cost-model pepperstone_razor --dk-test pooled --label-shuffle 200 --output reports/edge_search_cross_sectional_20260720.json

# Phase 0A: Sacred Holdout Validation (ONLY after GO on DK + label-shuffle)
python scripts/holdout_validate.py --trial 2001 --holdout data/sacred_holdout/holdout_fresh_20260717.csv

# Phase 0B: Spread Measurement
python scripts/measure_spread_continuous.py --symbols XAUUSD --duration-days 7 --output-dir data/spread_measurements/
python scripts/update_cost_calibration.py --from-spread-data data/spread_measurements/summary.json --output config/cost_calibration_live.json

# Phase 1: Run Full Test Suite After All Fixes
python -m pytest tests/ -v --tb=short -q

# Phase 1: Security Scan (must return empty)
git grep -i "api.key|secret|password|token" -- "*.py" | grep -v "os.environ|env|test_"

# Phase 2: Paper Trading
python -m paper_engine.engine --strategy momentum_factor_rotation --config config/paper_trade_config.json --universe XAUUSD,XAGUSD,EURUSD,GBPUSD,USDJPY,NAS100,US30 --broker-adapter paper --cost-model config/cost_calibration_live.json --output-dir reports/paper_trading/
python scripts/paper_trade_daily_check.py
python scripts/paper_trade_weekly_report.py

# Phase 3: Smoke Test
python -m live_readiness.smoke_test --duration-hours 24 --mt5-mode readonly --paper-trades only --monitor-all --output reports/live_readiness/smoke_test_YYYYMMDD.json

# Phase 3: Final Verification
python -m live_readiness.verify_env
python scripts/walk_forward.py --config config/live_trade_config.json
```

---

## 📁 FILE MANIFEST

### New Files
| File | Phase | Purpose |
|------|-------|---------|
| `scripts/edge_search_cross_sectional.py` | 0A | Cross-sectional DK-test harness |
| `scripts/paper_trade_daily_check.py` | 2 | Daily health check automation |
| `scripts/paper_trade_weekly_report.py` | 2 | Weekly performance report automation |
| `config/paper_trade_config.json` | 2 | Paper trading configuration |
| `config/live_trade_config.json` | 3 | Live trading configuration |
| `reports/edge_search_cross_sectional_*.json` | 0A | Edge search results |
| `reports/label_shuffle_cross_sectional_*.json` | 0A | Label-shuffle results |
| `reports/holdout_validation_2001_*.json` | 0A | Sacred holdout validation |
| `reports/paper_trading/*` | 2 | Paper trading logs + reports |
| `reports/live_readiness/smoke_test_*.json` | 3 | Smoke test results |
| `reports/spread_measurement_report.md` | 0B | Spread measurement report |
| `Meta/live_deployment_manifest.json` | 3 | Deployment manifest |

### Modified Files
| File | Phase | Change |
|------|-------|--------|
| `execution/fill_model.py` | 1 | SL/TP high/low fix (P0-B1) |
| `backtest/engine.py` | 1 | Swap costs + fill_method parity (P0-B2, T1.12) |
| `risk/kill_switch.py` | 1 | Corrupt JSON = fail closed (P0-B3) |
| `monitoring/alerts.py` | 1 | Implement alert routing (P0-B9) |
| `api/webhook_receiver.py` | 1 | Fix broken import (P0-B5) |
| `api/main.py` | 1 | Unify signal path (P0-B13) |
| `api/signal_service.py` | 1 | Remove CORS wildcard + port 8752 (P0-B4, B13) |
| `execution/manager.py` | 1 | Wire pre-trade gate (P0-B10) |
| `execution/position_reconciler.py` | 1 | Wire crash recovery (P0-B11) |
| `scripts/auto_retrain.py` | 1 | Replace dummy metrics (P0-B12) |
| `core/cost_model.py` | 1 | Load from cost_calibration_live.json (T1.13) |
| `.env.example` | 1 | Remove real keys (P0-B8) |
| Multiple `*.py` files | 1 | Remove hardcoded secrets (P0-B6) |
| `research/hypothesis_registry.json` | 0A | Add Trial #2001 |
| `config/cost_calibration_live.json` | 0B | Updated from spread measurement |
| `CHANGE_CONTROL.md` | All | Human sign-offs at each gate |

---

## 📋 SUMMARY TABLE

| Phase | Duration | Deliverable | Gate |
|-------|----------|-------------|------|
| **0A: Edge Discovery** | 2 weeks | DK t-stat + label-shuffle results | dk_t > 2.0, p < 0.05 |
| **0B: Spread Measure** | 1 week | Multi-session spread baseline | 21+ sessions |
| **🚦 Decision Gate** | 1 day | GO/NO-GO verdict | All 9 conditions |
| **1: Fix P0 Blockers** | 3 weeks | Zero P0 bugs, full test pass | 0 failures, clean git grep |
| **2: Paper Trading** | 9 weeks | 60d + 100 trades evidence | All 9 criteria met |
| **3: Live Readiness** | 2 weeks | 20-item checklist verified | All 20 items checked |
| **LIVE** | Continuous | Gradual scale 1% → 100% | Weekly approval + no incidents |

**Total minimum timeline: 17 weeks (~4 months) from start to live, IF every phase passes.**

**If ANY phase fails → STOP, archive, reassess.**

---

## One-Sentence Truth

> After 33 rejected trials across single-asset TA, Path B macro, and forex investigations, with 13 critical infrastructure bugs still open, the ONLY evidence-based path to live trading is: prove cross-sectional momentum edge via pre-registered DK-test + label-shuffle, measure real spreads for 7 days, fix every P0 blocker without introducing new bugs, survive 60+ days of paper trading with all criteria met, pass 20 live-readiness gates, then scale gradually — if ANY step fails, STOP.

---

**Generated:** 2026-07-20
**Sources:** 35+ documents cited inline throughout
**Next Review:** After Phase 0A completion (~2 weeks)
**Supersedes:** `Meta/GRAXIA_TSM_UNIFIED_MEGA_REMEDIATION_PLAN_2026-07-01.md` (Wave 0-9 plan, partially executed)
**Does NOT supersede:** `CONSTITUTION.md`, `CHANGE_CONTROL.md` (locked experiments), `AUDIT_INDEX.md`

# END OF PLAN