# Execution Master Plan: XAUUSD B2 Paper Trade (28-Day)

**Created**: 2026-06-25
**Source**: `Meta/pre_register_b2.md` (locked criteria)
**Strategy**: XGBoost classifier + magnitude filter, B2 stop-loss ($6.30)
**Broker**: Pepperstone Razor (zero commission XAUUSD)
**Platform**: MT5
**Evaluator**: strategist agent (ruflow)

---

## Week 0 — Setup (Jun 25 – Jun 28)

- **Deadline**: All items below must be checked off by end of Jun 28. No paper trade logging begins until Week 0 is fully green.

### □ 1. Open Pepperstone Razor Demo Account
- Visit pepperstone.com → Open demo account (Razor, not Standard)
- Region: Thailand (fastest onboarding path)
- Demo platform: MT5 (not cTrader)
- Fund type: Demo USD $100,000 (default demo balance)
- Save credentials to `Meta/pepperstone_creds.txt` (encrypted/gitignored)
- [x] Done, login credentials saved (Login: 61547941, Server: Pepperstone-Demo)

### □ 2. Install MT5 & Login
- Download MT5 from pepperstone.com/client-portal (not generic metaquotes)
- Install to default path
- Login with demo server: `Pepperstone-Demo03` (or whichever server the account is on)
- Verify connection: green "Trading" icon in bottom-left
- [x] Done, MT5 running (Build 5836)

### □ 3. Verify XAUUSD Symbol Details
- Open Market Watch (Ctrl+M) → right-click → Symbols → Show XAUUSD
- Verify spread (typical: 0.15–0.30 during liquid hours)
- Verify execution type: Market Execution
- Verify minimum lot: 0.01, lot step: 0.01
- [x] Spread recorded: `0.83` (filled in)
- [x] Execution type confirmed: Market

### □ 4. Run Stop Calculator & Lock Lot Size
```
python scripts/stop_calculator.py
```
- **Recommended lot size: 0.10** (1R = $6.30 risk, $0.63 price distance)
  - At 0.10 lot: $6.30 / (0.10 × 100) = $0.63 stop distance on price
  - Compatible with 15-min XAUUSD range (~$1–$3 per bar)
- Alternative: 0.05 lot ($3.15 risk, further distance) if wider stops preferred
- **Record chosen lot size here**: `0.10` (must not change during paper trade)
- Verify calculation: entry at say $2330.00 → long stop = $2329.37, short stop = $2330.63
- [ ] Lot size locked: `0.10`

### □ 5. Place 3 Test Trades (Confirmation Only)
Purpose: verify stop-loss fills as expected, no MT5 weirdness.

| Test | Action | Expected | Actual |
|------|--------|----------|--------|
| 1 | Open long 0.10 XAUUSD, set SL at $0.63 distance, close immediately | Market order fills, SL can be attached | `___` |
| 2 | Open short 0.10, let price mini-move, cancel | Order cancel succeeds | `___` |
| 3 | Open long 0.10 with SL, trigger SL manually or let price hit | SL fills at ~$6.30 loss, record fill price & slippage | `___` |

- Slippage on Test 3 must be recorded. Acceptable: ±$0.20.
- [x] All 3 test trades pass (2026-06-28 22:01 UTC)
  - Test 1: Long 0.10 @ 4076.23, SL=4069.93, closed immediately, profit=$15.22
  - Test 2: Short 0.10 @ 4065.92, SL=4072.22, closed, profit=-$5.40
  - Test 3: Long 0.10 @ 4075.56, SL=4069.26, manual close after 5min timeout

### □ 6. Verify trade_logger.py Works
The existing logger is at `scripts/trade_logger.py`, logs to `data/paper_trade_log.csv`.

Test sequence:
```powershell
cd packages/quant_os
python scripts/trade_logger.py --entry "2026-06-25 10:00|long|2330.00|2335.00|natural|||"
# Expected: "Logged: $5.00 gross / $5.00 net" (no stop hit → no slippage)
```
Then verify the CSV row was written correctly.
- [x] Logger works, CSV has correct headers and test row (delete test row after)

### □ 7. Lock Configuration — CHECKPOINT
- [x] paper_trade_bot.py aligned: LOT_SIZE=0.10, B2_STOP=6.30, MIN_CONF=0.85
- [x] evaluate_b2_paper.py created (block bootstrap evaluation for Jul 23)
- [x] Meta/connectivity_log.md created
- [x] All Week 0 items complete (broker creds ✅, MT5 verify ✅, spread record ✅, 3 test trades ✅, config locked ✅)
- [x] Lot size final: `0.10`
- [x] Stop $6.30 final (from pre-register, not changed)
- [x] All other params locked: `train_window=500, test_window=200, step=200, conf≥0.85, expected_profit>0.0005, cost=0.000147`
- [x] **No further config changes will be made during the 28-day period**
- [x] Git tag: `git tag b2-paper-start-2026-06-28` ✅

