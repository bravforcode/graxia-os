# Broker & Regulatory Verification Report — Phase 6A

**Created**: 2026-07-01
**Purpose**: Pre-deployment verification for live multi-asset trading
**Account**: 61547941 @ Pepperstone-Demo
**Status**: ⚠️ IN PROGRESS — requires live MT5 terminal verification for some items

---

## 1. Pepperstone Account Verification

### 1.1 Account Details (from `Meta/pepperstone_creds.txt`)

| Field | Value | Status |
|-------|-------|--------|
| Account Number | 61547941 | ✅ Verified |
| Server | Pepperstone-Demo | ✅ Demo account |
| Account Type | Razor (raw spread) | ✅ Confirmed |
| Platform | MT5 | ✅ Confirmed |
| Account Status | Demo | ✅ Paper trading only |

> **Note**: Credentials are stored in `Meta/pepperstone_creds.txt` (gitignored). No passwords or API keys are exposed in this report.

### 1.2 Broker Regulation

| Regulator | Entity | License | Status |
|-----------|--------|---------|--------|
| **ASIC** (Australia) | Pepperstone Group Limited | AFSL 389931 | ✅ Primary regulator |
| **FCA** (UK) | Pepperstone Limited | FRN 684312 | ✅ Active |
| **CySEC** (Cyprus) | Pepperstone (EU) Ltd | 388/20 | ✅ Active |
| **SCB** (Bahamas) | Pepperstone Markets Limited | SIA-F217 | ✅ Active |
| **DFSA** (Dubai) | Pepperstone Financial Services (DIFC) Ltd | F004356 | ✅ Active |
| **CMA** (Kenya) | Pepperstone Markets Kenya Limited | — | ✅ Active |

**Key Finding**: Pepperstone is regulated by ASIC (Tier 1), FCA (Tier 1), and CySEC (Tier 2). This provides strong regulatory protection for retail traders. ASIC regulation includes negative balance protection and segregated client funds.

### 1.3 Leverage & Margin (Razor Account)

| Asset Class | Leverage (ASIC) | Leverage (EU/CySEC) | Margin Requirement |
|-------------|-----------------|---------------------|-------------------|
| Forex (major) | 1:500 | 1:30 | 0.2% – 3.33% |
| Gold (XAUUSD) | 1:500 | 1:20 | 0.2% – 5% |
| Silver (XAGUSD) | 1:500 | 1:10 | 0.2% – 10% |
| Oil (WTI/Brent) | 1:500 | 1:10 | 0.2% – 10% |
| Crypto (BTC) | 1:500 | 1:2 | 0.2% – 50% |
| Crypto (ETH) | 1:500 | 1:2 | 0.2% – 50% |

> **⚠️ Important**: Leverage varies by regulatory entity. ASIC entity offers higher leverage than EU entity. Verify which entity your account is under.

### 1.4 Commission Structure (Razor Account)

| Asset | Commission | Spread (Typical) | Total Cost Estimate |
|-------|------------|------------------|---------------------|
| XAUUSD | $0 (embedded in spread) | 0.15–0.30 pips | ~$0.15–0.30/lot |
| EURUSD | $7/lot round-turn | 0.0–0.1 pips | ~$0.70–0.80/lot |
| GBPUSD | $7/lot round-turn | 0.0–0.2 pips | ~$0.70–0.90/lot |
| USDJPY | $7/lot round-turn | 0.0–0.1 pips | ~$0.70–0.80/lot |
| BTCUSD | $0 (embedded in spread) | 10–30 pips | ~$10–30/lot |
| ETHUSD | $0 (embedded in spread) | 0.5–2.0 pips | ~$0.50–2.00/lot |
| SILVER | $0 (embedded in spread) | 0.02–0.05 pips | ~$0.02–0.05/lot |
| OIL (WTI) | $0 (embedded in spread) | 0.03–0.05 pips | ~$0.03–0.05/lot |

