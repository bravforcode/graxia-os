# Quant OS Constitution

## Absolute Rules

- Never claim guaranteed profit, guaranteed win rate, zero loss, or zero drawdown
- Never claim backtest results are live-trading evidence
- Never claim demo performance proves real-money profitability
- Never allow an LLM, sentiment model, or external repository to override risk controls
- Every phase must end in exactly one verdict: PASS_TO_NEXT_PHASE | CONDITIONAL_PASS | NO_GO | ARCHIVE_NO_EDGE | INSUFFICIENT_SAMPLE
- **INV-012: Edge Claim Discipline** — Any document, report, or conversation that claims a strategy "has edge," "is an edge amplifier," "showed edge," or similar positive edge assertion MUST cite: (1) trial_number from `research/hypothesis_registry.json`, (2) p-value or dk_t statistic, (3) artifact path (walk-forward result, validation report, or test output). Without these three citations, the claim is an UNTESTED HYPOTHESIS, not a finding. Violations must be corrected before the document is used in any decision.
- **INV-013: Diff Matches Intent** — Every commit diff must be reviewed to confirm only intended changes are included. Before any commit: (1) run `git diff --staged` and verify every line belongs to the stated purpose, (2) if unintended changes appear (sweep-ins, accidental refactors, untested features), unstage them and fix the commit scope, (3) commit message must match the actual diff content. This prevents accidental inclusion of unverified changes (e.g., trailing stop, cost-math, unrelated refactors). Violations are treated as process failures, not code bugs.

## Invariants (INV-001 through INV-012)

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
| INV-012 | Edge claims require trial_number + p-value/dk_t + artifact path from hypothesis_registry.json | Document review, audit |
| INV-013 | Commit diff must match stated intent; unintended sweep-ins are process failures | `git diff --staged` review |

## Mandatory Result Labels

| Label | Meaning |
|-------|---------|
| `PASS_TO_NEXT_PHASE` | All tests pass, invariants hold, ready for next phase |
| `CONDITIONAL_PASS` | Tests pass with known gaps, next phase may proceed with caution |
| `NO_GO` | Critical failure or invariant violation, must fix before proceeding |
| `ARCHIVE_NO_EDGE` | Strategy tested but no statistically significant edge found |
| `INSUFFICIENT_SAMPLE` | Not enough data to draw conclusions, continue collecting |

---

## INV-012: Edge Claim Discipline — Detailed Rules

### Purpose
Prevent unfounded edge claims from entering the decision pipeline. Every edge assertion must be backed by pre-registered hypothesis + statistical evidence.

### Required Citations for Any Edge Claim

Any document, report, or conversation that uses language like:
- "strategy X has edge"
- "this is an edge amplifier"
- "showed edge in testing"
- "demonstrated alpha"
- "profitable after costs"
- or similar positive edge assertions

**MUST include all three:**

| Citation | Source | Example |
|----------|--------|---------|
| **Trial Number** | `research/hypothesis_registry.json` | `trial_number: 1001` |
| **Statistical Evidence** | Walk-forward result, validation report | `p-value: 0.032, dk_t: 2.15` |
| **Artifact Path** | File system location of proof | `reports/wf_xauusd_20260713.json` |

### What Qualifies as Evidence

- Walk-forward OOS results with p-value < 0.05
- Deflated Sharpe Ratio > 0
- PBO < 0.5
- Bootstrap CI excluding zero
- Paper trading results (100+ trades, 60+ days)

### What Does NOT Qualify

- Backtest-only results (in-sample)
- Single-snapshot measurements
- "It looks profitable" without statistics
- Hypothesis registry entries with status `REJECTED` or `UNTESTED`
- Ensemble weights derived from data not yet collected

### Enforcement

1. **Document Review**: Any document claiming edge must be checked against `hypothesis_registry.json` before use in decisions
2. **Audit Trail**: If a document violates INV-012, it must be corrected or annotated with `[UNTESTED HYPOTHESIS — INV-012 violation]`
3. **Decision Gate**: No phase verdict (PASS_TO_NEXT_PHASE, etc.) may rely on documents that violate INV-012

### Current Registry Status (as of 2026-07-13)

| Trial | Strategy | Status | p-value | Verdict |
|-------|----------|--------|---------|---------|
| 1001 | RYDC Arm A | REJECTED | 0.968 | No edge |
| 1003 | Cross-Asset Momentum | REJECTED | 0.598 | No edge |
| 1004 | Session Pattern | REJECTED | 0.934 | No edge |
| 1005 | Macro Regime MR | REJECTED | 0.244 | No edge |
| 1006 | Gold-Silver Spread | REJECTED | 0.505 | No edge |

**⚠️ STOPPING RULE TRIGGERED: 4 consecutive p-value failures. Research should STOP per stopping rule.**
