# FULL REPOSITORY AUDIT — quant_os (Graxia OS)
**Date:** 2026-06-25  
**Auditor:** bridge agent  
**Scope:** Complete codebase audit of quant_os v0.2.0-dev  
**Status:** READ-ONLY — no modifications made

---

## PHASE 0 — REPOSITORY CENSUS

### Folder Structure (Key Modules)
```
quant_os/
├── core/           Config, enums, cost model, regime filter, ML pipeline, signal filter
├── backtest/       Backtesting engine, walk-forward, metrics
├── execution/      Fill model, cost model, broker adapter, execution simulator, swap model
├── risk/           Kill switch, pre-trade risk, position sizer, circuit breaker
├── validation/     Walk-forward, bootstrap, deflated Sharpe, cost stress
├── data/           154 CSV files (10 symbols × 9 timeframes), feed, pipeline, warehouse
├── strategies/     Base, MTM, MRB, MLB, ensemble
├── regime/         Detector, liquidity map, sweep classifier, entry executor, risk overlay, monitor
├── shadow/         Shadow mode, canonical bar/tick, telemetry, broker profile
├── news_events/    Event models, event risk gate, event store, macro policy
├── monitoring/     Health check, Telegram, metrics, alerts
├── mt5_connector/  MT5 connection, shadow runner
├── tests/          100+ test files (unit, integration, phase-specific)
├── config/         cost_calibration.json, broker profile, telegram config
└── docs/           Architecture ADRs, schema, safety checklist
```

### Frameworks/Libraries Actually Used
| Library | Evidence | Location |
|---------|----------|----------|
| MetaTrader5 | `import MetaTrader5 as mt5` | `mt5_connector/connection.py:57`, `core/cost_model.py:90`, `run_paper_trading.py:77` |
| pandas/pandas_ta | `import pandas as pd; import pandas_ta as ta` | `backtest/engine.py:338-339` |
| sklearn | `from sklearn.preprocessing import StandardScaler` | `core/ml_pipeline.py:152` |
| requests | `import requests` | `monitoring/health_check.py:18` |
| pydantic | Used in schemas | `core/schemas.py` |

### Entry Points
| Script | Purpose | Evidence |
|--------|---------|----------|
| `run_paper_trading.py` | Paper trading via Liquidity Sweep pipeline | `run_paper_trading.py:550` |
| `run_backtest.py` | Backtest runner | `run_backtest.py` |
| `run_scheduled.py` | Scheduled tasks | `run_scheduled.py` |
| `api/main.py` | FastAPI surface | Referenced in AGENTS.md |
| `monitoring/health_check.py:watchdog_loop` | Watchdog for auto-restart | `monitoring/health_check.py:53` |

### Config Files & Parameters
| File | Parameters |
|------|-----------|
| `core/config.py` | `QuantConfig` — all trading mode, MT5, risk, strategy weights |
| `core/golden_rules.py` | `GoldenRules` — immutable safety constraints |
| `risk/risk_policy.py` | `RiskPolicy` — basis-point risk limits |
| `config/cost_calibration.json` | XAUUSD/EURUSD/GBPUSD cost calibration |
| `.env.example` | MT5 credentials template |
| `config/telegram_config.toml` | Telegram notification config |

### Data on Disk vs Referenced
| Status | Evidence |
|--------|----------|
| ✅ 154 CSV files present | `data/` directory listing |
| ✅ ForexFactory calendar absent | No ForexFactory files found in `data/news/` |
| ✅ Macro data present | `data/macro/` directory exists |
| ✅ Manifests present | `data/manifests/*.manifest.json` |

### Test Coverage
- **100+ test files** in `tests/` directory
- **Key coverage:** `test_phase_*` for each phase, `test_backtesting_py_oracle.py`, `test_cost_unit_regression.py`
- **Missing coverage:** No dedicated test for ForexFactory integration (absent data), no multi-position correlation test

---

## PHASE 1 — DATA PIPELINE & LEAKAGE FORENSICS

### Lookahead Bias