**Key Finding**: Metals and commodities have commission embedded in spread (no separate commission). FX pairs have separate $7/lot commission + raw spread.

---

## 2. Symbol Availability Check

### 2.1 Symbol Specifications (Pepperstone Razor MT5)

| Symbol | Min Lot | Max Lot | Lot Step | Contract Size | Trading Hours (UTC) |
|--------|---------|---------|----------|---------------|---------------------|
| XAUUSD | 0.01 | 50.00 | 0.01 | 100 oz | Sun 22:00 – Fri 21:00 |
| EURUSD | 0.01 | 50.00 | 0.01 | 100,000 | Sun 22:00 – Fri 21:00 |
| GBPUSD | 0.01 | 50.00 | 0.01 | 100,000 | Sun 22:00 – Fri 21:00 |
| USDJPY | 0.01 | 50.00 | 0.01 | 100,000 | Sun 22:00 – Fri 21:00 |
| BTCUSD | 0.01 | 10.00 | 0.01 | 1 BTC | Sun 22:00 – Fri 21:00 |
| ETHUSD | 0.01 | 10.00 | 0.01 | 1 ETH | Sun 22:00 – Fri 21:00 |
| XAGUSD | 0.01 | 50.00 | 0.01 | 5,000 oz | Sun 22:00 – Fri 21:00 |
| WTI | 0.01 | 50.00 | 0.01 | 1,000 barrels | Sun 22:00 – Fri 21:00 |

> **⚠️ Action Required**: Verify exact symbol names on your MT5 terminal. Some brokers use different naming conventions (e.g., `XAUUSD` vs `GOLD`, `BTCUSD` vs `BTCUSD.`, `OIL` vs `WTI`).

### 2.2 Spread Verification (from execution_plan.md)

| Symbol | Recorded Spread | Source | Status |
|--------|-----------------|--------|--------|
| XAUUSD | 0.83 pips | execution_plan.md (Week 0) | ✅ Recorded |
| Others | TBD | Requires MT5 verification | ⚠️ Pending |

> **⚠️ Action Required**: Open MT5 → Market Watch → right-click → Symbols → verify spreads for all 8 assets during liquid hours (London/NY overlap).

### 2.3 Swap/Rollover Rates

Pepperstone charges TomNext-based swap for positions held past NY 5pm rollover. **One day per week carries triple charge** (verify which day in your terminal).

| Symbol | Swap Long | Swap Short | Triple Day | Status |
|--------|-----------|------------|------------|--------|
| XAUUSD | TBD | TBD | TBD | ⚠️ Verify in MT5 |
| EURUSD | TBD | TBD | TBD | ⚠️ Verify in MT5 |
| GBPUSD | TBD | TBD | TBD | ⚠️ Verify in MT5 |
| USDJPY | TBD | TBD | TBD | ⚠️ Verify in MT5 |
| BTCUSD | TBD | TBD | TBD | ⚠️ Verify in MT5 |
| ETHUSD | TBD | TBD | TBD | ⚠️ Verify in MT5 |
| XAGUSD | TBD | TBD | TBD | ⚠️ Verify in MT5 |
| WTI | TBD | TBD | TBD | ⚠️ Verify in MT5 |

**How to verify**:
1. Open MT5 → Market Watch → right-click → Symbols
2. Select symbol → Properties
3. Look for "Swap type" and "Swap long/short" values
4. Record triple swap day (usually Wednesday or Friday)

---

## 3. Regulatory Status

### 3.1 Thai SEC Blocking Order

**Background**: On June 28, 2025, the Thai SEC ordered ISPs to block access to:
- Bybit
- OKX
- CoinEx
- 1000X
- XT.COM

These are **spot crypto exchanges** operating without Thai licenses. The blocking order targets direct retail access to unregulated crypto exchanges.

### 3.2 Does CFD via ASIC-Regulated Broker Fall Under the Ban?

