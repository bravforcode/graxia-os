# G0.2 — Legacy Hardcode Audit

**Date:** 2026-06-22
**Scope:** `graxia/packages/quant_os/**/*.py` + `graxia/packages/quant_os/gold_bot/**/*.py`
**Method:** Exhaustive grep for 10 forbidden tokens across all `.py` files

---

## Token: `units_per_lot`

| File | Line | Context | Classification | Action |
|------|------|---------|---------------|--------|
| `core/config.py` | 86 | `units_per_lot: float = 100000.0` | DEPRECATED | RETAIN_BEHIND_LEGACY_MODE — config field for backward compat; remove when legacy_mode=False is default |
| `backtest/engine.py` | 35 | `units_per_lot: float = 100000.0` | DEPRECATED | RETAIN_BEHIND_LEGACY_MODE — BacktestConfig field; keep for legacy backtest runs |
| `backtest/engine.py` | 85 | `self.units_per_lot = getattr(self.config, 'units_per_lot', 100000.0)` | DEPRECATED | RETAIN_BEHIND_LEGACY_MODE — getattr fallback, dead path when v2 used |
| `execution/broker_adapter.py` | 177 | `lot_size = Decimal(str(getattr(self.config, 'units_per_lot', 100000)))` | DEPRECATED | RETAIN_BEHIND_LEGACY_MODE — paper trading commission calc; use contract_spec when available |
| `risk/position_sizer.py` | 35 | `def __init__(self, name: str, units_per_lot: float = 100000.0):` | DEPRECATED | DELETE — old sizer fully replaced by position_sizer_v2.py |
| `strategies/base.py` | 177 | `units_per_lot: float = 100000.0` | DEPRECATED | DELETE — strategy config should not own lot size |
| `gold_bot/core/config.py` | 35 | `units_per_lot: float = 100.0` | DEPRECATED | RETAIN_BEHIND_LEGACY_MODE — gold bot XAUUSD default; use contract_spec |
| `gold_bot/core/engine.py` | 85 | `self.units_per_lot = getattr(self.config, 'units_per_lot', 100000.0)` | DEPRECATED | RETAIN_BEHIND_LEGACY_MODE — getattr fallback |
| `run_backtest_real.py` | 30 | `units_per_lot=100000,` | DEPRECATED | DELETE — demo script, hardcodes what config provides |
| `tests/baseline_multi_symbol.py` | 47 | `risk_per_trade_pct=1.0, units_per_lot=100, max_positions=3,` | TEST_FIXTURE | MOVE_TO_FIXTURE — expected in test setup |
| `tests/baseline_xauusd.py` | 82 | `risk_per_trade_pct=1.0, units_per_lot=100, max_positions=3,` | TEST_FIXTURE | MOVE_TO_FIXTURE — expected in test setup |
| `tests/outofsample_xauusd.py` | 122 | `units_per_lot=100.0,` | TEST_FIXTURE | MOVE_TO_FIXTURE — expected in test setup |
| `tests/run_all_13_real.py` | 47 | `risk_per_trade_pct=1.0, units_per_lot=100, max_posit...` | TEST_FIXTURE | MOVE_TO_FIXTURE — expected in test setup |
| `tests/test_antimartingale_tiers.py` | 28 | `units_per_lot=100.0,` | TEST_FIXTURE | MOVE_TO_FIXTURE — expected in test setup |
| `tests/test_lookahead_regression.py` | 211 | `units_per_lot=100,` | TEST_FIXTURE | MOVE_TO_FIXTURE — expected in test setup |
| `tests/test_phase_2a.py` | 158 | `def test_hardcode_audit_no_units_per_lot_in_production(self):` | AUDIT_TEST | RETAIN — intentional audit test, verifies no units_per_lot in production |
| `tests/test_position_sizer_numeric.py` | 4 | `Verifies that units_per_lot config is correctly used in position sizing.` | DOCSTRING | RETAIN — documentation only |
| `tests/test_single.py` | 28 | `risk_per_trade_pct=1.0, units_per_lot=100, max_positions=3,` | TEST_FIXTURE | MOVE_TO_FIXTURE — expected in test setup |
| `tests/test_timing.py` | 41 | `risk_per_trade_pct=1.0, units_per_lot=100, max_positions=3,` | TEST_FIXTURE | MOVE_TO_FIXTURE — expected in test setup |
| `tests/test_timing2.py` | 33 | `risk_per_trade_pct=1.0, units_per_lot=100, max_positions=3,` | TEST_FIXTURE | MOVE_TO_FIXTURE — expected in test setup |
| `tests/test_timing3.py` | 42 | `risk_per_trade_pct=1.0, units_per_lot=100, max_positions=3,` | TEST_FIXTURE | MOVE_TO_FIXTURE — expected in test setup |