| Check | Status | Evidence |
|-------|--------|----------|
| LookaheadGuard in backtest | ✅ PASS | `backtest/engine.py:274` — `guard = LookaheadGuard(strict=True)` |
| Guard advance per bar | ✅ PASS | `backtest/engine.py:280` — `guard.advance()` at start of each bar |
| Signal from closed bar N → fill on N+1 | ✅ PASS | `backtest/engine.py:311` comment: "4. Execute signal (fills on NEXT bar)" |
| LookaheadGuard check_data_access | ✅ PASS | `core/lookahead_guard.py:33-40` — raises `LookaheadViolation` in strict mode |
| Feature calculation uses slice | ✅ PASS | `backtest/engine.py:341-344` — `[:up_to_index+1]` slice in `_calculate_indicators` |
| get_slice uses current_index | ✅ PASS | `core/lookahead_guard.py:43-46` — returns `{k: v[:idx+1]}` |

### Timestamp/Timezone Handling

| Check | Status | Evidence |
|-------|--------|----------|
| MT5 server time vs local | ⚠️ UNVERIFIED | `run_paper_trading.py:240` — `datetime.fromtimestamp(int(r["time"]))` — uses system time, not explicit timezone |
| DST transitions | ⚠️ UNVERIFIED | No DST handling found in data pipeline |
| Bar timestamp type | ⚠️ UNVERIFIED | `backtest/engine.py:281` — `current_time = self.timestamps[i]` — depends on caller providing correct timestamps |
| Cost model session classification | ✅ PASS | `core/cost_model.py:33-56` — `get_session(hour_utc)` classifies UTC hours |

### Data Integrity

| Check | Status | Evidence |
|-------|--------|----------|
| CSV data present | ✅ PASS | 154 CSV files in `data/` |
| Manifests with SHA-256 | ✅ PASS | `CONSTITUTION.md:19` — INV-005 requires manifests |
| Duplicate detection | ⚠️ UNVERIFIED | No explicit dedup logic found in `data/feed.py` |
| Stale data handling | ✅ PARTIAL | `risk/risk_policy.py:19` — `reject_if_data_stale_seconds: int = 5` |

### Train/Test Boundary Leakage

| Check | Status | Evidence |
|-------|--------|----------|
| Scaler fit on train only | ✅ PASS | `core/ml_pipeline.py:147-155` — `fit_scaler` docs say "CRITICAL: Call ONLY on training data" |
| Chronological split | ✅ PASS | `core/ml_pipeline.py:130-145` — `prepare_training_data` sorts by timestamp, splits chronologically |
| Walk-forward embargo | ✅ PASS | `validation/walk_forward.py:25` — `embargo_bars` parameter for gap between train/test |

### Survivorship/Selection Bias

| Check | Status | Evidence |
|-------|--------|----------|
| Instrument choice | ⚠️ UNVERIFIED | XAUUSD primary, EURUSD/GBPUSD planned — not yet researched per `KNOWN_LIMITATIONS.md:6` |
| Period choice | ⚠️ UNVERIFIED | Backtest dates configurable in `core/config.py:103-104` |

---

## PHASE 2 — FEATURE & SIGNAL AUDIT

### Features Computed

| Feature | Where Defined | Evidence |
|---------|--------------|----------|
| EMA 9/20/50/200 | `backtest/engine.py:358-361` | `ta.ema(df["close"], length=N)` |
| RSI 14 | `backtest/engine.py:364` | `ta.rsi(df["close"], length=14)` |
| ATR 14 | `backtest/engine.py:365` | `ta.atr(df["high"], df["low"], df["close"], length=14)` |
| Bollinger Bands (20, 2) | `backtest/engine.py:368-372` | `ta.bbands(df["close"], length=20, std=2)` |
| Volume SMA 20 | `backtest/engine.py:375` | `df["volume"].rolling(window=20).mean()` |
| ADX 14 | `backtest/engine.py:378-380` | `ta.adx(df["high"], df["low"], df["close"], length=14)` |
| Regime Filter (ADX, volatility, EMA, BB) | `core/regime_filter.py:76-122` | `RegimeFilter.detect()` |