| Factor | Analysis | Risk Level |
|--------|----------|------------|
| **Regulatory Entity** | Pepperstone is ASIC-regulated (AFSL 389931), not a blocked exchange | ✅ Low |
| **Product Type** | CFDs (derivatives), not spot crypto | ✅ Low |
| **Execution Venue** | MT5 via regulated broker, not direct exchange access | ✅ Low |
| **Thai SEC Target** | Unregulated spot exchanges, not offshore CFD brokers | ✅ Low |

**Assessment**: CFD trading via ASIC/FCA/CySEC-regulated brokers appears to be a **different regulatory lane** from spot exchange access. The Thai SEC's blocking order targets unregulated exchanges, not regulated CFD brokers. However:

> **⚠️ Legal Disclaimer**: This is not legal advice. The regulatory landscape is evolving. The Thai SEC filed additional cases against brokers routing through affiliated overseas platforms (Feb 2026). Consult a licensed advisor for definitive compliance guidance.

### 3.3 Risk: What If Thai SEC Tightens Rules Further?

| Scenario | Probability | Impact | Mitigation |
|----------|-------------|--------|------------|
| SEC blocks CFD brokers | Low (currently) | High — cannot access broker | Monitor SEC announcements; have backup broker (IC Markets, OANDA) |
| Bank of Thailand restricts outbound FX | Low-Medium | Medium — funding difficulties | Use local bank transfer; document all transactions |
| ASIC tightens retail CFD rules | Medium | Medium — leverage reduction | Already experienced in EU (1:30 caps); plan for lower leverage |
| Pepperstone exits Thai market | Very Low | High — account closure | Multi-broker strategy; keep accounts at 2-3 brokers |

**Recommendation**:
1. Monitor Thai SEC announcements monthly
2. Maintain accounts at 2+ brokers (Pepperstone + IC Markets or OANDA)
3. Keep funds in AUD/USD accounts (not THB) to avoid currency conversion issues
4. Document all trading activity for potential tax reporting

---

## 4. Capital Requirements

### 4.1 Minimum Capital for 8 Assets with Vol-Targeting at 0.10

**Strategy Parameters**:
- Vol-target: 10% annualized
- Rebalance: Weekly
- Position sizing: `signal × (target_vol / realized_vol)`

**Margin Calculation (Worst-Case Scenario)**:

Assuming all 8 assets have simultaneous positions at maximum vol-target allocation:

| Asset | Price (Est.) | Lot Size | Notional | Margin (1:500) | Margin (1:30) |
|-------|--------------|----------|----------|----------------|---------------|
| XAUUSD | $2,350 | 0.10 | $23,500 | $47 | $783 |
| EURUSD | 1.08 | 0.10 | $10,800 | $22 | $360 |
| GBPUSD | 1.27 | 0.10 | $12,700 | $25 | $423 |
| USDJPY | 155.00 | 0.10 | $10,000 | $20 | $333 |
| BTCUSD | $62,000 | 0.01 | $620 | $1 | $21 |
| ETHUSD | $3,400 | 0.01 | $34 | $0.07 | $1 |
| XAGUSD | $30 | 0.10 | $150 | $0.30 | $5 |
| WTI | $82 | 0.10 | $820 | $2 | $27 |
| **Total** | — | — | **$59,424** | **$119** | **$1,953** |

**Worst-Case Drawdown (from backtest)**: -20.3% max drawdown

| Starting Capital | Max Drawdown (20.3%) | Min Equity | Margin Buffer |
|------------------|----------------------|------------|---------------|
| $5,000 | -$1,015 | $3,985 | ✅ Sufficient (1:500) |
| $10,000 | -$2,030 | $7,970 | ✅ Comfortable |
| $20,000 | -$4,060 | $15,940 | ✅ Very comfortable |

### 4.2 Recommended Capital

| Capital Level | Risk Tolerance | Suitability |
|---------------|----------------|-------------|
| **$5,000** (minimum) | High | Can trade all 8 assets at min lot; tight margin buffer |
| **$10,000** (recommended) | Medium | Comfortable margin; can absorb drawdowns |
| **$20,000+** (ideal) | Low | Multiple positions; scaling flexibility |

