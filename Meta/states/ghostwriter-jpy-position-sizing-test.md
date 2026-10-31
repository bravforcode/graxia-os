# Ghostwriter State — JPY Position-Sizing Regression Test

**Date:** 2026-08-07
**Status:** DONE

## Task
Strengthen JPY position-sizing regression test in `graxia/packages/quant_os/tests/chaos/test_api_untested.py`.

## Root Cause (verified)
- `api/webhook.py::calculate_position_size` L369-371 early-returns `Decimal("0.01")` when `atr` is None/<=0.
- `TradingViewPayload.atr` defaults to 0.0 → old JPY test passed vacuously (never reached get_spec branch).
- `_mock_config()` returns plain `MagicMock`; `risk_policy` auto-mocks → `float(MagicMock())` would TypeError if sizing branch ran without a real fraction.

## Changes (test file only — no code changes)
1. `test_calculate_position_size_jpy`: set `cfg.risk_policy.risk_per_trade_fraction = 0.01`, `atr=0.5`, `equity=10000.0`; assert `0.25 < float(result) < 0.35`.
2. `test_calculate_position_size_unknown_symbol_fallback`: also set atr + risk fraction (was vacuous too — FOOBAR atr=0 early-returned before fallback branch).

## Discriminator Proof
- NEW get_spec: 10000*0.01 / ((0.5/0.01)*6.67) = 100/333.5 = **0.30** → in range ✓
- OLD buggy (contract 100000/100=1000): 100/(0.5*1000) = **0.20** → FAILS range ✗ (1.5x discriminator)
- USDJPY spec confirmed in `core/contract_specs.py` L47: `ContractSpec(_FX, Decimal("0.01"), Decimal("6.67"), True)`

## Verification
- `pytest ... -k calculate_position_size -v` → **5 passed** (all position-size tests).
- Full file: 46 dots + 4 pre-existing `TestRiskChaos` failures (api/risk.py signature mismatch — `get_risk_status`/`get_portfolio_exposure`/`get_pnl_summary` missing `request` arg, `kill_switch_action` missing `payload`). OUT OF SCOPE, pre-existing, not touched.

## Files Changed
- `graxia/packages/quant_os/tests/chaos/test_api_untested.py` (+47 lines, 2 tests)

NOT committed — controller commits.