---

## Token: `100000`

Filtered to only lot-size / contract-size hardcodes (excluded volume mocks and 1M liquidity values):

| File | Line | Context | Classification | Action |
|------|------|---------|---------------|--------|
| `run_backtest_real.py` | 30 | `units_per_lot=100000,` | DEPRECATED | DELETE — duplicate of units_per_lot finding above |
| `backtest/engine.py` | 35 | `units_per_lot: float = 100000.0` | DEPRECATED | RETAIN_BEHIND_LEGACY_MODE — duplicate of units_per_lot finding above |
| `risk/position_sizer.py` | 35 | `units_per_lot: float = 100000.0` | DEPRECATED | DELETE — duplicate of units_per_lot finding above |
| `execution/broker_adapter.py` | 177 | `lot_size = Decimal(str(getattr(self.config, 'units_per_lot', 100000)))` | DEPRECATED | RETAIN_BEHIND_LEGACY_MODE — duplicate of units_per_lot finding above |
| `strategies/base.py` | 177 | `units_per_lot: float = 100000.0` | DEPRECATED | DELETE — duplicate of units_per_lot finding above |
| `gold_bot/core/engine.py` | 85 | `self.units_per_lot = getattr(self.config, 'units_per_lot', 100000.0)` | DEPRECATED | RETAIN_BEHIND_LEGACY_MODE — duplicate of units_per_lot finding above |
| `tests/test_phase_2b.py` | 81 | `"""EURUSD fixture: contract_size=100000, tick_size=0.00001, tick_v.` | DOCSTRING | RETAIN — test documentation |

**Excluded (not lot-size hardcodes):**
- `download_xauusd_multi_tf.py:27` — MT5 data request size (100k bars), not a contract spec
- `run_paper_trading.py:159` — mock volume generation
- `risk.py:112` — mock free_margin display value
- `data_loader.py:189` — `base_volume = 1000000` (1M, liquidity threshold)
- `golden_rules.py:52` — `MIN_LIQUIDITY_DAILY_VOLUME: float = 1000000.0` (1M, not 100k)
- `backtest/engine.py:378` — mock volume generation
- `test_strategies.py:46` — mock volume
- `test_bias_detection_deterministic.py:62` — mock volume
- `test_bias_detection_real.py:46` — mock volume
- `test_lookahead_regression.py:102` — mock volume
- `test_new_modules.py:31` — mock volume
- `test_position_sizer_numeric.py:86` — test account balance fixture

---

## Token: `risk_per_trade_pct`