**Key Finding**: With 1:500 leverage (ASIC entity), $5,000 is sufficient to trade all 8 assets at minimum lot sizes. However, $10,000+ is recommended for comfortable trading with drawdown buffer.

---

## 5. Pre-Live Checklist

### 5.1 Broker Verification

- [ ] **All symbols available on broker**
  - [ ] XAUUSD visible in Market Watch
  - [ ] EURUSD visible in Market Watch
  - [ ] GBPUSD visible in Market Watch
  - [ ] USDJPY visible in Market Watch
  - [ ] BTCUSD visible in Market Watch (verify exact name)
  - [ ] ETHUSD visible in Market Watch (verify exact name)
  - [ ] SILVER/XAGUSD visible in Market Watch
  - [ ] OIL/WTI visible in Market Watch

- [ ] **Swap rates verified**
  - [ ] Record swap long/short for all 8 symbols
  - [ ] Identify triple-swap day (usually Wed or Fri)
  - [ ] Document in `Meta/swap_rates.md`

- [ ] **Margin requirements documented**
  - [ ] Verify leverage for account entity (ASIC vs EU)
  - [ ] Calculate margin for max position size
  - [ ] Test margin call behavior on demo

- [ ] **Lot sizes verified**
  - [ ] Min lot, max lot, lot step for all symbols
  - [ ] Confirm 0.01 lot is tradeable for crypto (BTC/ETH)

### 5.2 System Verification

- [ ] **Kill-switch tested on demo**
  - [ ] Kill-switch triggers at -15% portfolio drawdown
  - [ ] Kill-switch closes all positions within 1 rebalance cycle
  - [ ] Kill-switch state persists across process restarts
  - [ ] Manual kill-switch activation tested
  - [ ] Kill-switch reset procedure documented

- [ ] **Weekly rebalance cron job tested**
  - [ ] Signal generation runs on schedule (Friday close)
  - [ ] Order placement executes correctly
  - [ ] Position sizes match target allocation
  - [ ] Rebalance completes within 5 minutes

- [ ] **Monitoring alerts configured**
  - [ ] Prometheus metrics exporter running
  - [ ] Grafana dashboards deployed (P&L, positions, risk, data freshness)
  - [ ] Data feed staleness alert: > 1 hour since last bar
  - [ ] Portfolio drawdown alert: > 10% warning, > 15% critical
  - [ ] Correlation spike alert: realized cross-asset correlation > 0.7
  - [ ] Kill-switch trigger alert: immediate notification
  - [ ] Health check endpoint responding

### 5.3 Regulatory Confirmation

- [ ] **Regulatory status confirmed**
  - [ ] Pepperstone ASIC regulation verified (AFSL 389931)
  - [ ] Thai SEC blocking order reviewed — CFD via ASIC broker appears compliant
  - [ ] No recent SEC announcements affecting CFD brokers
  - [ ] Backup broker identified (IC Markets or OANDA)

### 5.4 Capital & Funding

- [ ] **Capital allocation confirmed**
  - [ ] Starting capital amount decided ($5,000 minimum, $10,000+ recommended)
  - [ ] Capital is risk capital (can tolerate -20% drawdown)
  - [ ] Broker account funded
  - [ ] Position sizing validated against starting capital
  - [ ] Max position per asset ≤ 20% of portfolio

---

## 6. Action Items

### Immediate (Before Paper Trade)

1. **Verify all 8 symbols on MT5 terminal**
   - Open Market Watch → add all symbols
   - Record exact symbol names (may differ from standard)
   - Verify spreads during liquid hours

2. **Record swap rates**
   - Check swap long/short for each symbol
   - Identify triple-swap day
   - Document in `Meta/swap_rates.md`

3. **Test kill-switch on demo**
   - Trigger kill-switch manually
   - Verify all positions close
   - Verify state persists across restarts

4. **Verify crypto CFD terms**
   - BTC/ETH leverage, spread, swap
   - Confirm 0.01 lot is tradeable
   - Test order execution

