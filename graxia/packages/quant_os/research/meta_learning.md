# Meta-Learning Ledger

**Purpose:** Record what we learn from each hypothesis — failure modes, directions to avoid, directions to pursue.

**Update rule:** Add entry within 48h of any REJECTED or PASSED hypothesis.

---

## 1. Search #1 — REJECTED (pre-2026) — trials #1-1000

**What we did:** Bulk parameter sweep across 1000+ technical-indicator combinations (EMA/RSI/MACD crosses, breakout filters, momentum thresholds) on XAUUSD and EURUSD H1.

**What the data said:** PBO ~0.5, DSR negligible, no combination showed statistical significance.

**Why it failed:** No pre-registration, no named mechanism, post-hoc arm selection = classic PBO=0.5 trap. This is the baseline "do not do this" case.

**Implication:** Every future hypothesis must have: (1) named mechanism, (2) pre-registered parameters, (3) arm selection before seeing data.

---

## 2. RYDC Arm A — REJECTED (2026-07-12) — trial #1001

**What we did:** Tested information-diffusion-lag between rates markets and gold spot. Mechanism: rates desks re-price within same session; gold retail/CFD flow is slower; 4-day continuation predicted.

**What the data said:** p=0.9680, Sharpe 0.044, win rate 51.92%, profit factor 1.01, DSR=0.16%, 52 OOS trades, 0/5 gates pass.

**Why it failed:** No diffusion lag exists. Gold prices DXY/real-yield moves contemporaneously. Macro desks hedge gold exposure in real-time. The "slow retail channel" is too thin to dominate in 2026.

**Implication:**
- Named mechanism is necessary but not sufficient — must be *active in current markets*
- "Slow retail vs fast institutional" was 1990s story. In 2026, systematic funds trade same signal with sub-day latency
- p=0.968 = strong null, not underpowering. Do NOT retry with more data
- Do NOT pivot to Arm B without separate pre-registration
- Cross-asset XAUUSD framing is 0-for-1

---

## 3. Cross-Asset Momentum (CAM) — REJECTED (2026-07-13) — trial #1003

**What we did:** DXY z-score extremes predicting XAUUSD follow-through over 1-5 days. Same diffusion-lag framing as RYDC but simpler.

**What the data said:** p=0.5976, Sharpe 0.361, win rate 56.3%, 135 OOS trades, WFA 20%, WFE=0, DSR=82.3%, Bootstrap CI [-0.95, 1.51]. 1/6 gates pass.

**Why it failed:** Same null as RYDC — DXY momentum does not predict XAUUSD follow-through. p=0.60 is coin-flip.

**Implication:** Cross-asset momentum framing is 0-for-2 (RYDC + CAM). Category exhausted for XAUUSD.

---

## 4. Session Pattern (SP) — REJECTED (2026-07-13) — trial #1004

**What we did:** Session-conditional behavior — MR in Asian, momentum in London/NY.

**What the data said:** p=0.9338, Sharpe 0.056, win rate 48.9%, 141 OOS trades, WFA 60%, WFE=0.327, DSR=0.47%. 1/6 gates pass.

**Why it failed:** p=0.93 is the most null result yet. Win rate 48.9% = random.

**Implication:** Session patterns on XAUUSD daily = null. Mechanism plausible but too thin.

---

## 5. Macro Regime MR (MRM) — REJECTED (2026-07-13) — trial #1005

**What we did:** DFII10 CV classifies STABLE vs TRENDING; MR in stable, momentum in trending.

**What the data said:** p=0.2441, Sharpe -1.157, win rate 46.2%, 65 OOS trades, WFA 40%, WFE=0, DSR=0%. 0/6 gates pass.

**Why it failed:** Negative Sharpe — strategy LOSES money. Under 100 trades target.

**Implication:** Regime-conditional MR on XAUUSD using DFII10 is actively harmful.

---

## 6. Consecutive Gate Failure Tracker

| Gate | Count | Last Failed | Threshold | Status |
|------|-------|-------------|-----------|--------|
| p-value | 4 | MRM | 3 | **STOP TRIGGERED** |
| WFA OOS positive | 4 | MRM | 3 | **STOP TRIGGERED** |
| WFE | 3 | MRM | 3 | **STOP TRIGGERED** |
| DSR | 4 | MRM | 3 | **STOP TRIGGERED** |
| Bootstrap CI | 4 | MRM | 3 | **STOP TRIGGERED** |
| Min trades | 1 | MRM | 3 | ok |

