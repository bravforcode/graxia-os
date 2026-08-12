# G0 CANONICAL RUNTIME MAP — Quant OS

**Generated:** 2026-06-22
**Scope:** Every runtime path from CSV/tick → report
**Rule:** One canonical module per responsibility. Non-canonical modules get status labels.

---

## Overview

There are **two independent runtime paths** in this codebase:

1. **Backtest Path** — CSV/MT5 historical data → backtest engine → metrics report
2. **Live/Paper Trading Path** — MT5 tick/bar data → strategy → signal → risk → execution → trade ledger

Plus a **Gold Bot sub-system** that bridges both (backtest via adapter, live via its own engine).

---

## EDGE MAP: Backtest Runtime Path

### Edge 1: CSV Tick → Data Loader
| Field | Value |
|-------|-------|
| **Module** | `backtest/data_loader.py` |
| **Function** | `load_csv_data()` / `load_yahoo_csv()` / `load_mt5_data()` / `generate_sample_data()` |
| **Caller** | `run_backtest.py` / `run_backtest_real.py` / tests |
| **Callee** | Returns `Tuple[Dict[str, List], List[datetime]]` — raw OHLCV dict + timestamps |
| **Test coverage** | `tests/test_load.py` — ✅ ACTIVE |
| **Status** | **ACTIVE** |

### Edge 2: Data Loader → Backtest Engine
| Field | Value |
|-------|-------|
| **Module** | `backtest/engine.py` |
| **Function** | `BacktestEngine.load_data(data, timestamps)` |
| **Caller** | `run_backtest.py` step2_run_backtest / step3_run_all_strategies |
| **Callee** | Stores `self.ohlcv_data` and `self.timestamps`; validates schema |
| **Test coverage** | `tests/test_strategies.py`, `tests/test_execution.py` — ✅ ACTIVE |
| **Status** | **ACTIVE** |

### Edge 3: Backtest Engine → MTF Cursor
| Field | Value |
|-------|-------|
| **Module** | `backtest/mtf_cursor.py` |
| **Function** | `MultiTimeframeCursor(d1_data, d1_ts, h1_data, h1_ts, m15_data, m15_ts)` |
| **Caller** | `BacktestEngine.set_multi_timeframe()` → creates cursor; `BacktestEngine.run()` → calls `cursor.slice_as_of(current_time)` |
| **Callee** | Returns `Dict[str, Dict[str, List]]` — point-in-time sliced multi-TF data |
| **Test coverage** | `tests/test_mtf_leak.py` — ✅ ACTIVE |
| **Status** | **ACTIVE** |

### Edge 4: MTF Cursor → Strategy Adapter (Gold Bot path)
| Field | Value |
|-------|-------|
| **Module** | `gold_bot/strategy_adapter.py` |
| **Class** | `GoldStrategyAdapter` |
| **Function** | `_set_mtf_cursor(sliced_data)` + `generate_signal(symbol, ohlcv_data, ...)` |
| **Caller** | `BacktestEngine.run()` — line 217-219: injects sliced data into strategy via `strategy._set_mtf_cursor(sliced)` |
| **Callee** | Calls `self.gold_strategy.analyze(nested_data, current_price, symbol)` on the wrapped GoldBot strategy |
| **Test coverage** | `tests/run_all_13_strategies_real.py`, `tests/outofsample_xauusd.py` — ✅ ACTIVE |
| **Status** | **ACTIVE** |

### Edge 5: MTF Cursor → Canonical Strategy (backtest path)
| Field | Value |
|-------|-------|
| **Module** | `strategies/base.py` → `strategies/mtm.py` / `mrb.py` / `mlb.py` / `ensemble.py` |
| **Function** | `Strategy.generate_signal(symbol, ohlcv_data, indicators, regime)` |
| **Caller** | `BacktestEngine.run()` — line 221-227: calls `self.strategy.generate_signal(...)` |
| **Callee** | Returns `Optional[Signal]` with entry/SL/TP/confidence |
| **Test coverage** | `tests/test_strategies.py` — ✅ ACTIVE |
| **Status** | **ACTIVE** |