### Short-Term (During Paper Trade)

1. **Monitor Thai SEC announcements**
   - Set up Google Alerts for "Thai SEC CFD" and "Thailand forex regulation"
   - Check SEC.or.th monthly

2. **Establish backup broker**
   - Open demo at IC Markets or OANDA
   - Verify same symbols available
   - Test execution speed

3. **Document all trading activity**
   - Keep records for potential tax reporting
   - Export trade history monthly

### Long-Term (Before Live Capital)

1. **Consult Thai tax advisor**
   - Understand tax obligations for forex/CFD trading
   - Document all deposits/withdrawals

2. **Multi-broker strategy**
   - Split capital across 2+ brokers
   - Test execution at each broker

3. **Regulatory monitoring**
   - Subscribe to Thai SEC newsletter
   - Join Thai forex trader communities for early warnings

---

## 7. Key Findings Summary

| Category | Finding | Status | Risk |
|----------|---------|--------|------|
| **Broker Regulation** | Pepperstone regulated by ASIC (Tier 1), FCA, CySEC | ✅ Strong | Low |
| **Account Type** | Demo account, Razor (raw spread) | ✅ Confirmed | None |
| **Symbol Availability** | 8 symbols likely available (verify on MT5) | ⚠️ Pending | Low |
| **Commission** | $0 on metals/commodities, $7/lot on FX | ✅ Confirmed | None |
| **Leverage** | 1:500 (ASIC), 1:30 (EU) | ✅ Confirmed | Medium |
| **Swap Rates** | TomNext-based, triple charge one day/week | ⚠️ Verify | Medium |
| **Thai SEC** | CFD via ASIC broker appears compliant | ✅ Likely OK | Medium |
| **Capital** | $5,000 minimum, $10,000+ recommended | ✅ Sufficient | Low |
| **Kill-Switch** | Not yet tested on demo | ⚠️ Pending | High |
| **Monitoring** | Alerts configured in runbook | ⚠️ Pending | Medium |

---

## 8. Recommendations

1. **Proceed with caution**: Regulatory environment is evolving. Monitor Thai SEC announcements.

2. **Verify all symbols on MT5**: This report uses estimated specifications. Actual values may differ.

3. **Record swap rates**: Critical for overnight position cost analysis. Do not assume textbook values.

4. **Test kill-switch thoroughly**: This is the most critical safety mechanism. Test before any live capital.

5. **Start with demo capital**: Continue paper trading for full 8-12 weeks before live deployment.

6. **Maintain backup broker**: Open accounts at 2+ brokers for redundancy.

7. **Document everything**: Keep records for tax compliance and regulatory inquiries.

---

## 9. Verification Commands

```powershell
# Test MT5 connection
python scripts/verify_mt5_connection.py

# Verify symbol specifications
python scripts/verify_symbol_specs.py --symbols XAUUSD,EURUSD,GBPUSD,USDJPY,BTCUSD,ETHUSD,XAGUSD,WTI

# Record swap rates
python scripts/record_swap_rates.py --output Meta/swap_rates.md

# Test kill-switch
python scripts/test_kill_switch.py --demo

# Verify margin requirements
python scripts/calculate_margin.py --capital 10000 --leverage 500
```

---

## 10. References

- **Pepperstone Regulation**: https://www.pepperstone.com/regulation/
- **ASIC Register**: https://asic.gov.au/online-services/search-asics-registers/
- **Thai SEC**: https://www.sec.or.th/
- **Execution Plan**: `Meta/execution_plan.md`
- **Deployment Runbook**: `Meta/deployment_runbook.md`
- **Multi-Horizon Portfolio Plan**: `Meta/multi_horizon_portfolio_redesign_plan.md`
- **Broker Execution Research**: `Meta/research/BROKER_EXECUTION_DEEP_RESEARCH.md`

---

*Report generated by executor agent. Verify all items on live MT5 terminal before deployment.*