**⚠️ STOPPING RULE §3.4 TRIGGERED:** 4 consecutive p-value failures (RYDC, CAM, SP, MRM). Research should STOP per stopping rule. Re-examine: gate calibration, data quality, research direction.

---

## 7. Gold-Silver Spread (GSS) — REJECTED (2026-07-13) — trial #1006

**What we did:** Direction B — XAU/XAG ratio z-score mean-reversion. Structurally different from prior (pair trade, not lead-lag).

**What the data said:** p=0.5045, Sharpe -0.963, win rate 41.9%, 31 OOS trades, 0/6 gates pass.

**Why it failed:** Negative Sharpe — loses money. 31 trades < 100 target. The gold/silver ratio may not mean-revert at daily frequency, or the reversion is too slow for 10-day hold.

**Implication:** Pair MR on precious metals = null at daily frequency.

---

## 8. BTC Vol Clustering (BVC) — REJECTED (2026-07-13) — trial #1007

**What we did:** Direction B — BTCUSD vol spike continuation. Different instrument (crypto) + different mechanism (vol clustering).

**What the data said:** p=0.2479, Sharpe 1.739, win rate 72.4%, 29 OOS trades, 0/5 gates pass.

**Why it failed:** Interesting metrics (72.4% win rate, Sharpe 1.74) but only 29 trades < 100 target, p=0.25 not significant. Underpowered for this mechanism.

**Implication:** BTC vol clustering may have something, but sample too small. Could be worth revisiting with more data or lower threshold — but must be new pre-registration.

---

## 9. Cross-Asset Vol Rank (CVR) — REJECTED (2026-07-13) — trial #1008

**What we did:** Direction B — Relative vol percentile value across assets.

**What the data said:** p=0.6101, Sharpe -0.402, win rate 51.0%, 102 OOS trades, 1/6 gates pass.

**Why it failed:** Negative Sharpe. 102 trades pass min, but all other gates fail. Vol rank alone is not predictive.

**Implication:** Vol percentile value on XAUUSD = null.

---

## 10. Consecutive Gate Failure Tracker (Updated After Direction B)

| Gate | Count (Direction B) | Last Failed | Threshold | Status |
|------|---------------------|-------------|-----------|--------|
| p-value | 3 | CVR | 3 | **STOP TRIGGERED (again)** |
| WFA OOS positive | 3 | CVR | 3 | **STOP TRIGGERED (again)** |
| WFE | 3 | CVR | 3 | **STOP TRIGGERED (again)** |
| DSR | 3 | CVR | 3 | **STOP TRIGGERED (again)** |
| Bootstrap CI | 3 | CVR | 3 | **STOP TRIGGERED (again)** |
| Min trades | 1 | GSS | 3 | ok |

**⚠️ STOPPING RULE §3.4 TRIGGERED AGAIN:** 3 consecutive p-value failures in Direction B (GSS, BVC, CVR). Research should STOP again.

**Combined across both directions:** 8 hypotheses tested, 0 passed any gate. This is a very strong signal that edge is not accessible with current data/methodology.

---

## 11. Program Closure (2026-07-13) — Direction A chosen

**Decision:** STOP. No more hypotheses in this research program.

**Rationale:** p-values 0.24-0.97 all far from 0.05. This is absence of effect, not underpowering. Stopping rule fired twice independently. 8/8 REJECTED.

**Locked files:**
- `research/hypothesis_registry.json` (SHA: `1c65c799...`)
- `research/trial_ledger.json` (SHA: `efb11848...`)
- `data/sacred_holdout/holdout.csv` (SHA: `5a15961c...`) — never opened
- `reports/stopping_rule_2026_07_12.md` (SHA: `db3b8179...`)

**What was built (reusable):**
- Validation pipeline (DSR/WFE/PBO gates)
- Sacred holdout mechanism
- Stopping rule framework
- Pre-registration template
- Kill-switch/alert routing tests
- Cost calibration (16 assets)

**What remains:**
- KillSwitch/StateCoordinator wiring gap (must fix before live)
- Sacred holdout stays locked (for future Direction C if pursued)

**Closure report:** `reports/program_closure_2026_07.md`

---

## Conventions

- Entries appended chronologically. Do not delete past entries.
- Each entry: hypothesis id, what done, what data said, why failed/passed, implication.
- Cross-link to `reports/hypothesis_*.md` for full quantitative report.
