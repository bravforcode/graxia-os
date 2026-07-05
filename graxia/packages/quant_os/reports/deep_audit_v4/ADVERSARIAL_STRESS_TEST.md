# ADVERSARIAL STRESS TEST
**Phase 13 | 2026-07-05 | TIER 1**

---

## 13.1 — Label/Target Shuffling (Null Hypothesis)

### Status: PARTIALLY IMPLEMENTED

**Implementation:** `tests/test_label_shuffling.py` exists with:
- `run_label_shuffle_test()` — shuffles labels, computes Sharpe distribution
- 100 permutations by default
- p-value = fraction of null >= real Sharpe
- Survives if real > 95th percentile AND p < 0.05

### CRITICAL GAP
The test uses **synthetic random data** (`np.random.randn` for features, `np.random.choice` for labels) — NOT actual strategy features and labels. This tests the test framework, not the actual edge.

```python
# test_label_shuffling.py:138-141
def synthetic_data():
    np.random.seed(42)
    n = 500
    features = np.random.randn(n, 10)
    labels = np.random.choice([-1, 0, 1], size=n, p=[0.3, 0.4, 0.3])
```

**Required:** Run on actual MTM/MRB/MLB features from `artifacts/features_v2/` with real `target_return` labels.

### Status
| Test | Run on Synthetic? | Run on Real Data? | Survives? |
|---|---|---|---|
| Label shuffling | YES | **NO** | N/A |

---

## 13.2 — Synthetic/Surrogate Data Injection
- **Not performed**
- **Status:** `[NOT PERFORMED]`

## 13.3 — Cost & Friction Perturbation
- **Not performed** — no 0.5×/2×/5× spread re-runs found
- **Status:** `[NOT PERFORMED]`

## 13.4 — Outlier / Single-Trade Sensitivity
- **Not performed**
- **Status:** `[NOT PERFORMED]`

## 13.5 — Time-Period Sensitivity
- **Not performed**
- **Status:** `[NOT PERFORMED]`

## 13.6 — Parameter Perturbation Stability
- **Not performed**
- **Status:** `[NOT PERFORMED]`

---

## 13.7 — Adversarial Summary Table

| Stress Test | Run? | Result | Survives? |
|---|---|---|---|
| Label shuffling (null distribution) | Synthetic only | N/A | **UNVERIFIED** |
| Synthetic/surrogate data injection | NO | — | **UNVERIFIED** |
| Cost perturbation (0.5×–5×) | NO | — | **UNVERIFIED** |
| Best-trade/best-week removal | NO | — | **UNVERIFIED** |
| Leave-one-month-out | NO | — | **UNVERIFIED** |
| Parameter perturbation ±10–20% | NO | — | **UNVERIFIED** |

**None of the mandatory adversarial tests have been run on actual strategy data.**

## 13.8 — Per-Strategy Testing
- No per-strategy (MTM/MRB/MLB) adversarial testing found
- No ensemble-level adversarial testing found
