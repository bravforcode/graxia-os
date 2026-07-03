# TSM Portfolio — Deployment Runbook

**Created**: 2026-07-01
**Strategy**: Time-Series Momentum (TSM) multi-asset, dual-lookback (20d + 120d), inverse-vol combined
**Status**: Pre-deployment (pending Phase 5 paper trade completion)

---

## Strategy Summary

| Parameter | Value |
|-----------|-------|
| Assets | XAUUSD, EURUSD, GBPUSD, USDJPY, BTC, ETH, SILVER, OIL |
| Lookbacks | 20-day + 120-day (combined via inverse-vol) |
| Rebalance | Weekly, Friday close |
| Vol-target | 10% annualized |
| Combined Sharpe | 1.175 |
| Sortino | 1.584 |
| Max Drawdown | -20.3% |
| PBO | 31.7% |
| Deflated Sharpe | 1.052 (significant at 95%) |
| Best WF Stability | LB=20 (0.724) |
| Broker | Pepperstone Razor (MT5) |
| Position sizing | `signal × (target_vol / realized_vol)` |

---

## 1. Pre-Deployment Checklist

**ALL items must be checked before any live capital is deployed.**

### Phase 0–4 Artifact Verification

- [ ] **Phase 0**: Kill-switch persistence confirmed
- [ ] **Phase 0**: Live-vs-demo status documented
- [ ] **Phase 1**: Multi-asset D1/H4 data pipeline verified (point-in-time correct)
- [ ] **Phase 1**: COT data feed operational
- [ ] **Phase 1**: Swap-rate feed from broker verified
- [ ] **Phase 1**: Unit tests pass for cost/scale bugs
- [ ] **Phase 2**: TSM signal code reviewed (≤4 params per signal)
- [ ] **Phase 2**: Carry signal code reviewed (if carry sleeve active)
- [ ] **Phase 3**: Deflated Sharpe passes 95% confidence
- [ ] **Phase 3**: PBO < 50% (achieved 31.7%)
- [ ] **Phase 3**: Walk-forward OOS ≥ 30% of total sample
- [ ] **Phase 4**: Portfolio construction backtest passes all gates
- [ ] **Phase 4**: Vol-targeting + inverse-vol combination verified

### Paper Trade Review (after 8–12 weeks)

- [ ] Paper trade duration ≥ 8 weeks completed
- [ ] Live slippage within backtest assumptions (±20%)
- [ ] No kill-switch false triggers during paper trade
- [ ] Data feed uptime ≥ 99.5% during paper period
- [ ] Signal generation matches backtest expectations
- [ ] Rebalance execution time < 5 minutes per cycle
- [ ] Paper trade Sharpe within 25% of backtest Sharpe

### Broker Verification

- [ ] Pepperstone Razor demo account active and tested
- [ ] All 8 symbols tradeable on MT5 (verify lot sizes, spreads)
- [ ] Crypto CFD terms confirmed (leverage, swap, spread for BTC/ETH)
- [ ] Swap/rollover rates recorded for all overnight positions
- [ ] Order execution type confirmed: Market Execution
- [ ] Minimum lot and lot step verified per symbol
- [ ] Demo account extended beyond paper trade period

### Kill-Switch Testing

- [ ] Kill-switch triggers at -15% portfolio drawdown
- [ ] Kill-switch closes all positions within 1 rebalance cycle
- [ ] Kill-switch state persists across process restarts
- [ ] Kill-switch test logged with timestamp and result
- [ ] Manual kill-switch activation tested (emergency button)
- [ ] Kill-switch reset procedure documented and tested

### Monitoring Configuration

- [ ] Prometheus metrics exporter running
- [ ] Grafana dashboards deployed (P&L, positions, risk, data freshness)
- [ ] Alert rules configured (see Section 4 — Escalation)
- [ ] Data feed staleness alert: > 1 hour since last bar
- [ ] Portfolio drawdown alert: > 10% warning, > 15% critical
- [ ] Correlation spike alert: realized cross-asset correlation > 0.7
- [ ] Kill-switch trigger alert: immediate notification
- [ ] Health check endpoint responding

### Capital Allocation