### Edge 6: Strategy Signal → Backtest Execution
| Field | Value |
|-------|-------|
| **Module** | `backtest/engine.py` |
| **Function** | `BacktestEngine._execute_signal(signal, current_price, current_time)` |
| **Caller** | `BacktestEngine.run()` — line 230-231: if signal is BUY/SELL, execute |
| **Callee** | Creates `BacktestPosition`, applies slippage/commission, updates balance |
| **Test coverage** | `tests/test_strategies.py` — ✅ ACTIVE |
| **Status** | **ACTIVE** |

### Edge 7: Backtest Engine → Metrics/Report
| Field | Value |
|-------|-------|
| **Module** | `backtest/metrics.py` |
| **Function** | `calculate_metrics(trades, initial_capital, equity_curve)` |
| **Caller** | `BacktestEngine._build_results()` — line 494: calculates all metrics |
| **Callee** | Returns `BacktestMetrics` dataclass (Sharpe, Sortino, Calmar, win rate, PF, etc.) |
| **Test coverage** | `tests/test_strategies.py` — ✅ ACTIVE |
| **Status** | **ACTIVE** |

### Edge 8: Backtest Engine → Walk-Forward
| Field | Value |
|-------|-------|
| **Module** | `backtest/walk_forward.py` |
| **Class** | `WalkForwardAnalyzer` |
| **Function** | `analyze(data, timestamps, n_windows, optimize_func)` |
| **Caller** | `tests/run_holdout_and_deflated.py` / `tests/outofsample_xauusd.py` |
| **Callee** | Creates multiple BacktestEngine instances for IS/OOS windows |
| **Test coverage** | `tests/run_holdout_and_deflated.py` — ✅ ACTIVE |
| **Status** | **ACTIVE** |

### Edge 9: Backtest Engine → Lookahead Guard
| Field | Value |
|-------|-------|
| **Module** | `core/lookahead_guard.py` |
| **Class** | `LookaheadGuard` |
| **Function** | `initialize(total_bars)`, `advance()`, `get_slice(data)` |
| **Caller** | `BacktestEngine.run()` — line 198-199: guard created; line 204: advance; line 214: get_slice |
| **Callee** | Returns data sliced to current index; raises `LookaheadViolation` if strict |
| **Test coverage** | `tests/test_lookahead_regression.py` — ✅ ACTIVE |
| **Status** | **ACTIVE** |

---

## EDGE MAP: Live/Paper Trading Runtime Path

### Edge 10: MT5 Tick → Data Feed
| Field | Value |
|-------|-------|
| **Module** | `data/feed.py` |
| **Class** | `MT5DataFeed` (primary) / `YahooDataFeed` (fallback) |
| **Function** | `get_tick(symbol)` → `Tick`; `get_bars(symbol, timeframe, count)` → `List[Bar]` |
| **Caller** | `gold_bot/core/engine.py` `_fetch_data()` / `DataFeedManager` |
| **Callee** | Returns `Tick` (bid/ask/timestamp) or `List[Bar]` (OHLCV) |
| **Test coverage** | None explicit — ❌ UNKNOWN |
| **Status** | **ACTIVE** (live path) |

### Edge 11: Data Feed → DataFeedManager (fallback chain)
| Field | Value |
|-------|-------|
| **Module** | `data/feed.py` |
| **Class** | `DataFeedManager` |
| **Function** | `connect()`, `get_tick(symbol)`, `get_bars(symbol, tf, count)` |
| **Caller** | Would be called by live trading engine (not yet wired) |
| **Callee** | Tries feeds in priority order (MT5 > Yahoo), fail-loud on all failure |
| **Test coverage** | None — ❌ UNKNOWN |
| **Status** | **STUB** — implemented but not wired into main live path |

### Edge 12: Data Feed → Data Quality Gate
| Field | Value |
|-------|-------|
| **Module** | `data/quality_gate.py` |
| **Class** | `DataQualityGate` |
| **Function** | `validate_ohlcv(data)` → `List[QualityCheckResult]` |
| **Caller** | Would be called before strategy execution (not yet wired) |
| **Callee** | Checks missing timestamps, duplicates, outliers, stale quotes, zero volume |
| **Test coverage** | None — ❌ UNKNOWN |
| **Status** | **STUB** — implemented but not wired into main path |

