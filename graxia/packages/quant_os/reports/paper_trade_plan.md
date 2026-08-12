# Paper Trade Plan — Multi-Asset Quantitative Trading System

> **Version:** 1.0
> **Created:** 2026-07-01
> **Branch:** multi-asset-redesign-2026
> **Broker:** Pepperstone (MT5 Demo)
> **Symbols:** XAUUSD, EURUSD, BTCUSD, ETHUSD
> **Capital:** $10,000 (paper)

---

## 1. Overview

This plan defines the 4-week paper trading preparation, execution, and evaluation
process for the multi-asset quantitative trading system. Paper trading validates
signal quality, execution reliability, and risk management before any live capital
is deployed.

**Non-negotiable minimums (from CONSTITUTION.md golden rules):**
- 60 calendar days paper trading before live micro stage
- 100 completed trades minimum
- AI cannot directly submit live orders
- Maximum 1% risk per trade, 15% hard stop drawdown

---

## 2. Week-by-Week Schedule

### Week 0 (Preparation) — Current Week

**Goal:** All infrastructure validated, configuration generated, readiness confirmed.

| Day | Task | Status |
|-----|------|--------|
| Mon | Generate paper trade config (`scripts/paper_trade_config.py`) | |
| Mon | Run readiness checklist (`scripts/paper_trade_checklist.py`) | |
| Tue | Pull fresh data for all 4 symbols (M15, H1, D1) | |
| Tue | Verify ML models are trained and available | |
| Wed | Test MT5 connection on Pepperstone-Demo | |
| Wed | Validate Telegram alerts working | |
| Thu | Run dry-run simulation (no orders placed) | |
| Fri | Review dry-run output, fix any issues | |

**Week 0 exit criteria:**
- [ ] `paper_trade_config.json` generated and reviewed
- [ ] `paper_trade_readiness.json` shows all required checks PASS
- [ ] MT5 connection stable for 24+ hours
- [ ] Telegram alerts received for test message
- [ ] Dry-run simulation completed without errors

---

### Week 1 (Soft Start) — Days 1-7

**Goal:** System runs 24/7, generating signals but minimal execution.

| Time (UTC) | Action | Notes |
|------------|--------|-------|
| 00:30 | Data pull (M15, D1) | Via `data_pipeline.py` |
| 01:00 | Feature build | ML features + technical indicators |
| 01:15 | Signal generation | Ensemble model predictions |
| 01:30 | Execution (paper) | Only high-confidence signals (≥0.75) |
| 22:00 | Daily P&L report | Via `monitor_paper_trades.py` |

**Week 1 targets:**
- Trade only 1-2 symbols (XAUUSD, EURUSD)
- Max 2 trades per day total
- Focus on signal quality over quantity
- Daily report review at 22:00 UTC

**Week 1 metrics to track:**
- Signal generation count per symbol
- Trade execution count
- Daily P&L (realized + unrealized)
- Drawdown percentage
- Telegram alert delivery rate

---

### Week 2 (Expand) — Days 8-14

**Goal:** Add BTCUSD and ETHUSD, increase trade frequency.

| Time (UTC) | Action | Notes |
|------------|--------|-------|
| 00:30 | Data pull (all 4 symbols, M15, H1, D1) | |
| 01:00 | Feature build | Cross-asset correlation features |
| 01:15 | Signal generation | Full ensemble, lower confidence threshold (0.65) |
| 01:30 | Execution (paper) | All 4 symbols |
| 22:00 | Daily P&L report | |

**Week 2 targets:**
- All 4 symbols active
- Max 4 trades per day
- Begin correlation monitoring
- Verify news filter blocks correctly

**Week 2 metrics to track:**
- Per-symbol win rate
- Cross-asset correlation matrix
- News event blocking events
- Slippage simulation vs actual MT5 spread

---

### Week 3 (Stress Test) — Days 15-21

**Goal:** Validate risk management under adverse conditions.

| Day | Focus |
|-----|-------|
| Mon | Normal trading, baseline metrics |
| Tue | Simulated high-volatility regime |
| Wed | News event filter validation |
| Thu | Max position count test (4 open simultaneously) |
| Fri | Weekly review and report |