- [ ] Starting capital amount decided and documented
- [ ] Capital is risk capital (can tolerate -20% drawdown without life impact)
- [ ] Broker account funded
- [ ] Position sizing validated against starting capital
- [ ] Max position per asset ≤ 20% of portfolio verified

---

## 2. Deployment Steps

### Step 1: Verify Demo Account Connectivity

```bash
# Test MT5 connection
python scripts/verify_mt5_connection.py

# Expected output:
# - Connection: OK
# - Account type: Demo
# - Balance: $XXX,XXX
# - All 8 symbols visible in Market Watch
# - Spreads within acceptable range
```

**Acceptance criteria:**
- Green "Trading" indicator in MT5 terminal
- All 8 symbols have live bid/ask quotes
- Spread for each symbol within 2× normal range

### Step 2: Run Signal Computation (Dry-Run)

```bash
# Generate signals without placing orders
python scripts/tsm_signal_dry_run.py --date $(Get-Date -Format "yyyy-MM-dd")

# Expected output per asset:
# - XAUUSD: signal=+1 (long), vol_20d=X.XX, vol_120d=X.XX, weight=X.XX
# - EURUSD: signal=-1 (short), vol_20d=X.XX, vol_120d=X.XX, weight=X.XX
# - ...
# - Total portfolio vol target: 10%
# - Number of positions: N
```

**Acceptance criteria:**
- Signals match backtest signal logic (no drift)
- Vol calculations are reasonable (not zero, not extreme)
- Combined weights sum to approximately 1.0
- No NaN or Inf values in output

### Step 3: Verify Position Sizes Are Reasonable

```bash
# Compute target positions from signals + capital
python scripts/compute_positions.py --capital $XXX,XXX --vol-target 0.10

# Expected output:
# Symbol    | Signal | Lots  | Notional | % Portfolio
# XAUUSD    | +1     | 0.XX  | $XX,XXX  | XX%
# EURUSD    | -1     | 0.XX  | $XX,XXX  | XX%
# ...
```

**Acceptance criteria:**
- No single position > 20% of portfolio
- Total gross exposure within 200% of capital
- Position sizes are tradeable (above minimum lot)
- Crypto positions account for higher vol (smaller size)

### Step 4: Enable Kill-Switch Arm

```bash
# Arm the kill-switch with configured thresholds
python scripts/kill_switch.py arm \
  --max-dd 0.15 \
  --max-vol 0.15 \
  --max-correlation 0.70

# Verify armed status
python scripts/kill_switch.py status

# Expected output:
# Kill-switch: ARMED
# Max drawdown threshold: -15.0%
# Max realized vol threshold: 15.0%
# Max correlation threshold: 0.70
# Last test: 2026-XX-XX (PASS)
```

**Acceptance criteria:**
- Kill-switch status shows ARMED
- All thresholds match this runbook
- State file persists on disk

### Step 5: Start Weekly Rebalance Cron

```powershell
# Register the weekly rebalance task (Windows Task Scheduler)
schtasks /create /tn "TSM-WeeklyRebalance" /tr "python C:\Users\menum\graxia os\graxia\packages\quant_os\scripts\tsm_rebalance.py" /sc weekly /d FRI /st 21:00 /f

# Alternative: Use APScheduler in-process (preferred for monitoring)
python scripts/tsm_rebalance_scheduler.py --start
```

**Rebalance schedule:**
- **When**: Every Friday at 21:00 UTC (after major market closes)
- **What**: Compute new signals → calculate target positions → execute trades
- **Log**: Every rebalance logged to `data/tsm_rebalance_log.csv`
- **Alert**: Notification sent on each rebalance execution

### Step 6: Monitor First 2 Weeks Closely

**Week 1–2 heightened monitoring schedule:**

| Day | Action |
|-----|--------|
| Daily | Check P&L vs backtest expectations |
| Daily | Verify data feed freshness (all 8 symbols) |
| Daily | Review any kill-switch warnings |
| Mon | Re-read this runbook and pre-register rules |
| Wed | Mid-week position reconciliation |
| Fri | Post-rebalance verification (positions match signals) |
| Fri | Record weekly P&L, compare to backtest distribution |

