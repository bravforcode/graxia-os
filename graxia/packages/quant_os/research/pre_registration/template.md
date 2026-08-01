# Hypothesis Pre-Registration — [HYPOTHESIS NAME]

**Status:** DRAFT — not yet locked.
**Cumulative trial count entering this test:** [from research/trial_ledger.json]
**Trial number for this hypothesis:** [from research/auto_increment_trial.py]
**Date drafted:** YYYY-MM-DD

---

## 1. Economic Rationale

[Name the falsifiable mechanism. What economic force produces the predicted return? Why would this force exist in 2026 markets and not be arbitraged away instantly?]

Required:
- Named behavioral/structural cause (not "indicator X predicts Y")
- Why the effect is plausibly persistent for the chosen horizon
- Clear, testable prediction

## 2. Arm Selection — ONE Arm, Picked Before Testing

| Arm | Prediction | Mechanism |
|---|---|---|
| **A — [name]** | [prediction] | [why] |
| B — [name] | [prediction] | [why] |

**Registered choice: Arm [A/B].** Testing both and keeping whichever wins = PBO=0.50 failure mode. Unchosen arm requires separate pre-registration.

## 3. Data Requirements

| Series | Source | Frequency | Min. history |
|---|---|---|---|
| [instrument] | [source] | [freq] | [years — must span 2+ regimes] |

## 4. Feature Construction (exact, no discretion)

```
[Frozen pseudocode. Coefficients estimated on data through t-1 only.]
signal_t = f(data_{t-1}, params)
```

## 5. Signal & Trade Rule (fixed — cannot be tuned after seeing results)

- **Entry long:** [exact conditions]
- **Entry short:** [exact conditions]
- **Exit:** [exact conditions]
- **Stop-loss:** [exact, e.g. 1.5 × ATR(14)]
- **Sizing:** [fixed-fractional]
- **Filters:** [e.g. FOMC/CPI 48h exclusion]

## 6. Validation Gates — Identical to Existing Pipeline, No Relaxation

| Gate | Threshold | Note |
|---|---|---|
| p-value | < 0.05 | two-sided t-test, OOS only |
| WFA OOS positive | ≥ 70% | |
| WFE | ≥ 0.5 & < 1.5 | |
| Deflated Sharpe | > 0.95 | cumulative trial count |
| PBO | < 0.5 | only if in-sample selection occurred |
| Bootstrap CI | excludes 0 | block bootstrap |
| Min trades | ≥ 100 | |

## 7. Sample Size Check

[Estimate expected non-overlapping signals. Compare to ≥100 target.]

## 8. Pre-Registration Lock Checklist

- [ ] Arm chosen in §2
- [ ] IS/OOS split fixed
- [ ] Parameters frozen
- [ ] DSR uses cumulative trial count
- [ ] Go/no-go criteria match pipeline
- [ ] Sample-size decision made
- [ ] Trial number allocated
- [ ] Document hashed at lock

---

## 9. Validation Results — [PASSED/REJECTED] (fill after running)

**Date:**
**Verdict:**
**Trial count after:**

| Gate | Value | Threshold | Status |
|---|---|---|---|
| p-value | | < 0.05 | |
| WFA | | ≥ 70% | |
| WFE | | ≥ 0.5 | |
| DSR | | > 0.95 | |
| PBO | | < 0.5 | |
| Bootstrap CI | | > 0 | |
| Min trades | | ≥ 100 | |