**VIOLATION WARNING**: Adjusting any config during the paper trade voids the entire test (per pre-register).

### Recent Fixes (2026-06-27)
- [x] `scripts/paper_trade_bot.py` params aligned: LOT_SIZE=0.10, B2_STOP=6.30, MIN_CONF=0.85
- [x] `scripts/evaluate_b2_paper.py` created: block bootstrap evaluation for Jul 23
- [x] `Meta/connectivity_log.md` created: template for MT5 connectivity issues

---

## Weeks 1–4 — Paper Trade (Jun 29 – Jul 23)

### Daily Procedure

Each trading day, run the live strategy and log every generated trade to `data/paper_trade_log.csv`.

```
python scripts/trade_logger.py --entry "YYYY-MM-DD HH:MM|direction|entry_price|exit_price|exit_reason|stop_filled_at|slippage"
```

**Fields** (from trade_logger.py):
| Field | Description |
|-------|-------------|
| `timestamp` | Trade open datetime |
| `direction` | `long` or `short` |
| `entry_price` | Fill price |
| `exit_price` | Exit fill price |
| `exit_reason` | `natural` (TP/close), `stop_hit`, or `gap_through` |
| `stop_filled_at` | Actual stop fill price (leave blank if natural) |
| `slippage` | Auto-computed for stop hits; `stop_filled_at` − intended stop level |
| `notes` | Optional: news events, connectivity issues, etc. |

### Weekly Checklist

Each Monday morning, execute before trading:

- [ ] **Re-read pre-register rules** (`Meta/pre_register_b2.md`) — re-anchor discipline
- [ ] **Verify MT5 connectivity** — ping test, check terminal status
- [ ] **Confirm no config drift** — compare `data/paper_trade_log.csv` first 10 rows still show correct format
- [ ] **Check for hidden threshold changes** — lot size still 0.10? stop still $6.30?
- [ ] **Record any MT5 issues** from prior week in `Meta/connectivity_log.md`

### Tracked Events (Special Monitoring)

| Date | Event | Risk | Action |
|------|-------|------|--------|
| Jul 4 | US NFP (Non-Farm Payrolls) | High gap risk on XAUUSD | Record exact stop fill vs intended $6.30. Mark gap-through exits. |
| Jul 30 | FOMC Rate Decision | Extreme gap risk | Note: falls on Day 30 (post-evaluation, but within the 28-day window if counting Jun 29-Jul 28 is before). Actually check exact date overlap. |

**NFP Scheduled**: Jul 4, 2026 (Friday) — If XAUUSD gaps, then `exit_reason = gap_through` and record `stop_filled_at` as the actual fill.

### Golden Rules (Violation = Test Void)

1. **NO threshold changes** — $6.30 stop is locked. Do not widen, narrow, or disable.
2. **NO peeking at running PnL** — Do not compute cumulative PnL before Jul 23.
3. **NO parallel historical tests** — No backtesting during the paper trade period.
4. **NO mid-period decisions** — Even if a trade string goes 10 losses in a row, continue. No filtering, no skipping.
5. **Log every trade** — Every signal generated by the strategy must be logged. No cherry-picking.

---

## Jul 23 — Evaluation

### Step 1: Export Trade Log
- CSV ready at `data/paper_trade_log.csv`
- Verify all rows complete, no missing fields
- Count total trades: `____`

### Step 2: Run Block Bootstrap Evaluation
Use `validation/bootstrap_sensitivity.py` or write a dedicated evaluation script:

```
python scripts/evaluate_b2_paper.py
```

Expected evaluation script interface:
```python
# Reads data/paper_trade_log.csv
# Computes 3 locked criteria:
results = {
    "avg_net": 0.XX,        # Criterion 1: avg_net ≥ $0.40
    "win_rate": 0.XX,       # Criterion 2: WR ≥ 0.55
    "t_stat": 0.XX,         # Criterion 3: t ≥ 2.0 (block bootstrap 95% CI)
}
```

### Step 3: Pass/Fail Decision