**Escalation trigger during first 2 weeks:**
- Any single-day loss > 3% of portfolio → investigate immediately
- Kill-switch warning triggered → review and document
- Data feed gap > 2 hours → check broker status
- Signal mismatch vs backtest → halt and investigate

---

## 3. Risk Limits

### Position-Level Limits

| Limit | Threshold | Action if breached |
|-------|-----------|-------------------|
| Max position per asset | 20% of portfolio | Reduce to 20%, log violation |
| Max single-trade loss | 2% of portfolio | Close position, log event |
| Max lot size per symbol | Per broker margin requirements | Cap at broker limit |

### Portfolio-Level Limits

| Limit | Threshold | Action if breached |
|-------|-----------|-------------------|
| Max portfolio drawdown | -15% from peak | **Kill-switch triggers**: close all positions, halt trading |
| Max realized vol (annualized) | 15% | Reduce all positions proportionally until vol ≤ 12% |
| Max cross-asset correlation | 0.70 (rolling 20-day) | Reduce gross exposure by 30% |
| Max gross exposure | 200% of capital | Cap new positions until exposure drops |

### Vol-Target Enforcement

```
# Vol-target formula (per asset):
position_size(t) = signal(t) × (target_vol / realized_vol(t))

# Portfolio-level adjustment:
if portfolio_realized_vol > 1.2 × target_vol:
    scale_all_positions(target_vol / realized_vol)
```

### Correlation Monitoring

```python
# Rolling correlation matrix (20-day window)
# Alert if any pairwise correlation > 0.7
# Action: reduce gross exposure by 30%
# Do NOT wait for manual intervention
```

---

## 4. Escalation Procedures

### Kill-Switch Triggered

**Severity: CRITICAL**

1. **Immediate**: All positions are closed automatically by kill-switch
2. **Within 1 hour**: Review `data/kill_switch_log.csv` for trigger reason
3. **Within 4 hours**: Analyze drawdown cause (market event? correlation spike? vol explosion?)
4. **Within 24 hours**: Document findings in `Meta/incident_log.md`
5. **Before re-arming**: Root cause must be identified and addressed
6. **Re-arm procedure**:
   ```bash
   python scripts/kill_switch.py reset --reason "Root cause: [description]"
   python scripts/kill_switch.py arm --max-dd 0.15
   ```

**Decision tree:**
- Drawdown caused by single extreme event (black swan) → Re-arm after review
- Drawdown caused by strategy decay → Halt trading, investigate signal quality
- Drawdown caused by execution failure → Fix execution, then re-arm
- Drawdown cause unknown → Do NOT re-arm until identified

### Data Feed Stale

**Severity: WARNING → CRITICAL (if > 2 hours)**

1. **Detection**: Alert fires when last bar timestamp > 1 hour old
2. **Immediate check**: Is MT5 terminal connected? (green indicator)
3. **If MT5 disconnected**:
   - Restart MT5 terminal
   - Re-login with demo credentials
   - Verify all 8 symbols have live quotes
4. **If MT5 connected but data stale**:
   - Check symbol-specific feed (some symbols may have different trading hours)
   - Check broker server status (Pepperstone maintenance windows)
   - Switch to backup data source if available (Dukascopy, yfinance)
5. **If data gap > 4 hours**:
   - Skip the affected symbol for this rebalance cycle
   - Log the gap in `Meta/connectivity_log.md`
   - Do NOT backfill or interpolate missing data

### Broker Connection Lost

**Severity: CRITICAL**

1. **Detection**: MT5 shows "No Connection" or orders rejected
2. **Immediate**: Check internet connectivity (ping test)
3. **If internet down**:
   - Switch to backup connection (mobile hotspot)
   - Monitor until primary connection restored
4. **If internet up but broker down**:
   - Check Pepperstone status page
   - Wait 15 minutes, retry
   - If persistent > 30 minutes: log incident, monitor positions from mobile MT5
5. **If positions are open during outage**:
   - Do NOT attempt to close positions from unstable connection
   - Wait for stable connection before any order activity
   - Log all missed rebalance opportunities

### Unexpected Drawdown

**Severity: WARNING → CRITICAL (if approaching -15%)**