**Week 3 targets:**
- Risk limits are hit at least once (to validate circuit breakers)
- Kill switch triggers correctly at 15% drawdown
- News filter blocks trades during NFP/FOMC
- Position correlation monitoring works

---

### Week 4 (Go/No-Go) — Days 22-28

**Goal:** Final evaluation, produce go-live recommendation.

| Day | Action |
|-----|--------|
| Mon-Tue | Normal trading, collect final metrics |
| Wed | Complete 4-week performance report |
| Thu | Review against go-live criteria (Section 5) |
| Fri | Go/No-Go decision and documentation |

**Week 4 exit criteria:**
- [ ] All 4 weeks completed
- [ ] 100+ trades executed
- [ ] Go-live criteria evaluated
- [ ] Final report generated

---

## 3. Daily Routine

### Morning Routine (00:30-01:30 UTC)

```bash
# 1. Pull latest data
python scripts/data_pipeline.py pull --symbols XAUUSD EURUSD BTCUSD ETHUSD --timeframes M15 H1 D1

# 2. Check readiness (optional daily check)
python scripts/paper_trade_checklist.py

# 3. System auto-generates signals and executes paper trades
# (handled by paper_trade_bot.py or scheduled cron)
```

### Evening Review (22:00 UTC)

```bash
# 1. Generate daily report
python scripts/monitor_paper_trades.py

# 2. Check risk limits
python scripts/monitor_paper_trades.py --check-risk

# 3. Review Telegram alerts for the day
```

### Weekly Review (Friday 22:00 UTC)

1. Generate weekly P&L summary
2. Review win rate per symbol
3. Check drawdown trajectory
4. Review correlation matrix changes
5. Update paper_trade_plan.md status
6. Decide on Week 2/3/4 adjustments

---

## 4. Configuration

### Symbol Settings

| Symbol | Lot Size | SL (pips) | TP (pips) | Max Positions | Min Confidence |
|--------|----------|-----------|-----------|---------------|----------------|
| XAUUSD | 0.01 | 30 | 60 | 1 | 0.65 |
| EURUSD | 0.01 | 20 | 40 | 1 | 0.60 |
| BTCUSD | 0.01 | 500 | 1000 | 1 | 0.65 |
| ETHUSD | 0.01 | 30 | 60 | 1 | 0.65 |

### Risk Limits

| Parameter | Value | Notes |
|-----------|-------|-------|
| Risk per trade | 1% | Hard limit from golden rules |
| Daily loss limit | 2% | Circuit breaker |
| Max drawdown | 10% | Paper trading limit |
| Kill switch | 15% | Halt all trading |
| Max positions | 4 | One per symbol |
| Initial capital | $10,000 | Paper only |

### Trading Hours (UTC)

| Symbol | Start | End | Notes |
|--------|-------|-----|-------|
| XAUUSD | 01:00 | 21:00 | Avoid low-liquidity window |
| EURUSD | 01:00 | 21:00 | London/NY overlap preferred |
| BTCUSD | 00:00 | 23:59 | 24/7 market |
| ETHUSD | 00:00 | 23:59 | 24/7 market |

### News Filter

- **Pre-block:** 30 minutes before HIGH importance events
- **Post-block:** 15 minutes after HIGH importance events
- **Blocked events:** NFP, FOMC, ECB/BOJ rate decisions, US/EU CPI, US GDP

---

## 5. Go-Live Criteria

Paper trading is considered successful when ALL of the following are met:

### Performance Metrics

| Metric | Threshold | Notes |
|--------|-----------|-------|
| Total trades | >= 100 | Minimum sample size |
| Win rate | >= 45% | After accounting for R:R ratio |
| Profit factor | >= 1.2 | Gross profit / gross loss |
| Max drawdown | < 10% | From equity high |
| Sharpe ratio (daily) | >= 0.5 | Risk-adjusted return |
| Avg R:R ratio | >= 1.5 | Average win / average loss |

### System Metrics