### Edge 13: Signal → Risk Engine (legacy path)
| Field | Value |
|-------|-------|
| **Module** | `risk/engine.py` |
| **Class** | `RiskEngine` |
| **Function** | `check_order(order)` → `RiskCheckResult` |
| **Caller** | `execution/manager.py` `OrderManager.submit_order()` — line 115-124 |
| **Callee** | Runs 13 pre-trade checks (kill switch, mode, symbol, position size, exposure, daily loss, etc.) |
| **Test coverage** | `tests/test_phase_2a.py` — ✅ ACTIVE |
| **Status** | **LEGACY** — superseded by `pre_trade_risk.py` for new code; still wired into `OrderManager` |

### Edge 14: Signal → Pre-Trade Risk (canonical path)
| Field | Value |
|-------|-------|
| **Module** | `risk/pre_trade_risk.py` |
| **Function** | `pre_trade_check(sizing_result, risk_policy, risk_ledger, account_equity, kill_switch)` |
| **Caller** | Should be called by execution pipeline (not yet wired into OrderManager) |
| **Callee** | Returns `RiskCheckResult(approved, reasons)` checking kill switch, daily/weekly/drawdown, position count, order rate |
| **Test coverage** | `tests/test_phase_2b.py` — ✅ ACTIVE |
| **Status** | **ACTIVE** — canonical, but not yet wired into OrderManager |

### Edge 15: Signal → Position Sizing (canonical)
| Field | Value |
|-------|-------|
| **Module** | `risk/position_sizer_v2.py` |
| **Function** | `size_position(symbol, side, entry_price, stop_loss, equity, contract_spec, risk_policy, ...)` |
| **Caller** | Should be called before `pre_trade_check` |
| **Callee** | Returns `SizingResult` with volume, risk_amount, margin_estimate, rejected flag |
| **Test coverage** | `tests/test_phase_2b.py` — ✅ ACTIVE |
| **Status** | **ACTIVE** — canonical |

### Edge 16: Signal → Position Sizing (legacy)
| Field | Value |
|-------|-------|
| **Module** | `risk/position_sizer.py` |
| **Classes** | `FixedFractionalSizer` / `KellySizer` / `ATRSizer` / `AntiMartingaleSizer` |
| **Caller** | `tests/test_strategies.py` / `tests/test_position_sizer_numeric.py` |
| **Callee** | Returns `PositionSizeResult` with lots, units, notional |
| **Test coverage** | `tests/test_strategies.py`, `tests/test_position_sizer_numeric.py` — ✅ ACTIVE |
| **Status** | **LEGACY** — old sizer with hardcoded methods; `position_sizer_v2.py` is canonical |

### Edge 17: Risk → Kill Switch
| Field | Value |
|-------|-------|
| **Module** | `risk/kill_switch.py` |
| **Class** | `KillSwitch` |
| **Function** | `is_active()`, `activate(reason)`, `deactivate(reason, authorized_by)` |
| **Caller** | `risk/pre_trade_risk.py` `pre_trade_check()` / `risk/engine.py` `_check_kill_switch()` / `execution/manager.py` |
| **Callee** | Returns bool; persists to `data/kill_switch_state.json` |
| **Test coverage** | None explicit — ❌ UNKNOWN |
| **Status** | **ACTIVE** |

### Edge 18: Risk → Risk Ledger
| Field | Value |
|-------|-------|
| **Module** | `risk/risk_ledger.py` |
| **Class** | `RiskLedger` |
| **Function** | `record_trade(pnl, symbol, volume)`, `record_order()`, `set_open_positions(...)` |
| **Caller** | `risk/pre_trade_risk.py` `pre_trade_check()` reads daily/weekly loss from ledger |
| **Callee** | Reads/writes `data/risk_ledger.json` |
| **Test coverage** | `tests/test_phase_2b.py` `test_risk_ledger_daily_tracking` — ✅ ACTIVE |
| **Status** | **ACTIVE** |

### Edge 19: Risk → Risk Policy
| Field | Value |
|-------|-------|
| **Module** | `risk/risk_policy.py` |
| **Class** | `RiskPolicy` (frozen dataclass) |
| **Purpose** | Canonical risk limits in basis points (10 bps = 0.10%) |
| **Caller** | `risk/pre_trade_risk.py`, `risk/position_sizer_v2.py` |
| **Callee** | Immutable config; provides `risk_per_trade_fraction`, `max_daily_loss_fraction` etc. |
| **Test coverage** | `tests/test_phase_2a.py` — ✅ ACTIVE |
| **Status** | **ACTIVE** — canonical |

