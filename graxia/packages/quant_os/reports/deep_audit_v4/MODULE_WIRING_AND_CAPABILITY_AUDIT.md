# MODULE WIRING AND CAPABILITY AUDIT

Generated: 2026-07-05 | Version: quant_os 0.2.0-dev

---

## 0.10 Module Wiring Audit

Verdict: WIRED | ORPHANED | PARTIALLY WIRED
All claims with file:line citations.

---

### 1. RegimeDetector (regime/__init__.py): WIRED

Module: regime/__init__.py:20-228 (228 lines)
ADX-based detector: TREND_UP, TREND_DOWN, RANGE, UNCLEAR

CALL SITES:
  run_paper_trading.py:30 - from regime import RegimeDetector
  run_paper_trading.py:74 - self.regime_detector = RegimeDetector()
  run_paper_trading.py:491 - self.regime_detector.detect(closes, highs, lows)
  run_paper_trading.py:494 - if regime.regime == UNCLEAR: return

GATING: Trades are skipped when UNCLEAR (line 494-495).
This is the ONLY entry point using this detector.
Test: regime/test_detector.py (145 lines)

---

### 2. RiskOverlay (regime/risk_overlay.py): WIRED

Module: regime/risk_overlay.py:1-309 (309 lines)
Enforces: position sizing, daily/weekly loss, kill switch, cooldown
Persistent state: JSON file disk persistence for kill switch survival

CALL SITES:
  run_paper_trading.py:36 - from regime.risk_overlay import RiskOverlay
  run_paper_trading.py:75 - self.risk_overlay = RiskOverlay(initial_balance=...)
  run_paper_trading.py:548 - self.risk_overlay.approve(risk_amount=..., stop_distance=..., current_balance=...)
  regime/test_risk.py:5 - test import

GATING: Line 553-555: if not risk_result.approved: continue
Test: regime/test_risk.py (136 lines)

---

### 3. Alpha RegimeDetector (alpha/regime_detector.py): ORPHANED

Module: alpha/regime_detector.py:1-535 (535 lines)
Asset-class regime detector (metals/crypto/forex/indices)
Position multipliers by regime (e.g., CRISIS=0.2x, BULL=1.0x)

CALL SITES:
  alpha/engine.py:254 - from .regime_detector import RegimeDetector
  alpha/engine.py:338 - self.regime_detector.detect(data, asset_class)

VERDICT: [ORPHANED] -- alpha/engine.py imports and uses it, but alpha/engine.py
is NOT called from any entry point. grep for alpha.engine imports found none.
No strategy, ensemble, or entry point references alpha.engine.
This is a SECOND, MORE SOPHISTICATED regime detector that is fully coded but
never wired into production. The regime/__init__.py simpler detector is used instead.
Test: NONE (no test file for alpha/regime_detector.py)

---

### 4. Ensemble+Regime Wiring (strategies/ensemble.py): PARTIALLY WIRED

Module: strategies/ensemble.py:1-534 (534 lines)
Multi-strategy ensemble with dynamic weighting. Does NOT import or call
any RegimeDetector. The ensemble.get_ensemble_signal() method accepts a regime
parameter but does not internally gate on it.

WIRING ANALYSIS:
  strategies/ensemble.py:15 - get_ensemble_signal(symbol, ohlcv, indicators, regime, **kw) -> Signal
  The regime parameter is PASSED IN but the ensemble does not validate or
  gate on it internally. Responsibility is on the caller.

  strategies/mtm.py, strategies/mrb.py, strategies/mlb.py: Do NOT import
  regime detection. Do NOT self-gate on regime.

  gold_bot/run_paper.py: Uses GoldBotEngine, not RegimeDetector.
  gold_bot strategies (13): Score-based, no regime gating.

VERDICT: [PARTIALLY WIRED] -- The regime detector IS wired in run_paper_trading.py
but IS NOT wired in ensemble.py, gold_bot strategies, or the API entry points.
The alpha/regime_detector.py is fully coded but ORPHANED.
There is a SECOND, less sophisticated regime detector in regime/__init__.py
that IS wired into the paper trading pipeline only.

Test: strategies/ lacks dedicated regime integration tests.

---

### 5. SwapCost (core/risk/swap_cost.py): WIRED