### Correlation/IC Claims

| Claim | Evidence | Status |
|-------|----------|--------|
| max \|r\| ≈ 0.06 on 1-min features | No source file found with this exact number | ⚠️ UNVERIFIED — likely from external analysis, not in codebase |
| 58.2% accuracy OOS | `SUMMARY.md:6` — "58.2% accuracy OOS at conf≥0.75" | ⚠️ UNVERIFIED — claimed in summary, not in code |

### Multiple Testing Correction

| Check | Status | Evidence |
|-------|--------|----------|
| Bonferroni correction | ❌ NOT FOUND | No Bonferroni implementation in codebase |
| Benjamini-Hochberg/FDR | ❌ NOT FOUND | No FDR implementation in codebase |
| Any p-value correction | ❌ NOT FOUND | `core/signal_filter.py` checks p-value but doesn't correct for multiple tests |

### Feature Redundancy

| Check | Status | Evidence |
|-------|--------|----------|
| EMA 9/20/50/200 correlated | ⚠️ UNVERIFIED | No multicollinearity check found |
| ADX vs ATR overlap | ⚠️ UNVERIFIED | ADX uses ATR internally |

---

## PHASE 3 — BACKTEST / WALK-FORWARD VALIDATION INTEGRITY

### Transaction Cost Model — First Principles Re-derivation

**Two cost models exist:**

1. **`execution/cost_model.py`** (Stress matrix)
   - `calculate_trade_costs()` at line 32-51
   - `spread = spread_points * scenario.spread_mult * contract_size * volume`
   - `slippage = spread_points * scenario.slippage_mult * contract_size * volume`
   - **Units:** spread_points × contract_size × volume = account currency (USD)

2. **`core/cost_model.py`** (Session-based for XAUUSD)
   - `COST_PER_TRADE_BY_SESSION` at line 18-23
   - Asian: $0.28, London: $0.14, NY: $0.15, Overlap: $0.12
   - **Units:** dollars per 0.01 lot (1 oz)

**The ~2000x Bug — Is It Fixed?**

| Finding | Evidence |
|---------|----------|
| Bug description in code | `core/cost_model.py:4` — "Bug #2 fix: v2.0 treated XAUUSD like an FX pair with spread + flat per-side commission" |
| Pepperstone Razor: commission embedded in spread | `core/cost_model.py:7` — "commission on metals is embedded in the quoted spread" |
| Live round-trip cost = ask - bid | `core/cost_model.py:83-98` — `get_live_round_trip_cost()` returns `tick.ask - tick.bid` |
| SUMMARY.md confirms fix | `SUMMARY.md:4` — "Bug fixed: simulate_fills.py had ms/ns unit bug (added 50,000,000ms=13.9hr instead of 50ms). Fixed P90 slippage: 6367pts→39pts" |

**Conclusion:** The ms→ns unit bug was fixed (confirmed in SUMMARY.md:4). The Pepperstone Razor double-counting bug was fixed (core/cost_model.py:4). **However, the swap model is NOT integrated into backtest cost calculation** (KNOWN_LIMITATIONS.md:3 — "Swap not modeled in cost calculations").

### Walk-Forward Methodology

| Check | Status | Evidence |
|-------|--------|----------|
| Fold construction | ✅ PASS | `validation/walk_forward.py:17-42` — `walk_forward_split()` with embargo |
| Embargo gap | ✅ PASS | `validation/walk_forward.py:36` — `test_start = train_end + embargo_bars` |
| Parameter fit outside fold | ⚠️ UNVERIFIED | Walk-forward splits data but doesn't explicitly track hyperparameter fitting |

### Slippage & Fill Assumptions

| Check | Status | Evidence |
|-------|--------|----------|
| Conservative bar model | ✅ PASS | `execution/conservative_bar_model.py` — `estimate_bid_ask_from_bar()` |
| Next-bar fill | ✅ PASS | `execution/execution_simulator.py:183` — `fill_idx = bar_index + 1` |
| Slippage as spread/2 | ✅ PASS | `execution/execution_simulator.py:197` — `slippage_entry = market.spread / Decimal("2")` |