### Edge 20: Execution → Order State Machine (canonical)
| Field | Value |
|-------|-------|
| **Module** | `execution/order_state_machine.py` |
| **Class** | `OrderStateMachine` (16 states) |
| **Transitions** | `SIGNAL_CREATED → RISK_CHECKED → ORDER_PRECHECKED → ORDER_SUBMITTED → ORDER_ACKNOWLEDGED → PARTIAL_FILL → FILLED → PROTECTIVE_STOPS_PENDING → PROTECTIVE_STOPS_VERIFIED → POSITION_RECONCILED → CLOSED → DEAL_RECONCILED → AUDITED` |
| **Caller** | Should be used by execution pipeline |
| **Callee** | Raises `OrderStateError` on invalid transitions |
| **Test coverage** | `tests/test_phase_3_order.py` — ✅ ACTIVE (15 tests) |
| **Status** | **ACTIVE** — canonical |

### Edge 21: Execution → Order (legacy, still wired)
| Field | Value |
|-------|-------|
| **Module** | `execution/order.py` |
| **Class** | `Order` + `OrderStateMachine` (inline, 10 states) |
| **Function** | `create_order(...)`, state transitions via `transition()` / `fill()` / `cancel()` |
| **Caller** | `execution/manager.py` `OrderManager.submit_order()` / `execution/broker_adapter.py` |
| **Callee** | Uses inline state machine with `OrderStatus` enum |
| **Test coverage** | `tests/test_execution.py` — ✅ ACTIVE |
| **Status** | **LEGACY** — older Order class with inline state; `order_state_machine.py` is canonical |

### Edge 22: Execution → Order Manager
| Field | Value |
|-------|-------|
| **Module** | `execution/manager.py` |
| **Class** | `OrderManager` |
| **Function** | `submit_order(...)`, `approve_order(...)`, `cancel_order(...)` |
| **Caller** | `api/webhook.py` `tradingview_webhook()` / `gold_bot/core/engine.py` |
| **Callee** | Orchestrates: kill switch → create order → idempotency → validate → risk check → compliance → human approval (MICRO) → broker submit |
| **Test coverage** | None explicit for manager itself — ❌ UNKNOWN |
| **Status** | **ACTIVE** |

### Edge 23: Execution → Broker Adapter
| Field | Value |
|-------|-------|
| **Module** | `execution/broker_adapter.py` |
| **Classes** | `BrokerAdapter` (ABC) / `PaperBroker` / `MT5BrokerAdapter` / `BrokerManager` |
| **Function** | `place_order(order)` → `BrokerOrderResponse`; `get_price(symbol)`, `get_account()` |
| **Caller** | `execution/manager.py` `_submit_to_broker()` |
| **Callee** | PaperBroker simulates fills with slippage/commission; MT5BrokerAdapter sends to MT5 terminal |
| **Test coverage** | `tests/test_execution.py` — ✅ ACTIVE |
| **Status** | **ACTIVE** |

### Edge 24: Execution → Fill Model
| Field | Value |
|-------|-------|
| **Module** | `execution/fill_model.py` |
| **Functions** | `simulate_entry(req, bid, ask, spread)`, `simulate_exit(side, bid, ask, slippage)`, `check_sl_tp_trigger(...)`, `can_fill_on_info_candle(...)` |
| **Caller** | `execution/conservative_bar_model.py` |
| **Callee** | Returns `FillResult` with entry_price, sl_cost, execution_quality, is_ambiguous |
| **Test coverage** | `tests/test_phase_3.py` `test_signal_cannot_fill_on_same_bar` — ✅ ACTIVE |
| **Status** | **ACTIVE** |

### Edge 25: Execution → Conservative Bar Model
| Field | Value |
|-------|-------|
| **Module** | `execution/conservative_bar_model.py` |
| **Functions** | `estimate_bid_ask_from_bar(...)`, `simulate_bar_execution(bars, signals, ...)`, `next_bar_fill(...)` |
| **Caller** | Backtesting (when tick data unavailable) |
| **Callee** | Uses `fill_model.simulate_entry()` for fills; enforces next-bar fill timing |
| **Test coverage** | `tests/test_phase_3.py` — ✅ ACTIVE |
| **Status** | **ACTIVE** |