| Metric | Threshold | Notes |
|--------|-----------|-------|
| Uptime | >= 95% | System availability |
| Signal generation | No missed days | All scheduled runs completed |
| Telegram alerts | 100% delivery | No missed alerts |
| Data freshness | < 30 minutes stale | Max delay for M15 data |
| Risk limit hits | 0 breaches | All limits respected |

### Risk Management

| Metric | Threshold | Notes |
|--------|-----------|-------|
| Daily loss limit | Never breached | 2% daily limit respected |
| Kill switch | Never triggered | 15% drawdown not reached |
| Position count | Always <= 4 | Max positions respected |
| Stop loss | 100% of trades | Every trade has SL |

### Qualitative Assessment

- [ ] Signal quality consistent across all 4 symbols
- [ ] News filter blocking appropriately
- [ ] No suspicious pattern (curve-fitting, overtrading)
- [ ] Risk management feels appropriate (not too tight/loose)
- [ ] Mental bandwidth manageable (not overwhelming)

---

## 6. Rollback Plan

### Trigger Conditions (HALT paper trading and escalate)

| Condition | Action |
|-----------|--------|
| Drawdown > 10% | Pause all new trades, investigate |
| Drawdown > 15% | Kill switch activated, halt trading |
| Daily loss > 2% | Halt trading for the day |
| MT5 disconnection > 4 hours | Investigate connectivity |
| Data pipeline failure > 24 hours | Investigate data sources |
| Signal quality degradation (win rate < 30% over 20 trades) | Retrain models |
| Any code error causing unintended behavior | Rollback to last known good commit |

### Rollback Procedure

1. **Stop all trading:** Set kill switch to ACTIVE via Telegram or manually
2. **Preserve state:** Archive current paper_trade_log.csv and monitor_state.json
3. **Investigate:** Run `paper_trade_checklist.py` and review logs
4. **Decision point:**
   - If code issue: revert to last stable commit, re-run checklist
   - If model issue: retrain on fresh data, validate on holdout
   - If data issue: investigate source, pull fresh data
5. **Resume only after:** Checklist passes, dry-run completes, manual review

### Emergency Contacts

- Kill switch Telegram command: `/kill`
- Manual kill switch file: `data/kill_switch_state.json`
- MT5 manual shutdown: Close terminal window

---

## 7. Tools and Scripts

| Script | Purpose | Frequency |
|--------|---------|-----------|
| `scripts/paper_trade_config.py` | Generate/update configuration | Once + as needed |
| `scripts/paper_trade_checklist.py` | Validate readiness | Daily |
| `scripts/monitor_paper_trades.py` | P&L computation + alerts | Every 5 min (continuous) |
| `scripts/data_pipeline.py pull` | Pull latest OHLCV data | Daily 00:30 UTC |
| `scripts/paper_trade_bot.py` | Signal generation + execution | 15-min intervals |
| `risk/kill_switch.py` | Emergency halt | Always-on |

---

## 8. Reporting

### Daily Report (`reports/paper_trades/daily_YYYY-MM-DD.md`)

- Trade count, wins/losses, win rate
- Realized + unrealized P&L
- Equity and drawdown
- Risk limit status

### Weekly Report (Friday)

- Aggregate daily reports
- Per-symbol performance breakdown
- Correlation matrix snapshot
- Regime analysis (what market conditions dominated)
- Model performance vs backtest expectations

### Final Report (Week 4)

- 4-week cumulative performance
- Go-live recommendation (YES/NO/CONDITIONAL)
- Outstanding issues or concerns
- Recommendations for live micro stage

---

## 9. Notes

- **Paper != Live:** Slippage, latency, and execution quality in paper trading
  will differ from live. Account for this in go-live criteria.
- **Overfitting risk:** If paper results significantly outperform backtest,
  suspect overfitting rather than celebrating.
- **Market regime:** 4 weeks may not cover all regimes. Be cautious about
  extrapolation to live trading conditions.
- **Correlation:** BTC and ETH are highly correlated. Monitor position correlation
  to avoid hidden concentration risk.
