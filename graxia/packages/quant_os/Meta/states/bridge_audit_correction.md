# Bridge Agent State — Audit Correction

**Session:** 2026-06-25
**Task:** Correct 3 critical gaps in full repository audit

## Findings

### Gap 1: ~2000x Bug vs ms→ns Bug
- **~2000x bug** = cost-unit bug (missing *2350 multiplier in `compute_fold_pnl`) — FIXED per `test_cost_unit_regression.py`
- **ms→ns bug** = slippage estimation bug in `simulate_fills.py` — claimed fixed in SUMMARY.md but unverified against current code
- They are DIFFERENT bugs. The ~2000x is the cost-unit bug (2350x ≈ ~2000x)

### Gap 2: Three Separate Cost Paths
1. `backtest/engine.py` — hardcoded 2 pips spread, $3.5 commission, 0.5 pips slippage
2. `scripts/backtest_cost.py` — $0.17 spread + $0.39 slippage P90 (used for SUMMARY.md numbers)
3. `scripts/walk_forward.py` — return-unit costs from `config/cost_calibration.json`

**"No edge" conclusion** from SUMMARY.md is based on path #2 ($0.56/trade). Path #1 uses ~10x lower costs.

### Gap 3: RiskPolicy Mutable vs Frozen
- `pre_trade_risk.py:12` — `@dataclass` (MUTABLE) — used by `pre_trade_check()`
- `position_sizer_v2.py:22` — `@dataclass` (MUTABLE) — used by `size_position()`
- `risk_policy.py:8` — `@dataclass(frozen=True)` (FROZEN) — correct per INV-001, but not used by production code

**INV-001 violation confirmed.** Practical risk is low but architectural invariant is broken.

## Files Written
- `reports/FULL_REPOSITORY_AUDIT.md` — original audit
- `reports/CORRECTIVE_AUDIT_ADDENDUM.md` — correction for 3 gaps