### Edge 26: Execution → Cost Model
| Field | Value |
|-------|-------|
| **Module** | `execution/cost_model.py` |
| **Function** | `calculate_trade_costs(...)`, `run_cost_stress_matrix(...)` |
| **Caller** | Backtest analysis |
| **Callee** | Returns `TradeCosts` with spread_cost, slippage_cost, commission under stress scenarios |
| **Test coverage** | None — ❌ UNKNOWN |
| **Status** | **ACTIVE** |

### Edge 27: Execution → Trade Ledger
| Field | Value |
|-------|-------|
| **Module** | `execution/trade_ledger.py` |
| **Class** | `TradeLedger` |
| **Function** | `record_trade(TradeRecord)`, `get_trades(symbol, date)`, `get_summary()`, `ledger_hash()` |
| **Caller** | Should be called after fill; `tests/test_phase_3_order.py` |
| **Callee** | Writes individual JSON files per trade; computes SHA-256 ledger hash |
| **Test coverage** | `tests/test_phase_3_order.py` `test_trade_ledger_record_and_retrieve` / `test_trade_ledger_hash_deterministic` / `test_trade_ledger_summary` — ✅ ACTIVE |
| **Status** | **ACTIVE** |

### Edge 28: Execution → Idempotency Checker
| Field | Value |
|-------|-------|
| **Module** | `execution/idempotency.py` |
| **Class** | `IdempotencyChecker` / `WindowedIdempotencyChecker` |
| **Function** | `check_and_record(idempotency_key, order_id)`, `is_duplicate(key)` |
| **Caller** | `execution/manager.py` `OrderManager.submit_order()` — line 107 |
| **Callee** | Checks Redis (fast) + DB (authoritative); prevents duplicate orders |
| **Test coverage** | `tests/test_execution.py` `test_generate_key` / `test_duplicate_detection` — ✅ ACTIVE |
| **Status** | **ACTIVE** |

---

## EDGE MAP: Gold Bot Runtime Path

### Edge 29: MT5 Data → Gold Bot Engine
| Field | Value |
|-------|-------|
| **Module** | `gold_bot/core/engine.py` |
| **Class** | `GoldBotEngine` |
| **Function** | `_fetch_data()` — gets bars from `MT5BrokerAdapter` for all timeframes |
| **Caller** | `_trading_cycle()` — runs every 30 seconds |
| **Callee** | Returns `Dict[str, Dict[str, List]]` — OHLCV per timeframe |
| **Test coverage** | `gold_bot/tests/test_engine.py` `test_generate_mock_data` — ✅ ACTIVE |
| **Status** | **ACTIVE** |

### Edge 30: Gold Bot Engine → 13 Strategies
| Field | Value |
|-------|-------|
| **Module** | `gold_bot/strategies/*.py` (13 strategies) |
| **Base** | `gold_bot/strategies/base.py` → `GoldStrategy` ABC |
| **Function** | `strategy.analyze(data, current_price, symbol)` → `Optional[StrategySignal]` |
| **Caller** | `GoldBotEngine._run_strategies(data)` |
| **Callee** | Returns `StrategySignal` with direction, confidence, score, entry/SL/TP |
| **Test coverage** | `gold_bot/tests/test_strategies.py` — ✅ ACTIVE (all 13 tested) |
| **Status** | **ACTIVE** |

### Edge 31: Gold Bot Strategies → Signal Aggregation
| Field | Value |
|-------|-------|
| **Module** | `gold_bot/core/engine.py` |
| **Function** | `GoldBotEngine._aggregate_signals(signals)` |
| **Caller** | `_trading_cycle()` |
| **Callee** | Returns `AggregatedSignal` with weighted total_score, buy_score, sell_score, consensus levels |
| **Test coverage** | `gold_bot/tests/test_engine.py` — ✅ ACTIVE |
| **Status** | **ACTIVE** |

### Edge 32: Gold Bot Aggregation → AI Validation
| Field | Value |
|-------|-------|
| **Module** | `gold_bot/ai/validator.py` |
| **Class** | `ClaudeAIValidator` |
| **Function** | `validate(AggregatedSignal)` → `bool` |
| **Caller** | `GoldBotEngine._trading_cycle()` — line 279 |
| **Callee** | Calls Claude API to validate signal; returns True/False |
| **Test coverage** | None explicit — ❌ UNKNOWN |
| **Status** | **ACTIVE** |