Module: core/risk/swap_cost.py (150+ lines)
Estimate overnight swap costs from broker rates

CALL SITES:
  backtest/engine.py:77 - from core.risk.swap_cost import get_swap_cost_for_trade
  backtest/engine.py:1110 - swap_cost = self._calculate_swap_cost(...)
  backtest/engine.py:1118 - pnl -= total_fees + swap_cost
  scripts/tsm_ensemble_backtest.py:211 - df[swap_cost] = 0.0 (inline calc)
  scripts/backtest_cost_aware.py:240 - swap_cost calculation

VERDICT: [WIRED] -- Swap costs are subtracted from backtest PnL.
Test: tests/test_swap_cost_verification.py, tests/chaos/test_core_untested.py:1110

---

### 6. SlippageModel (risk/slippage_model.py and core/slippage_model.py): PARTIALLY WIRED

Two implementations exist:
  core/slippage_model.py:92 - SlippageModel class (usage example at line 13-14)
  risk/slippage_model.py:70 - SlippageModel with session/volatility classification

CALL SITES:
  core/slippage_model.py: No production call sites found beyond tests
  risk/slippage_model.py: tests/test_risk_edge_cases.py:982
  backtest/engine.py: Does NOT import risk/slippage_model.py
  run_paper_trading.py: Does NOT import slippage model

VERDICT: [PARTIALLY WIRED] -- Two implementations exist but neither is clearly
integrated into the backtest engine or paper trading pipeline. The backtest
uses a simple config.slippage_pips constant (backtest/engine.py line 76 context).
Test: tests/test_core_modules.py:418, tests/test_risk_edge_cases.py:982

---

### 7. MultiBrokerPolicy (governance/multi_broker_policy.py): ORPHANED

Module: governance/multi_broker_policy.py:1-32 (32 lines)
BrokerRequirements dataclass with validate() method.
MultiBrokerPolicy with add_broker() method.

CALL SITES:
  tests/test_phase_11_expansion.py:3 - import MultiBrokerPolicy, BrokerRequirements
  tests/test_phase_11_integration.py:3 - import MultiBrokerPolicy, BrokerRequirements

VERDICT: [ORPHANED] -- No production code imports this module.
Only test files reference it. The api/main.py and execution/adapters/manager.py
use BrokerManager which has its own failover logic, not MultiBrokerPolicy.

BrokerManager._failover() (execution/broker_adapter.py:593): Uses a simple
loop over fallbacks list. Only fallback is PaperBroker.

execution/adapters/manager.py:97 _failover(): Similarly simple fallback.

Current config (core/config.py:37-39): primary=ic_markets, fallbacks=pepperstone,xm
But actual broker initialization (broker_adapter.py:549): Only PaperBroker or
MT5BrokerAdapter connect. BrokerManager preferentially uses PaperBroker.

Test: tests/test_phase_11_expansion.py, tests/test_phase_11_integration.py

---

### 8. NewsBlackout (core/news_blackout.py): WIRED

Module: core/news_blackout.py:1-113 (113 lines)
Blocks trading during HIGH/CRISIS news events.

CALL SITES:
  core/signal_gateway.py:24 - from .news_blackout import NewsBlackout
  core/signal_gateway.py:174 - news_blackout parameter
  core/signal_gateway.py:231 - if self._news_blackout.is_blocked():
  core/production_readiness.py:172 - from core.news_blackout import NewsBlackout
  risk/engine.py:197 - news_blackout parameter
  risk/engine.py:217 - if self._news_blackout.is_blocked():
  core/agents/autonomous_engine.py:139 - guards_checked.append(news_blackout)
  tests/chaos/test_news_blackout_integration.py - integration tests
  tests/chaos/test_autonomous_engine.py:179 - TestNewsBlackout class

VERDICT: [WIRED] -- Signal gateway and risk engine both check news blackout
before allowing trades. The paper_trade_config.json line 119-132 also
specifies news_filter parameters (30min pre-block, 15min post-block).

---

### 9. DriftDetector / Auto-Retrain (ml/pipeline.py, ml/drift_monitor.py): PARTIALLY WIRED

Module: ml/pipeline.py:509 - DriftDetector class (window_size=50, threshold=0.10)
Module: ml/drift_monitor.py - DriftMonitor class