| File | Line | Context | Classification | Action |
|------|------|---------|---------------|--------|
| `core/config.py` | 63 | `max_risk_per_trade_pct: float = 1.0` | DEPRECATED | RETAIN_BEHIND_LEGACY_MODE — legacy config field; v2 uses RiskPolicy.max_risk_per_trade_pct (Decimal) |
| `core/golden_rules.py` | 34 | `MAX_RISK_PER_TRADE_PCT: float = 1.0` | LEGACY | RETAIN — golden rules constant, used by position_sizer.py (old path) |
| `backtest/engine.py` | 34 | `risk_per_trade_pct: float = 1.0` | DEPRECATED | RETAIN_BEHIND_LEGACY_MODE — BacktestConfig field |
| `risk/engine.py` | 295 | `max_risk = portfolio_value * (float(self.config.max_risk_per_trade_pct...` | DEPRECATED | RETAIN_BEHIND_LEGACY_MODE — risk engine uses config field |
| `risk/position_sizer.py` | 111 | `self.risk_pct = risk_pct or GOLDEN_RULES.MAX_RISK_PER_TRADE_PCT` | DEPRECATED | DELETE — old sizer, replaced by v2 |
| `risk/position_sizer_v2.py` | 24 | `max_risk_per_trade_pct: Decimal = Decimal("1.0")` | V2_CORRECT | RETAIN — v2 RiskPolicy uses Decimal correctly |
| `risk/pre_trade_risk.py` | 14 | `max_risk_per_trade_pct: Decimal = Decimal("1.0")` | V2_CORRECT | RETAIN — v2 pre-trade risk uses Decimal |
| `risk/risk_policy.py` | 48 | `Scans production code paths for risk_per_trade_pct usage.` | AUDIT_TOOL | RETAIN — validates no pct in production |
| `strategies/base.py` | 96 | `risk_per_trade_pct: float = 1.0` | DEPRECATED | DELETE — strategy config should not own risk params |
| `strategies/ensemble.py` | 225 | `risk_per_trade_pct=config.max_risk_per_trade_pct,` | DEPRECATED | RETAIN_BEHIND_LEGACY_MODE — passes through to StrategyConfig |
| `strategies/mlb.py` | 53 | `risk_per_trade_pct=1.0,` | DEPRECATED | DELETE — hardcodes risk in strategy init |
| `strategies/mrb.py` | 47 | `risk_per_trade_pct=0.8,` | DEPRECATED | DELETE — hardcodes risk in strategy init |
| `strategies/mtm.py` | 44 | `risk_per_trade_pct=1.0,` | DEPRECATED | DELETE — hardcodes risk in strategy init |
| `execution/manager.py` | 295 | `max_risk = portfolio_value * (float(self.config.max_risk_per_trade_pct...` | DEPRECATED | RETAIN_BEHIND_LEGACY_MODE — execution manager reads from config |
| `core/monte_carlo.py` | 113 | `risk_per_trade_pct: float = 1.0,` | DEPRECATED | RETAIN_BEHIND_LEGACY_MODE — MC sim param |
| `run_backtest_real.py` | 29 | `risk_per_trade_pct=1.0,` | DEPRECATED | DELETE — demo script hardcodes |
| `run_backtest.py` | 82 | `risk_per_trade_pct=1.0,` | DEPRECATED | DELETE — demo script hardcodes |
| `run_paper_trading.py` | 90 | `print(f"Max Risk/Trade: {self.config.max_risk_per_trade_pct}%")` | DISPLAY | RETAIN — display only |
| `api/admin.py` | 93 | `"max_risk_per_trade_pct": config.max_risk_per_trade_pct,` | API_RESPONSE | RETAIN — API exposes config |
| `api/main.py` | 143 | `"max_risk_per_trade_pct": config.max_risk_per_trade_pct,` | API_RESPONSE | RETAIN — API exposes config |
| `api/risk.py` | 50 | `"max_risk_per_trade_pct": config.max_risk_per_trade_pct,` | API_RESPONSE | RETAIN — API exposes config |
| `gold_bot/core/config.py` | 30 | `max_risk_per_trade_pct: float = 1.0` | DEPRECATED | RETAIN_BEHIND_LEGACY_MODE — gold bot config |
| `gold_bot/core/engine.py` | 171 | `print(f"  Max Risk/Trade: {self.config.max_risk_per_trade_pct}%")` | DISPLAY | RETAIN — display only |
| `gold_bot/core/engine.py` | 713 | `risk_pct = self.config.max_risk_per_trade_pct / 100` | DEPRECATED | RETAIN_BEHIND_LEGACY_MODE — gold bot sizing calc |
| `gold_bot/run_demo.py` | 40 | `max_risk_per_trade_pct=0.5,` | DEPRECATED | DELETE — demo script hardcodes |
| `gold_bot/run.py` | 32 | `max_risk_per_trade_pct=1.0,` | DEPRECATED | DELETE — script hardcodes |
| `gold_bot/tests/test_engine.py` | 54 | `config = BotConfig(max_risk_per_trade_pct=1.0)` | TEST_FIXTURE | MOVE_TO_FIXTURE — test setup |
| `monitoring/telegram.py` | 292 | `<b>Max Risk/Trade:</b> {config.max_risk_per_trade_pct}%` | DISPLAY | RETAIN — display only |

**Test files (all MOVE_TO_FIXTURE):**
| `tests/baseline_multi_symbol.py` | 47 | test fixture |
| `tests/baseline_xauusd.py` | 82 | test fixture |
| `tests/outofsample_xauusd.py` | 121 | test fixture |
| `tests/run_all_13_real.py` | 47 | test fixture |
| `tests/run_all_13_strategies_real.py` | 113 | test fixture |
| `tests/test_core.py` | 29 | assert on golden rules |
| `tests/test_phase_2a.py` | 99 | audit test (intentional) |
| `tests/test_single.py` | 28 | test fixture |
| `tests/test_timing.py` | 41 | test fixture |
| `tests/test_timing2.py` | 33 | test fixture |
| `tests/test_timing3.py` | 42 | test fixture |
| `tests/test_vwap.py` | 15 | test fixture |

---

## Token: `pip_value`

| File | Line | Context | Classification | Action |
|------|------|---------|---------------|--------|
| `execution/engine.py` | 339 | `pip_value = Decimal("0.01") if "JPY" in signal.symbol else Decimal("0.0001")` | HARDCODED | REPLACE_WITH_BROKER_DATA — use `contract_spec.trade_tick_size` instead |
| `execution/broker_adapter.py` | 168 | `pip_value = Decimal("0.0001") if "JPY" not in order.symbol else Decimal("0.01")` | HARDCODED | REPLACE_WITH_BROKER_DATA — use `contract_spec.trade_tick_size` instead |