### Edge 33: Gold Bot Aggregation → Risk Check
| Field | Value |
|-------|-------|
| **Module** | `gold_bot/core/engine.py` |
| **Class** | `RiskManager` (gold_bot-specific, not `risk/engine.py`) |
| **Function** | `check(signal, open_trades, daily_pnl)` → `bool`; `calculate_position_size(balance, entry, sl)` |
| **Caller** | `_trading_cycle()` — line 286-291 |
| **Callee** | Checks max positions, daily loss, drawdown, min score, min active strategies |
| **Test coverage** | `gold_bot/tests/test_engine.py` `test_risk_check_*` — ✅ ACTIVE |
| **Status** | **ACTIVE** |

### Edge 34: Gold Bot Execution → MT5 Broker
| Field | Value |
|-------|-------|
| **Module** | `gold_bot/core/engine.py` → `execution/broker_adapter.py` |
| **Function** | `GoldBotEngine._execute_signal(aggregated)` → creates `Order` → `self.broker.place_order(order)` |
| **Caller** | `_trading_cycle()` — line 291 |
| **Callee** | `MT5BrokerAdapter.place_order(order)` → `BrokerOrderResponse` |
| **Test coverage** | None for execution path — ❌ UNKNOWN |
| **Status** | **ACTIVE** |

### Edge 35: Gold Bot → Telegram Notification
| Field | Value |
|-------|-------|
| **Module** | `gold_bot/monitoring/telegram_bot.py` |
| **Class** | `GoldBotTelegram` |
| **Function** | `notify_trade(trade, signal)`, `notify_daily_report(stats)` |
| **Caller** | `GoldBotEngine._execute_signal()` — line 554 |
| **Callee** | Sends Telegram messages |
| **Test coverage** | None — ❌ UNKNOWN |
| **Status** | **ACTIVE** |

---

## EDGE MAP: Webhook/API Runtime Path

### Edge 36: TradingView Webhook → Order Pipeline
| Field | Value |
|-------|-------|
| **Module** | `api/webhook.py` |
| **Function** | `tradingview_webhook(request, x_signature, db)` |
| **Caller** | HTTP POST `/webhook/tradingview` |
| **Callee** | Verifies HMAC → parses payload → records `SignalModel` → creates `BrokerManager` + `RiskEngine` + `OrderManager` → `submit_order()` |
| **Test coverage** | None — ❌ UNKNOWN |
| **Status** | **ACTIVE** |

### Edge 37: API → Risk Status
| Field | Value |
|-------|-------|
| **Module** | `api/risk.py` |
| **Function** | `get_risk_status()`, `get_risk_limits()` |
| **Caller** | HTTP GET `/risk/status` / `/risk/limits` |
| **Callee** | Reads from risk engine |
| **Test coverage** | None — ❌ UNKNOWN |
| **Status** | **ACTIVE** |

---

## EDGE MAP: Data Pipeline (Multi-Source)

### Edge 38: Multi-Source Pipeline → Data Ingestion
| Field | Value |
|-------|-------|
| **Module** | `core/multi_source_pipeline.py` |
| **Class** | `MultiSourcePipeline` |
| **Function** | `fetch_ohlcv(...)`, `fetch_macro(...)`, `fetch_fear_greed()`, `fetch_google_trends(...)` |
| **Caller** | ML training, research notebooks |
| **Callee** | Fetches from CCXT, CoinGecko, Yahoo, FRED, Google Trends |
| **Test coverage** | None — ❌ UNKNOWN |
| **Status** | **ACTIVE** |

### Edge 39: ML Pipeline → Model Training
| Field | Value |
|-------|-------|
| **Module** | `ml/pipeline.py` |
| **Class** | `MLPipeline` |
| **Function** | `train(...)`, `predict(...)`, `load_model(...)` |
| **Caller** | `run_ml_train.py` |
| **Callee** | XGBoost models saved to `ml/models/*.pkl` |
| **Test coverage** | None — ❌ UNKNOWN |
| **Status** | **ACTIVE** |

---

## COMPLETE EDGE REFERENCE TABLE