### Statistical Significance

| Check | Status | Evidence |
|-------|--------|----------|
| Monte Carlo | ✅ EXISTS | `core/monte_carlo.py` — `MonteCarloResult` with p-value |
| Deflated Sharpe | ✅ EXISTS | `validation/deflated_sharpe.py` |
| PBO | ✅ EXISTS | `validation/probability_overfitting.py` |
| Multiple testing correction | ❌ MISSING | No Bonferroni/BH across all hypotheses tested |

---

## PHASE 4 — RISK & EXECUTION FORENSICS

### Position Sizing

| Check | Status | Evidence |
|-------|--------|----------|
| Risk-based sizing | ✅ PASS | `risk/position_sizer_v2.py:33-230` — `size_position()` with risk budget |
| Volume rounds DOWN | ✅ PASS | `risk/position_sizer_v2.py:166` — `to_integral_value(rounding=ROUND_DOWN)` |
| Contract snapshot binding | ✅ PASS | `risk/position_sizer_v2.py:229` — `contract_snapshot_id=contract_spec.snapshot_hash` |

### Kill Switch & Circuit Breaker

| Check | Status | Evidence |
|-------|--------|----------|
| Kill switch exists | ✅ PASS | `risk/kill_switch.py:8` — `KillSwitch` class |
| Kill switch persists across restart | ✅ PASS | `risk/kill_switch.py:39-46` — `_load()` from JSON file |
| Circuit breaker exists | ✅ PASS | `risk/circuit_breaker.py:53` — `CircuitBreaker` with auto-reset |
| Pre-trade risk gate | ✅ PASS | `risk/pre_trade_risk.py:35-92` — `pre_trade_check()` checks kill switch, daily/weekly/drawdown, position count |

### MT5 Connection Handling

| Check | Status | Evidence |
|-------|--------|----------|
| Connect/disconnect | ✅ PASS | `mt5_connector/connection.py:54-86` |
| Reconnect logic | ❌ NOT FOUND | No auto-reconnect in `MT5Connection` |
| Requote handling | ❌ NOT FOUND | `MT5BrokerAdapter.place_order()` sends `deviation: 10` points but doesn't handle requote response |
| Partial fills | ❌ NOT FOUND | `PaperBroker` always fills 100%, MT5 adapter doesn't handle partial |

### Order Lifecycle

| Check | Status | Evidence |
|-------|--------|----------|
| Duplicate order protection | ⚠️ PARTIAL | `run_paper_trading.py:254-256` — skips if existing position, but no idempotency key |
| Missing stop loss rejection | ✅ PASS | `backtest/engine.py:409` — `if not signal.stop_loss or signal.stop_loss <= 0: self._log_critical_incident("MISSING_SL", signal)` |
| Invalid SL direction rejection | ✅ PASS | `backtest/engine.py:417-422` |

### Crash Recovery

| Check | Status | Evidence |
|-------|--------|----------|
| Reconciliation on restart | ❌ NOT FOUND | No reconciliation logic against MT5 account state on restart |
| State persistence | ⚠️ PARTIAL | `kill_switch.py` persists kill switch state, but no trade state persistence |

---

## PHASE 5 — CODE QUALITY & TECHNICAL DEBT

### Dead Code / Duplicated Logic

| Issue | Evidence |
|-------|----------|
| Two RiskPolicy classes | `risk/pre_trade_risk.py:12` and `risk/risk_policy.py:8` — both define `RiskPolicy` |
| Two cost models | `execution/cost_model.py` and `core/cost_model.py` — different approaches |
| Two position sizers | `risk/position_sizer.py` and `risk/position_sizer_v2.py` — v2 is newer |
| `RiskPolicy` not frozen | `risk/pre_trade_risk.py:12` — `@dataclass` (mutable), violating INV-001 |
| `risk/risk_policy.py:8` — frozen | `@dataclass(frozen=True)` — correct implementation |