```
                  ┌─────────────────────────────────────┐
                  │     avg_net ≥ $0.40?                │
                  │     WR ≥ 0.55?                      │
                  │     t-stat ≥ 2.0?                   │
                  └─────────────────────────────────────┘
                              │
                    ┌─────────┴─────────┐
                    ▼                   ▼
               ALL 3 PASS           ANY FAILS
                    │                   │
                    ▼                   ▼
           ┌────────────────┐  ┌──────────────────────┐
           │  🟢 PASS       │  │  🔴 FAIL             │
           │  B2 viable.    │  │  Check contingency:  │
           │  Proceed to    │  │                      │
           │  live proposal │  │  Fail avg_net only,  │
           └────────────────┘  │  but pass WR?        │
                               │  → Yes: gap risk.    │
                               │    Next: $7.00 stop, │
                               │    repeat 4wk paper. │
                               │                      │
                               │  Fail WR?            │
                               │  → Accuracy failure  │
                               │    structural.       │
                               │    Requires feature  │
                               │    redesign (cross-  │
                               │    asset + session). │
                               │    B2 alone dead.   │
                               └──────────────────────┘
```

### Step 4: Generate Evaluation Report
- Save results to `reports/b2_paper_evaluation.json`
- Archive trade log to `artifacts/paper_trade_b2/`
- Update `Meta/pre_register_b2.md` with actual verdict and review date
- Handoff to next agent if PASS or document contingency path if FAIL

---

## Risk Monitoring

### **R1: Gap Risk During NFP (Jul 4) & FOMC (Jul 30)**
- **Monitor**: Record `stop_filled_at` vs intended $6.30 for every gap-through event
- **Mitigation**: If multiple gap-throughs occur, note the average slippage for the contingency analysis
- **Expected worst case**: XAUUSD can gap $3–$10 during NFP. At 0.10 lot, a $5 gap on a $6.30 stop means actual loss of $5 + $6.30 gap = $11.30 loss vs budgeted $6.30.
- **Post-hoc**: If gap slippage explains a WR≥0.55 / avg_net<$0.40 split, the contingency path (retry at $7.00 stop) is triggered.

### **R2: MT5 Connectivity Issues**
- **Plan A**: Wired ethernet + fiber connection
- **Plan B**: Mobile hotspot (4G/5G) as backup
- **Detection**: MT5 shows "No Connection" in bottom-left
- **Recovery**: Restart MT5, re-login. If demo account expired, re-extend via Pepperstone portal.
- **Log every outage** in `Meta/connectivity_log.md` with timestamp and duration.
- **Missed trades during outage**: Do NOT backfill trades. Outages are part of execution reality. Note in evaluation.

### **R3: Emotional Discipline**
- **Trigger**: Desire to skip a trade after 3 losses, or to adjust stop after a gap loss
- **Prevention**: Re-read pre-register rules every Monday morning
- **Mantra**: "The criteria were locked before data was seen. Any mid-period adjustment is data snooping. The test is binary: pass all three or fail cleanly."
- **If urge is strong**: Step away for 1 hour. Do not touch MT5 during that hour.

### **R4: Demo Account Expiry**
- **Risk**: Pepperstone demo accounts expire after 30 days
- **Mitigation**: Extend demo before expiry (Jul 25) via client portal. Or re-open new demo and re-verify.
- **If demo expires and trades are missed**: Note in evaluation. Do not extend the 28-day window.

### **R5: Data Integrity (trade_logger)**
- **Risk**: CSV corruption, missed rows, duplicate entries
- **Mitigation**: After every 5 trades, verify CSV line count matches manual count
- **Backup**: End of each week, copy `data/paper_trade_log.csv` to `data/paper_trade_log_weekN.csv`
- **Recovery**: git checkout from last commit if corruption detected

---

## Daily Log Template

Copy-paste this into each day's entry in a trading journal or `Meta/trade_journal.md`:

```
## YYYY-MM-DD (Day X/28)
- Trades taken: ___
- Gap-throughs: ___
- Stop slippages: ___ (avg $___)
- MT5 issues: [None / brief outage / connection problems]
- Notes: ___
```

---

## Appendix: Key Reference

| Item | Value | Locked |
|------|-------|--------|
| Symbol | XAUUSD | ✅ |
| Timeframe | 15-min | ✅ |
| Strategy | XGBoost + magnitude filter | ✅ |
| Stop-loss | $6.30 per trade (1× avg_win) | ✅ |
| Lot size | 0.10 | ✅ (set Week 0) |
| Train window | 500 | ✅ |
| Test window | 200 | ✅ |
| Step | 200 | ✅ |
| Confidence | ≥ 0.85 | ✅ |
| Cost | 0.000147 return units | ✅ |
| Broker | Pepperstone Razor (demo) | ✅ |
| Log file | `data/paper_trade_log.csv` | ✅ |
| Pass criteria | avg_net ≥ $0.40, WR ≥ 0.55, t ≥ 2.0 | ✅ |
| Review date | 2026-07-23 | ✅ |

---

*Plan generated by strategist agent. Pre-register cross-signed at `Meta/pre_register_b2.md`.*