| # | Source | Target | Module / Function | Status | Test |
|---|--------|--------|-------------------|--------|------|
| 1 | CSV/tick | Data Loader | `backtest/data_loader.py` / `load_csv_data()` | ACTIVE | ✅ |
| 2 | Data Loader | Backtest Engine | `backtest/engine.py` / `load_data()` | ACTIVE | ✅ |
| 3 | Backtest Engine | MTF Cursor | `backtest/mtf_cursor.py` / `MultiTimeframeCursor.slice_as_of()` | ACTIVE | ✅ |
| 4 | MTF Cursor | Strategy Adapter | `gold_bot/strategy_adapter.py` / `GoldStrategyAdapter.generate_signal()` | ACTIVE | ✅ |
| 5 | MTF Cursor | Canonical Strategy | `strategies/mtm.py` / `generate_signal()` | ACTIVE | ✅ |
| 6 | Strategy Signal | Backtest Execution | `backtest/engine.py` / `_execute_signal()` | ACTIVE | ✅ |
| 7 | Backtest Engine | Metrics/Report | `backtest/metrics.py` / `calculate_metrics()` | ACTIVE | ✅ |
| 8 | Backtest Engine | Walk-Forward | `backtest/walk_forward.py` / `WalkForwardAnalyzer.analyze()` | ACTIVE | ✅ |
| 9 | Backtest Engine | Lookahead Guard | `core/lookahead_guard.py` / `LookaheadGuard.get_slice()` | ACTIVE | ✅ |
| 10 | MT5 Tick | Data Feed | `data/feed.py` / `MT5DataFeed.get_tick()` | ACTIVE | ❌ |
| 11 | Data Feed | DataFeedManager | `data/feed.py` / `DataFeedManager` | STUB | ❌ |
| 12 | Data Feed | Quality Gate | `data/quality_gate.py` / `DataQualityGate.validate_ohlcv()` | STUB | ❌ |
| 13 | Signal | Risk Engine (legacy) | `risk/engine.py` / `RiskEngine.check_order()` | LEGACY | ✅ |
| 14 | Signal | Pre-Trade Risk (canonical) | `risk/pre_trade_risk.py` / `pre_trade_check()` | ACTIVE | ✅ |
| 15 | Signal | Position Sizer v2 (canonical) | `risk/position_sizer_v2.py` / `size_position()` | ACTIVE | ✅ |
| 16 | Signal | Position Sizer v1 (legacy) | `risk/position_sizer.py` / `FixedFractionalSizer.calculate()` | LEGACY | ✅ |
| 17 | Risk | Kill Switch | `risk/kill_switch.py` / `KillSwitch.is_active()` | ACTIVE | ❌ |
| 18 | Risk | Risk Ledger | `risk/risk_ledger.py` / `RiskLedger.record_trade()` | ACTIVE | ✅ |
| 19 | Risk | Risk Policy | `risk/risk_policy.py` / `RiskPolicy` (immutable) | ACTIVE | ✅ |
| 20 | Execution | Order State Machine (canonical) | `execution/order_state_machine.py` / `OrderStateMachine.advance()` | ACTIVE | ✅ |
| 21 | Execution | Order (legacy) | `execution/order.py` / `OrderStateMachine.transition()` | LEGACY | ✅ |
| 22 | Execution | Order Manager | `execution/manager.py` / `OrderManager.submit_order()` | ACTIVE | ❌ |
| 23 | Execution | Broker Adapter | `execution/broker_adapter.py` / `PaperBroker.place_order()` | ACTIVE | ✅ |
| 24 | Execution | Fill Model | `execution/fill_model.py` / `simulate_entry()` | ACTIVE | ✅ |
| 25 | Execution | Conservative Bar Model | `execution/conservative_bar_model.py` / `simulate_bar_execution()` | ACTIVE | ✅ |
| 26 | Execution | Cost Model | `execution/cost_model.py` / `calculate_trade_costs()` | ACTIVE | ❌ |
| 27 | Execution | Trade Ledger | `execution/trade_ledger.py` / `TradeLedger.record_trade()` | ACTIVE | ✅ |
| 28 | Execution | Idempotency | `execution/idempotency.py` / `IdempotencyChecker.check_and_record()` | ACTIVE | ✅ |
| 29 | MT5 Data | Gold Bot Engine | `gold_bot/core/engine.py` / `GoldBotEngine._fetch_data()` | ACTIVE | ✅ |
| 30 | Gold Bot Engine | 13 Strategies | `gold_bot/strategies/*.py` / `GoldStrategy.analyze()` | ACTIVE | ✅ |
| 31 | Gold Bot Strategies | Signal Aggregation | `gold_bot/core/engine.py` / `_aggregate_signals()` | ACTIVE | ✅ |
| 32 | Aggregation | AI Validation | `gold_bot/ai/validator.py` / `ClaudeAIValidator.validate()` | ACTIVE | ❌ |
| 33 | Aggregation | Gold Bot Risk | `gold_bot/core/engine.py` / `RiskManager.check()` | ACTIVE | ✅ |
| 34 | Gold Bot Risk | MT5 Execution | `gold_bot/core/engine.py` → `execution/broker_adapter.py` | ACTIVE | ❌ |
| 35 | Gold Bot | Telegram | `gold_bot/monitoring/telegram_bot.py` / `GoldBotTelegram.notify_trade()` | ACTIVE | ❌ |
| 36 | TradingView | Order Pipeline | `api/webhook.py` / `tradingview_webhook()` | ACTIVE | ❌ |
| 37 | API | Risk Status | `api/risk.py` / `get_risk_status()` | ACTIVE | ❌ |
| 38 | Multi-Source | Data Ingestion | `core/multi_source_pipeline.py` / `fetch_ohlcv()` | ACTIVE | ❌ |
| 39 | ML Pipeline | Model Training | `ml/pipeline.py` / `MLPipeline.train()` | ACTIVE | ❌ |