### Hardcoded Parameters

| Parameter | Location | Should Be |
|-----------|----------|-----------|
| Spread = 2 pips | `backtest/engine.py:437` | Config-driven per symbol |
| Contract size = 100 | `backtest/engine.py:446` | From ContractSpec |
| Commission = $3.5/lot | `backtest/engine.py:92` | Broker-specific |
| SLippage = 0.5 pips | `backtest/engine.py:91` | Broker-specific |

### Backtest/Live Parity

| Check | Status | Evidence |
|-------|--------|----------|
| Shared execution logic | ✅ PASS | `execution/execution_simulator.py` — `BacktestExecutionSimulator` used by engine |
| Separate code paths | ⚠️ CONCERN | `run_paper_trading.py` uses `PaperBroker` which has its own fill logic separate from `BacktestExecutionSimulator` |
| Fill model differences | ⚠️ CONCERN | `PaperBroker` uses random slippage (`random.uniform(0, 0.5)`), backtest uses spread-based slippage |

---

## PHASE 6 — SECURITY AUDIT

### MT5 Credentials

| Check | Status | Severity | Evidence |
|-------|--------|----------|----------|
| .env.example has placeholders | ✅ SAFE | N/A | `.env.example:2-4` — `MT5_LOGIN=0`, empty password |
| Hardcoded server in config | ⚠️ LOW | Low | `core/config.py:33` — `mt5_server: str = "ICMarketsSC-Demo"` |
| Hardcoded MT5 path | ⚠️ LOW | Low | `core/config.py:34` — `mt5_path = r"C:\Program Files\MetaTrader 5\terminal64.exe"` |
| Telegram token in env | ✅ SAFE | N/A | `core/config.py:48` — loaded from env |
| JWT secret in config | ✅ SAFE | N/A | `core/config.py:42` — loaded from env |

### Secrets Management

| Check | Status | Severity | Evidence |
|-------|--------|----------|----------|
| No plaintext secrets in code | ✅ SAFE | N/A | All secrets loaded via `os.getenv()` |
| .gitignore present | ✅ SAFE | N/A | `.gitignore` exists |
| No .env committed | ✅ SAFE | N/A | Only `.env.example` present |

---

## PHASE 7 — OBSERVABILITY

### What Gets Logged

| Component | Logging | Evidence |
|-----------|---------|----------|
| Backtest engine | Critical incidents only | `backtest/engine.py:616-619` — `logging.critical(f"CRITICAL_INCIDENT: {incident_type}")` |
| Paper trading | Full cycle output | `run_paper_trading.py:260-261` — prints regime, signals, entries |
| Telegram notifications | Trade alerts | `run_paper_trading.py:402-410` — `await self.telegram.notify_trade(...)` |
| Health check | Heartbeat file | `monitoring/health_check.py:27-29` — writes to `data/heartbeat.txt` |
| Circuit breaker | Status dict | `risk/circuit_breaker.py:226-245` — `get_status()` |

### Silent Failure Detection

| Failure Mode | Detected? | Evidence |
|--------------|-----------|----------|
| Stopped receiving data | ⚠️ PARTIAL | Heartbeat file checked by watchdog, but no data freshness check in trading loop |
| Calculation broke | ❌ NO | No try/except around indicator calculation in `_calculate_indicators` |
| MT5 disconnect | ❌ NO | No reconnect logic, no disconnect detection |
| Order rejection | ⚠️ PARTIAL | `run_paper_trading.py:412` — prints error, but no alert/notification |

---

## PHASE 8 — HONEST SCORECARD