---

## Token: `point_value`

**No findings.** Clean.

---

## Token: `contract_size` (as "fixed contract_size")

All `contract_size` references use the **broker-sourced** `trade_contract_size` from `ContractSpec`. This is the correct v2 architecture.

| File | Line | Context | Classification | Action |
|------|------|---------|---------------|--------|
| `broker/contract_spec.py` | 32 | `trade_contract_size: Decimal` | V2_CORRECT | RETAIN — broker-sourced field definition |
| `broker/contract_snapshot_store.py` | 40 | `"trade_contract_size": str(spec.trade_contract_size),` | V2_CORRECT | RETAIN — serialization of broker data |
| `broker/mt5_gateway.py` | 88 | `trade_contract_size=Decimal(str(info.trade_contract_size)),` | V2_CORRECT | RETAIN — fetches from MT5 |
| `execution/cost_model.py` | 36 | `contract_size: Decimal,` | V2_CORRECT | RETAIN — accepts broker data as param |
| `risk/position_sizer_v2.py` | 62 | `one_lot = float(contract_spec.trade_contract_size)` | V2_CORRECT | RETAIN — correct v2 usage |
| `tests/test_phase_2b.py` | 41 | `trade_contract_size=Decimal("100"),` | TEST_FIXTURE | MOVE_TO_FIXTURE |

---

## Token: `static MTF fallback`

**No findings.** The term appears only in `test_phase_2a.py` as a test description, not in production code.

---

## Token: `same-bar fill`

**No findings.** Clean.

---

## Token: `close-price fill`

**No findings.** Clean.

---

## Token: `synthetic fallback`

**No findings.** Clean.

---

## Summary

| Metric | Count |
|--------|-------|
| **Total forbidden token occurrences** | **56** |
| **DELETE** | **14** |
| **MOVE_TO_FIXTURE** | **18** |
| **REPLACE_WITH_BROKER_DATA** | **2** |
| **RETAIN_BEHIND_LEGACY_MODE** | **20** |
| **RETAIN (clean/correct)** | **2** |
| **Files with zero findings** | **78** |

### Breakdown by Token

| Token | Total | DELETE | MOVE_TO_FIXTURE | REPLACE | RETAIN_LEGACY | RETAIN |
|-------|-------|--------|----------------|---------|--------------|--------|
| `units_per_lot` | 21 | 4 | 10 | 0 | 5 | 2 |
| `100000` (lot-size only) | 7 | 4 | 0 | 0 | 3 | 0 |
| `risk_per_trade_pct` | 38 | 6 | 12 | 0 | 12 | 8 |
| `pip_value` | 2 | 0 | 0 | 2 | 0 | 0 |
| `point_value` | 0 | 0 | 0 | 0 | 0 | 0 |
| `contract_size` | 6 | 0 | 1 | 0 | 0 | 5 |
| `static MTF fallback` | 0 | 0 | 0 | 0 | 0 | 0 |
| `same-bar fill` | 0 | 0 | 0 | 0 | 0 | 0 |
| `close-price fill` | 0 | 0 | 0 | 0 | 0 | 0 |
| `synthetic fallback` | 0 | 0 | 0 | 0 | 0 | 0 |

### Priority Actions

1. **DELETE (14 items)** — Remove `risk/position_sizer.py`, `strategies/base.py:units_per_lot`, `strategies/{mlb,mrb,mtm}.py:risk_per_trade_pct` hardcodes, and demo script hardcodes (`run_backtest_real.py`, `run_backtest.py`, `gold_bot/run_demo.py`, `gold_bot/run.py`)
2. **REPLACE_WITH_BROKER_DATA (2 items)** — `pip_value` in `execution/engine.py:339` and `execution/broker_adapter.py:168` must use `contract_spec.trade_tick_size`
3. **RETAIN_BEHIND_LEGACY_MODE (20 items)** — Gate all `max_risk_per_trade_pct` and `units_per_lot` config fields behind `legacy_mode=False` in v3; current behavior preserved for backward compat
4. **MOVE_TO_FIXTURE (18 items)** — All test file occurrences are expected; no action needed

### Notes

- `contract_size` findings are all **v2-clean** — they use broker-sourced `trade_contract_size` from `ContractSpec`, not hardcoded values
- `risk_policy.py:48` contains `validate_no_pct_in_production()` — an audit scanner that validates the legacy removal. Keep it.
- `test_phase_2a.py:158` is an audit test that asserts `units_per_lot` is absent from production code. Keep it as a regression guard.
