# Quant OS Constitution

## Absolute Rules

- Never claim guaranteed profit, guaranteed win rate, zero loss, or zero drawdown
- Never claim backtest results are live-trading evidence
- Never claim demo performance proves real-money profitability
- Never allow an LLM, sentiment model, or external repository to override risk controls
- Every phase must end in exactly one verdict: PASS_TO_NEXT_PHASE | CONDITIONAL_PASS | NO_GO | ARCHIVE_NO_EDGE | INSUFFICIENT_SAMPLE

## Invariants (INV-001 through INV-011)

| ID | Invariant | Enforced By |
|----|-----------|-------------|
| INV-001 | Risk policy is frozen dataclass, no runtime mutation | `RiskPolicy(frozen=True)` |
| INV-002 | All loss limits in basis points, never percentage floats | `validate_no_pct_in_production()` |
| INV-003 | No `order_send` exists in backtest or risk modules | Firewall tests |
| INV-004 | Strict MTF blocks static fallback without cursor | `StrictMTFViolation` |
| INV-005 | Every dataset has manifest with SHA-256 checksum | `data/manifests/*.manifest.json` |
| INV-006 | ContractSpec validates on creation, rejects invalid specs | `ContractSpec.validate()` |
| INV-007 | Volume rounds down to broker step, never up | `position_sizer_v2` |
| INV-008 | Kill switch persists across restart via JSON file | `kill_switch.py` |
| INV-009 | Pre-trade risk gate mandatory before any order | `pre_trade_risk.py` |
| INV-010 | Missing/invalid/stale contract data = reject + fail closed | `require_contract_snapshot=True` |
| INV-011 | Every sizing decision bound to immutable contract_snapshot_id | `contract_snapshot_store` |

## Mandatory Result Labels

| Label | Meaning |
|-------|---------|
| `PASS_TO_NEXT_PHASE` | All tests pass, invariants hold, ready for next phase |
| `CONDITIONAL_PASS` | Tests pass with known gaps, next phase may proceed with caution |
| `NO_GO` | Critical failure or invariant violation, must fix before proceeding |
| `ARCHIVE_NO_EDGE` | Strategy tested but no statistically significant edge found |
| `INSUFFICIENT_SAMPLE` | Not enough data to draw conclusions, continue collecting |