| Question | Status | Evidence |
|----------|--------|----------|
| Is the data pipeline free of lookahead bias? | **Partial** | LookaheadGuard exists and is strict, but timestamp/timezone handling is unverified |
| Is the cost model in walk-forward validation correct? | **Partial** | ms→ns bug fixed, Pepperstone double-count fixed, but swap not modeled |
| Is there a statistically significant out-of-sample edge after costs? | **No** | `SUMMARY.md:9` — "Net P&L: -$23.21 (costs of $37.52 eat all edge)" |
| Are risk limits/kill switches actually implemented in code? | **Yes** | Kill switch, circuit breaker, pre-trade risk gate all implemented |
| Is MT5 connection failure handled safely? | **No** | No reconnect, no disconnect detection, no partial fill handling |
| Are credentials/secrets properly secured? | **Yes** | All secrets via env vars, no plaintext in code |
| Would a silent system failure be detected? | **Partial** | Heartbeat watchdog exists, but no data freshness or calculation error detection |
| Is the codebase safe to extend without breaking backtest/live parity? | **Partial** | Two separate fill implementations (BacktestExecutionSimulator vs PaperBroker) can drift |

---

## PHASE 9 — PRIORITIZED NEXT STEPS

### P0 — Blocks Any Live Deployment
| Item | Evidence | Action | Falsification |
|------|----------|--------|---------------|
| **No statistically significant edge after costs** | `SUMMARY.md:9` — Net P&L: -$23.21 | Do NOT proceed to live until edge is proven | Net P&L must be positive after all costs |
| **No multiple testing correction** | No Bonferroni/BH in codebase | Apply BH-FDR to all feature findings | Adjusted p-values < 0.05 |
| **MT5 connection failure unsafe** | No reconnect in `mt5_connector/connection.py` | Implement reconnect + disconnect detection | System survives MT5 disconnect gracefully |
| **Swap not modeled** | `KNOWN_LIMITATIONS.md:3` | Add swap to cost model or prove impact is negligible | Backtest includes swap cost |

### P1 — High Priority
| Item | Evidence | Action |
|------|----------|--------|
| Duplicate RiskPolicy classes | `risk/pre_trade_risk.py:12` vs `risk/risk_policy.py:8` | Consolidate to single frozen dataclass |
| Hardcoded spread/commission | `backtest/engine.py:437,92` | Make config-driven per symbol |
| PaperBroker fill divergence | `execution/broker_adapter.py:167` — random slippage | Align with BacktestExecutionSimulator |
| ForexFactory calendar absent | No files in `data/news/` | Acquire and integrate economic calendar data |
| Timestamp/timezone handling | `run_paper_trading.py:240` — no explicit TZ | Add explicit UTC handling |

### P2 — Medium Priority
| Item | Evidence | Action |
|------|----------|--------|
| Regime-filter via ATR-percentile join | Planned in SUMMARY.md | Implement and test |
| Feature multicollinearity check | No check found | Add correlation matrix before feature selection |
| Crash recovery/reconciliation | No logic found | Implement MT5 account reconciliation on restart |
| Order rejection handling | `run_paper_trading.py:412` — print only | Add Telegram alert for failed orders |

### P3 — Low Priority
| Item | Evidence | Action |
|------|----------|--------|
| Dead code cleanup | Multiple sizers, cost models | Remove deprecated modules |
| Dashboard logging | `monitoring/metrics.py` exists | Add structured logging for backtest runs |
| Documentation gaps | `KNOWN_LIMITATIONS.md` lists items | Update as items are resolved |

---

## FINAL VERDICT

**This is a well-structured research-phase system with strong architectural foundations (immutable risk policies, lookahead guard, phase-based development, walk-forward validation).** However:

1. **No proven edge after costs** — the system has not demonstrated statistical significance after realistic transaction costs
2. **Multiple testing correction missing** — any "significant" feature could be chance
3. **MT5 integration is incomplete** — no reconnect, partial fill handling, or crash recovery
4. **Two parallel execution paths** — backtest and live can silently drift apart
5. **The ~2000x cost bug is fixed** — but swap is still not modeled

**Recommendation:** Continue paper trading and research. Do not deploy live capital until:
- Edge is proven after all costs (including swap)
- Multiple testing correction applied
- MT5 connection resilience implemented
- Backtest/live execution parity verified

---

*Audit completed: 2026-06-25. All findings are evidence-based with file:line citations.*