**Drawdown response ladder:**

| Drawdown Level | Action |
|----------------|--------|
| -5% | Log and monitor. No action required. |
| -8% | Review positions. Verify signals match backtest expectations. |
| -10% | **Alert**: Reduce gross exposure by 20%. Review correlation matrix. |
| -12% | **Warning**: Reduce gross exposure by 50%. Consider pausing new positions. |
| -15% | **Kill-switch**: Automatic. All positions closed. See "Kill-Switch Triggered" above. |

**Investigation checklist:**
- [ ] Is the drawdown within backtest max DD distribution? (-20.3% was the backtest max)
- [ ] Are correlations spiking? (stress regime)
- [ ] Is realized vol within expectations?
- [ ] Are signals being generated correctly?
- [ ] Is the data feed clean (no bad prices)?
- [ ] Has the market regime shifted? (trend → mean-reversion)

---

## 5. Weekly Review Checklist

**Execute every Friday after rebalance.**

- [ ] **P&L vs backtest expectations**
  - Weekly return within 1σ of backtest weekly return distribution
  - Cumulative return tracking backtest equity curve
  - Record in `data/tsm_weekly_review.csv`

- [ ] **Position reconciliation**
  - Actual positions match target positions from signal computation
  - No orphaned positions from failed order execution
  - Lot sizes within risk limits

- [ ] **Data freshness**
  - All 8 symbols have data within last 24 hours
  - No gaps in daily bars for the week
  - COT data up to date (weekly release: Friday)

- [ ] **Correlation monitoring**
  - Rolling 20-day cross-asset correlation matrix reviewed
  - No pairwise correlation > 0.70 (if so, exposure reduced)
  - Record correlation snapshot in `data/tsm_correlation_log.csv`

- [ ] **Vol-target adherence**
  - Portfolio realized vol within ±20% of 10% target
  - Per-asset vol within expected range
  - If vol drifts, position adjustments logged

- [ ] **Kill-switch health**
  - Kill-switch status: ARMED
  - No false triggers during the week
  - Thresholds unchanged

- [ ] **Execution quality**
  - Rebalance slippage within backtest assumptions
  - Order fill rate > 95%
  - No rejected orders

---

## 6. Monthly Review Checklist

**Execute first Monday of each month.**

- [ ] **Rolling Sharpe vs backtest**
  - Compute 3-month rolling Sharpe from live returns
  - Compare to backtest Sharpe (1.175)
  - Alert if rolling Sharpe < 0.5 (potential strategy decay)
  - Record in `data/tsm_monthly_review.csv`

- [ ] **Drawdown analysis**
  - Max drawdown this month vs backtest distribution
  - Drawdown duration analysis (backtest max duration: TBD)
  - Recovery time analysis
  - Is drawdown within acceptable range? (-20.3% backtest max)

- [ ] **Signal decay check**
  - Compare live signal hit-rate to backtest signal hit-rate
  - Check if 20d vs 120d lookback contribution has shifted
  - Verify signal generation matches backtest logic (no code drift)
  - If hit-rate drops > 15% from backtest → investigate

- [ ] **Rebalance cost analysis**
  - Total trading costs this month (spread + swap + commission)
  - Cost per rebalance vs backtest assumption
  - Cost as % of portfolio return
  - If costs > 2× backtest assumption → review execution

- [ ] **Regime assessment**
  - Current market regime (trending/ranging/volatile/crisis)
  - Regime-appropriate behavior check (TSM should profit in trending)
  - Correlation regime (normal/stress) — stress = all correlations → 1

- [ ] **Infrastructure health**
  - Data feed uptime this month (target: ≥ 99.5%)
  - Kill-switch test results
  - MT5 connectivity incidents
  - Any manual interventions required

---

## 7. Emergency Contacts & Resources