CALL SITES:
  run_ml_train.py:109 - detector = DriftDetector(window_size=50, threshold=0.10)
  api/signal_service.py:521 - from ml.drift_monitor import DriftMonitor
  scripts/auto_retrain.py - Scheduled auto-retrain script

VERDICT: [PARTIALLY WIRED] -- DriftDetector EXISTS and has a MANUAL retrain script
(scripts/auto_retrain.py). However, retrain is NOT auto-triggered in the live
paper trading loop. It requires:
  1. Manual invocation: python scripts/auto_retrain.py
  2. Docker cron: docker/trainer/crontab (supercronic scheduled)
  3. Signal service has drift monitor but may not auto-retrain

The core.config ml_retrain_interval_days = 7 (line 105) is set but
no automatic trigger in run_paper_trading.py or gold_bot/run_paper.py.

Test: tests/chaos/test_new_components.py:339

---

### 10. Additional Orphaned/Partially-Wired Modules

---

**core/slippage_model.py** [ORPHANED]:
  No call sites found. risk/slippage_model.py is the wired one.

**risk/market_session_guard.py** [UNVERIFIED]:
  Exists but call sites not confirmed.

**broker/mt5_gateway.py** [WIRED - READ ONLY]:
  broker/mt5_gateway.py:207 - must NEVER contain order_send
  broker/mt5_gateway.py:213 - Guard that asserts no order_send exists
  Used by: shadow/*, tests/test_mt5_gateway.py:503
  This is a READ-ONLY MT5 interface for market data.

**gold_bot/mt5_adapter.py** [WIRED - Linux Paper Only]:
  gold_bot/mt5_adapter.py:214 - order_send returns paper mode only
  Uses yfinance, not real MT5. For Linux compatibility.
  Used by: gold_bot/run_linux.py, gold_bot/run_multi_linux.py

**execution/adapters/mt5.py** [WIRED - LIVE CAPABLE]:
  execution/adapters/mt5.py:209 - result = mt5.order_send(request)
  execution/adapters/mt5.py:252 - result = mt5.order_send(request)
  This IS the live-order-capable MT5 adapter.
  Used by: execution/adapters/manager.py via BrokerManager

**execution/broker_adapter.py MT5BrokerAdapter** [WIRED - LIVE CAPABLE]:
  execution/broker_adapter.py:485 - result = self.mt5.order_send(request)
  execution/broker_adapter.py:509 - result = self.mt5.order_send(request)
  DEPRECATED (line 3-15) but still has live-order capabilities.

---

### SUMMARY: Module Wiring Verdicts

| Module | Verdict | Wired To |
|--------|---------|----------|
| regime/RegimeDetector | WIRED | run_paper_trading.py only |
| regime/RiskOverlay | WIRED | run_paper_trading.py only |
| alpha/RegimeDetector | ORPHANED | alpha/engine.py (no entry point) |
| strategies/ensemble | PARTIALLY | Does not gate on regime |
| core/risk/swap_cost | WIRED | backtest/engine.py |
| risk/slippage_model | PARTIALLY | Tests only, not in backtest |
| core/slippage_model | ORPHANED | No production call sites |
| governance/multi_broker_policy | ORPHANED | Tests only |
| core/news_blackout | WIRED | signal_gateway, risk/engine |
| ml/DriftDetector | PARTIALLY | Manual script, not auto |
| broker/mt5_gateway | WIRED (RO) | shadow, tests |
| execution/adapters/mt5 | WIRED (LIVE) | BrokerManager |
| gold_bot/mt5_adapter | WIRED (Paper) | Linux gold_bot |

---

## 0.11 Live-Order-Capability Ground-Truth Check

### CHALLENGE: Could any currently-runnable command path submit a real order RIGHT NOW?

---

### Analysis

Three separate MT5-order-capable modules exist:

1. execution/adapters/mt5.py (lines 209, 252, 331, 399, 476):
   Uses mt5.order_send() -- REAL order submission.
   Canonical MT5 adapter for Pepperstone.

2. execution/broker_adapter.py MT5BrokerAdapter (lines 485, 509):
   Uses self.mt5.order_send() -- REAL order submission.
   DEPRECATED but still importable.

3. gold_bot/mt5_adapter.py (line 214):
   order_send returns OrderSendResult(retcode=10009, comment=Paper mode)
   PAPER ONLY -- returns hardcoded fake result.

### Entry Point Trace

---

#### Entry Point: run_paper_trading.py

  run_paper_trading.py:28 - from execution.broker_adapter import PaperBroker
  run_paper_trading.py:61 - self.broker = PaperBroker()
  run_paper_trading.py:584 - result = await self.broker.place_order(order)

  PaperBroker.place_order() (broker_adapter.py:176):
    Simulates fills in memory. NO mt5.order_send().
    CONFIRMED: PaperBroker CANNOT submit real orders.

#### Entry Point: gold_bot/run_paper.py

  gold_bot/run_paper.py:96 - self.broker = None  # PaperBroker
  Uses PaperBroker. CANNOT submit real orders.

#### Entry Point: start_bot.ps1 -> gold_bot/run_paper.py

  Same as above. PaperBroker only.

#### Entry Point: api/main.py

  api/main.py:58 - broker_manager = BrokerManager.from_config()
  api/main.py:78 - app.state.broker_manager.active.disconnect()

  BrokerManager.from_config() (execution/adapters/manager.py:44):
    Reads config.trading_mode. Default: TradingMode.PAPER.
    In PAPER mode, creates PaperBroker.
    In LIVE_MICRO/LIVE_LIMITED/LIVE_CONTROLLED mode, could create MT5 adapter.

  CRITICAL PATH:
    If TRADING_MODE env var is set to LIVE_MICRO, LIVE_LIMITED, or LIVE_CONTROLLED,
    AND LIVE_TRADING_ENABLED=true,
    AND MT5 credentials are configured,
    THEN BrokerManager COULD connect via execution/adapters/mt5.py
    which DOES call mt5.order_send() REAL order submission.

#### Entry Point: gold_bot/run.py

  gold_bot/run.py:22 - from gold_bot.core.engine import GoldBotEngine
  Default BotConfig with no mode switch.
  GoldBotEngine probably uses gold_bot/mt5_adapter.py (paper only).
  To verify: gold_bot/core/engine.py needs inspection.

#### Entry Point: docker-compose

  graxia-executor (docker-compose.yml:225):
    env: RISK_PER_TRADE=0.0025, INITIAL_BALANCE=100000, SYMBOL=XAUUSD
    Polls graxia-signal for predictions, executes on PaperBroker.
    Does NOT have MT5 access (container is isolated).

---

### RESOLUTION

CONFIRMED READ-ONLY (Paper Only) under DEFAULT configuration:

  - run_paper_trading.py: Hardcodes TradingMode.PAPER (line 778)
  - run_paper_trading.py: Hardcodes live_trading_enabled = False (line 779)
  - gold_bot/run_paper.py: Uses PaperBroker only
  - gold_bot/mt5_adapter.py: order_send returns paper mode
  - .env.example: TRADING_MODE=paper (line 28)
  - core/config.py: Default TradingMode.PAPER (line 20)

HOWEVER -- THE FOLLOWING PATH EXISTS FOR LIVE ORDER SUBMISSION:

  api/main.py -> BrokerManager.from_config() -> execution/adapters/mt5.py
  If TRADING_MODE is changed to LIVE_MICRO/LIVE_LIMITED/LIVE_CONTROLLED
  and LIVE_TRADING_ENABLED=true, live orders WOULD be submitted.

  Also: start_bot.ps1 line 9 contains HARDCODED MT5 credentials:
    /login:61547941 /password:Graxia-12345Ghr /server:Pepperstone-Demo

  WARNING: The live-order-capable adapter (execution/adapters/mt5.py) is
  FULLY FUNCTIONAL and only a config change away from live trading.
  Multiple guardrails exist (TradingMode.PAPER default, live_trading_enabled=False)
  but NO HARDWARE/SYSTEM LEVEL barrier prevents switching to live mode.

EVIDENCE:
  - execution/adapters/mt5.py:209: result = mt5.order_send(request)
  - core/config.py:150: mode_str = os.getenv(TRADING_MODE, PAPER)
  - run_paper_trading.py:778: config.trading_mode = TradingMode.PAPER

---