---

## ENTRY POINTS

| Entry Point | File | Triggers |
|-------------|------|----------|
| Backtest (Yahoo data) | `run_backtest.py` | `main()` → download → backtest → compare strategies |
| Backtest (real data) | `run_backtest_real.py` | Direct script execution |
| ML Training | `run_ml_train.py` | Trains XGBoost models |
| Paper Trading | `run_paper_trading.py` | Starts paper trading engine |
| Gold Bot Live | `gold_bot/run.py` | `GoldBotEngine.start()` → 30s cycle loop |
| Gold Bot Demo | `gold_bot/run_demo.py` | Demo mode with mock data |
| API Server | `api/main.py` | FastAPI with webhook, orders, positions, risk endpoints |
| Webhook | `api/webhook.py` | TradingView → `/webhook/tradingview` |

---

## DUAL-TRACK STATUS SUMMARY

| Module | Canonical Path | Legacy Path | Notes |
|--------|---------------|-------------|-------|
| Position Sizing | `risk/position_sizer_v2.py` | `risk/position_sizer.py` | v2 uses decoupled ContractSpec + RiskPolicy |
| Pre-Trade Risk | `risk/pre_trade_risk.py` | `risk/engine.py` | pre_trade_risk is simpler, checks sizing_result |
| Order State Machine | `execution/order_state_machine.py` | `execution/order.py` (inline) | 16 states vs 10 states; canonical has CRITICAL_INCIDENT |
| Trade Ledger | `execution/trade_ledger.py` | `core/structured_trades.py` | JSON-file records with SHA-256 hash chain |
| Data Loading | `data/feed.py` | `backtest/data_loader.py` | feed is live/paper; data_loader is backtest-specific |
| Strategy Base | `strategies/base.py` | `gold_bot/strategies/base.py` | Different lineages; gold_bot uses GoldStrategy ABC |
| Risk Policy | `risk/risk_policy.py` | `core/golden_rules.py` | policy is soft limits (bps); golden_rules are hard limits |

---

## GAPS AND UNWIRED PATHS

1. **`data/quality_gate.py`** — STUB: Implemented but not called anywhere in the live path
2. **`data/feed.py` `DataFeedManager`** — STUB: Fallback chain implemented but not wired into live engine
3. **`execution/manager.py`** → `risk/pre_trade_risk.py` — NOT WIRED: OrderManager still uses `risk/engine.py` (legacy)
4. **`risk/pre_trade_risk.py`** → `risk/position_sizer_v2.py` — NOT WIRED: No code calls both in sequence
5. **`execution/trade_ledger.py`** — NOT WIRED: No production code calls `record_trade()` after fills
6. **`execution/order_state_machine.py`** — NOT WIRED: `execution/manager.py` uses inline state in `order.py`
7. **`broker/contract_spec.py`** + `broker/contract_snapshot_store.py` — NOT WIRED into sizing path
8. **`execution/cost_model.py`** — NOT WIRED into backtest or live execution
9. **`gold_bot/ai/validator.py`** — Wired but no test coverage
10. **`api/webhook.py`** — Wired but no test coverage

---

*Canonical runtime map: 2026-06-22*