| Resource | Location |
|----------|----------|
| This runbook | `Meta/deployment_runbook.md` |
| Pre-registration | `Meta/pre_register_b2.md` |
| Execution plan | `Meta/deployment_runbook.md` (this file) |
| Kill-switch code | `scripts/kill_switch.py` |
| Signal computation | `scripts/tsm_signal_dry_run.py` |
| Rebalance script | `scripts/tsm_rebalance.py` |
| Position calculator | `scripts/compute_positions.py` |
| Trade log | `data/tsm_rebalance_log.csv` |
| Connectivity log | `Meta/connectivity_log.md` |
| Incident log | `Meta/incident_log.md` |
| Broker credentials | `Meta/pepperstone_creds.txt` (gitignored) |

---

## 8. Deployment Decision Tree

```
                    ┌─────────────────────────────┐
                    │  All pre-deployment items    │
                    │  checked?                    │
                    └─────────────────────────────┘
                                │
                      ┌─────────┴─────────┐
                      ▼                   ▼
                    YES                   NO
                      │                   │
                      ▼                   ▼
              ┌───────────────┐   ┌──────────────────┐
              │ Paper trade   │   │ Complete missing  │
              │ ≥ 8 weeks?    │   │ items first       │
              └───────────────┘   └──────────────────┘
                      │
                ┌─────┴─────┐
                ▼           ▼
              YES           NO
                │           │
                ▼           ▼
        ┌───────────┐ ┌──────────────────┐
        │ Paper     │ │ Continue paper   │
        │ results   │ │ trading until    │
        │ acceptable?│ │ 8 weeks complete │
        └───────────┘ └──────────────────┘
                │
          ┌─────┴─────┐
          ▼           ▼
        YES           NO
          │           │
          ▼           ▼
  ┌───────────────┐ ┌──────────────────┐
  │ Deploy with   │ │ Review strategy, │
  │ small capital │ │ adjust or abandon│
  │ (Step 1-6)    │ │                  │
  └───────────────┘ └──────────────────┘
```

---

## Appendix A: Key Configuration Values

| Parameter | Value | Source | Locked |
|-----------|-------|--------|--------|
| Vol-target | 10% annualized | Backtest optimization | ✅ |
| Lookback (short) | 20 days | WF stability best (0.724) | ✅ |
| Lookback (long) | 120 days | Standard TSM literature | ✅ |
| Combination method | Inverse-vol weighted | Moskowitz et al. methodology | ✅ |
| Rebalance frequency | Weekly (Friday close) | Matched to signal horizon | ✅ |
| Max drawdown (kill-switch) | -15% | Below backtest max (-20.3%) | ✅ |
| Max vol threshold | 15% annualized | 50% above target | ✅ |
| Max correlation | 0.70 | Regime stress indicator | ✅ |
| Max position per asset | 20% | Diversification requirement | ✅ |
| Broker | Pepperstone Razor | Zero commission on commodities | ✅ |
| Platform | MT5 | Broker-native | ✅ |

## Appendix B: Backtest Performance Reference

| Metric | Value | Notes |
|--------|-------|-------|
| Combined Sharpe | 1.175 | Across all 8 assets |
| Sortino | 1.584 | Downside risk adjusted |
| Max Drawdown | -20.3% | Historical worst case |
| PBO | 31.7% | Below 50% threshold |
| Deflated Sharpe | 1.052 | Significant at 95% confidence |
| WF Stability (LB=20) | 0.724 | Best lookback stability |
| Annualized Return | TBD | From backtest equity curve |
| Calmar Ratio | TBD | Return / Max DD |

## Appendix C: Asset-Specific Notes

| Asset | Notes |
|-------|-------|
| XAUUSD | Core asset. Zero commission on Pepperstone Razor. Best TSM evidence. |
| EURUSD | Single-pair momentum weakened per literature. Works as basket component. |
| GBPUSD | Basket component for FX diversification. |
| USDJPY | Carry-tilted pair. Monitor swap rates. |
| BTC | Crypto CFD. Higher vol → smaller position. Verify leverage/spread. |
| ETH | Crypto CFD. Higher vol → smaller position. Verify leverage/spread. |
| SILVER | Commodity. Correlated with gold in stress regimes. |
| OIL | Commodity. Diversification benefit. Monitor COT positioning. |

---

*Runbook created by executor agent. Cross-references: `Meta/multi_horizon_portfolio_redesign_plan.md`, `Meta/multi_asset_redesign_progress.md`, `Meta/deployment_runbook.md`.*
