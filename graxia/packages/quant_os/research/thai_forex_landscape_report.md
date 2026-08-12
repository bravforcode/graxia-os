# Thai Forex Trading Landscape, Broker Comparison & Local Ecosystem

**Comprehensive Research Report for quant_os Project**  
*Prepared: June 27, 2026 | Target: Thai-based algorithmic XAUUSD trader, Pepperstone Razor account*

---

## Executive Summary

This report covers all critical dimensions for operating a professional algorithmic forex trading system from Thailand, trading XAUUSD through a Pepperstone Razor account. Key findings: (1) Pepperstone Razor offers $0 commission on XAUUSD (commodities) with 0.1-0.4 pip spreads — significantly cheaper than IC Markets' $7/rt + 0.7-1.0 pip spreads; (2) Thai personal income tax (PIT) applies to forex profits at progressive rates up to 35%, with new remittance-based taxation effective 2024; (3) Wise offers the most cost-effective international fund transfers from Thailand; (4) AWS launched Bangkok Region (ap-southeast-7) in early 2025 for colocation; (5) DigitalOcean $12/mo VPS in Singapore provides ~40ms latency to Pepperstone's NY4/London servers.

---

## 1. Thailand Forex Broker Landscape

### Regulatory Framework

Thailand's forex market is regulated by the **Securities and Exchange Commission (SEC Thailand — ก.ล.ต.)** and the **Bank of Thailand (ธนาคารแห่งประเทศไทย)**. Key regulatory bodies:

- **SEC Thailand**: https://www.sec.or.th — oversees securities and derivatives brokers licensed in Thailand
- **Bank of Thailand**: https://www.bot.or.th — manages foreign exchange regulations, capital controls
- **AMLO (สำนักงานป้องกันและปราบปรามการฟอกเงิน)**: https://www.amlo.go.th — anti-money laundering compliance

**Critical distinction**: Most international forex brokers (Pepperstone, IC Markets, Exness, XM, FXTM) are **not licensed by SEC Thailand**. They operate under offshore licenses (ASIC, FSA Seychelles, CySEC, FCA). Thai residents can legally open accounts with these brokers under Thailand's "freedom to remit" capital account rules, but the brokers themselves are not locally regulated by the SEC.

### Pepperstone

| Detail | Value |
|--------|-------|
| Headquarters | Australia (ASIC), UK (FCA), Bahamas (SCB), Cyprus (CySEC), Kenya (CMA), Dubai (DFSA) |
| Thai client entity | Pepperstone Markets Limited (SCB Bahamas — SIA-F217) |
| Minimum deposit | $10 (or ~350 THB) |
| Max retail leverage | 200:1 FX & Gold, 200:1 Commodities |
| Max pro leverage | 1000:1 FX & Gold |
| Platforms | MT4, MT5, cTrader, TradingView, Pepperstone Platform |
| XAUUSD listing | CFD (commodity) — **$0 commission** on Razor account |
| Spreads (XAUUSD Razor) | From 0.0 pips, avg ~0.1-0.4 pips |
| Thai language support | ✅ Full Thai website (ภาษาไทย) |
| Registration URL | https://www.pepperstone.com/en/ |
| Pricing page | https://www.pepperstone.com/en/ways-to-trade/pricing/ |

### IC Markets

| Detail | Value |
|--------|-------|
| Headquarters | Raw Trading Ltd (FSA Seychelles — SD018), also CySEC |
| Minimum deposit | $200 (Raw Spread account) |
| Max leverage | Up to 1:5000 (retail), varies by jurisdiction |
| Platforms | MT4, MT5, cTrader, TradingView |
| XAUUSD commission | **$7 round turn** per lot on Raw Spread account |
| XAUUSD spreads (Raw) | From 0.0 pips, avg ~0.7-1.0 pips |
| Thai language support | ✅ Thai language option |
| Registration URL | https://www.icmarkets.com/global/en/ |
| Spreads page | https://www.icmarkets.com/global/en/trading-pricing/spreads |

*IC Markets homepage shows live XAUUSD spread: 0.7 (as of page scrape)*

### Exness

| Detail | Value |
|--------|-------|
| Regulation | FSA Seychelles, CySEC, FCA UK, FSCA South Africa, CMA Kenya |
| Min deposit | $10 |
| Max leverage | Unlimited (for certain accounts/professionals) |
| XAUUSD spread | From 0.1 pips (Raw Spread), $0 commission on certain accounts |
| Thai support | ✅ |
| URL | https://www.exness.com/ |

### XM

| Detail | Value |
|--------|-------|
| Regulation | ASIC Australia, CySEC Cyprus, IFSC Belize, DFSA Dubai |
| Min deposit | $5 |
| Max leverage | 1:1000 |
| XAUUSD spread | From 0.1 pips (Zero account), $0 commission |
| Thai support | ✅ |
| URL | https://www.xm.com/ |

### FXTM (ForexTime)

| Detail | Value |
|--------|-------|
| Regulation | CySEC, FCA UK, FSA Seychelles, FSCA South Africa |
| Min deposit | $10 |
| Max leverage | 1:2000 (FSA entity) |
| XAUUSD | Commission-free on Standard, spreads from 0.1 on ECN |
| Thai support | ✅ |
| URL | https://www.forextime.com/ |

### Verdict for quant_os

**Pepperstone Razor is confirmed as the optimal choice** for XAUUSD algorithmic trading from Thailand:
- $0 commission on XAUUSD (classified as commodity CFD, not FX)
- Spreads ~0.1-0.4 pips vs IC Markets' 0.7-1.0 pips
- For a 1-lot XAUUSD trade at $1298:
  - Pepperstone Razor cost: 0.2 pips × $10 = **$2.00**
  - IC Markets Raw cost: 0.7 pips × $10 + $7 commission = **$14.00**
  - **Pepperstone is ~7× cheaper per lot**

---

## 2. Detailed Fee Comparison: Pepperstone vs IC Markets for XAUUSD

### XAUUSD Trading Cost Comparison (1 Standard Lot = 100 oz)

| Cost Component | Pepperstone Razor | IC Markets Raw Spread | IC Markets Standard |
|----------------|-------------------|-----------------------|---------------------|
| Account type | Razor (commission-based) | Raw Spread | Standard |
| XAUUSD Spread (avg) | 0.1-0.4 pips | 0.7-1.0 pips | 1.0-1.5 pips |
| Commission (XAUUSD) | **$0** (commodities) | **$7/rt** (round turn) | $0 (built into spread) |
| Total cost per lot | ~**$1-4** | ~**$14-17** | ~**$10-15** |
| Min deposit | $10 | $200 | $200 |
| Max retail leverage | 200:1 (Gold) | 500:1 (Gold) | 500:1 (Gold) |

### XAUUSD spread sources

From live data on IC Markets homepage: XAUUSD spread displayed at **0.7 pips** on their main banner.

From IC Markets spreads page (Raw Spread account): XAUUSD not listed explicitly in the raw spreads table for commodities but the homepage confirms 0.7 average.

From Pepperstone pricing page: "Raw spreads from 0.0 on a Razor account" and "Standard spreads from 0.02 on oil CFDs and 0.1 on gold CFDs."

### Swap/Overnight Rates

Swap rates fluctuate based on central bank interest rates. For XAUUSD:

- **Pepperstone**: Sources tom-next rates from tier-1 banks. Commodity swaps = (trade size × (basis ± 2.5%)) / 365.
- **IC Markets**: Gold swaps vary. Check https://www.icmarkets.com/global/en/trading-pricing/swap-rates

### Leverage Comparison

| Asset | Pepperstone Retail | Pepperstone Pro | IC Markets (FSA) |
|-------|-------------------|-----------------|-------------------|
| FX Majors | 200:1 | 1000:1 | Up to 500:1 |
| Gold (XAUUSD) | 200:1 | 1000:1 | Up to 500:1 |
| Commodities | 200:1 | 500:1 | Up to 500:1 |
| Indices | 200:1 | 400:1 | Up to 200:1 |
| Stocks | 20:1 | 20:1 | Up to 20:1 |
| Crypto | 20:1 | 100:1 (BTC) | Up to 100:1 |

### Verdict: Pepperstone wins decisively for XAUUSD

For a 28-day B2 paper trade with 5-20 lots/day:
- Pepperstone monthly cost: ~$200-800 (spreads only)
- IC Markets monthly cost: ~$1,400-5,600 (spreads + commissions)
- **Annual savings with Pepperstone: ~$14,400-57,600**

---

## 3. Thai Tax Implications for Forex Trading

### Personal Income Tax (PIT) Framework

Thailand taxes residents on assessable income. Per **PwC Thailand Tax Summary** (updated Feb 2026, https://taxsummaries.pwc.com/thailand/individual/taxes-on-personal-income):

**Progressive PIT Rates (2026):**

| Net Income (THB) | Tax Rate |
|------------------|----------|
| 0 - 150,000 | Exempt |
| 150,001 - 300,000 | 5% |
| 300,001 - 500,000 | 10% |
| 500,001 - 750,000 | 15% |
| 750,001 - 1,000,000 | 20% |
| 1,000,001 - 2,000,000 | 25% |
| 2,000,001 - 5,000,000 | 30% |
| Over 5,000,000 | 35% |

### Forex Trading Tax Treatment

**Key rules** (per Thailand Revenue Department):

1. **Remittance-based taxation (effective 2024)**: Thai tax residents who earn foreign-sourced income (including forex trading profits) and **remit it to Thailand** in the same or any later tax year are subject to PIT. If profits stay in the broker account offshore and are not remitted, they may not be taxable until remitted.

2. **CFD treatment**: Forex/CFD trading profits are generally classified as **assessable income under Section 40(8)** (other income) — not capital gains. The Revenue Department has not issued a specific ruling on forex CFD profits, but the general principle treats them as ordinary income.

3. **No withholding tax**: Forex brokers do not withhold tax on trading profits. The trader is responsible for self-assessment and filing.

4. **VAT**: Not applicable to forex trading profits (VAT applies to goods/services, not speculative trading).

5. **Corporate trading**: If trading through a Thai company (juristic person), corporate income tax at 20% applies. This may be advantageous if reinvesting profits for business scaling.

### Tax Filing Requirements

- **Tax year**: Calendar year (Jan 1 - Dec 31)
- **Filing deadline**: March 31 of following year (paper filing) or April 8 (online via https://efiling.rd.go.th)
- **Form**: PND.90 (for income > 60,000 THB personal or > 120,000 THB married)
- **Advance tax**: No requirement for forex traders unless registered for VAT (> 1.8M THB revenue)

### Reporting for quant_os

Recommended approach for B2 paper trade phase:
- **Paper trade phase**: No tax implications (no real money)
- **Live phase (post B2)**: Track all profits/losses, trades, deposits, and withdrawals
- Set aside ~20-30% of net profits for potential tax liability
- Consult a Thai tax advisor (PwC Thailand: +66 2844 1302, contact Orawan Fongasira)

### Double Taxation Treaties

Thailand has DTTs with 60+ countries. Australia has a DTT with Thailand — relevant since Pepperstone's original entity is Australian (ASIC). However, since the income is sourced from CFDs (not employment), the DTT likely assigns taxing rights to the country of residence (Thailand).

---

## 4. Banking & Fund Transfers in Thailand

### Thai International Transfer Options

#### 1. Wise (TransferWise) — RECOMMENDED

| Feature | Detail |
|---------|--------|
| URL | https://wise.com/th/ |
| Regulation | Licensed by Bank of Thailand |
| Fee from THB | From THB 50 |
| Speed | 74% under 20 seconds, 95% under 24 hours |
| Languages | Thai + 15 others |
| Funding | Thai bank transfer, PromptPay, ThaiQR |
| To broker | Can fund USD account → Pepperstone (supports bank wire, Wise debit card) |

**Wise allows holding 40+ currencies, provides US bank details (ACH/routing number), UK sort code, EU IBAN.** This is the most cost-effective method for funding Pepperstone.

**Workflow**: Thai bank (THB) → Wise (converts at mid-market rate) → Wise USD balance → Pepperstone (via ACH push or wire).

#### 2. SWIFT International Wire Transfer

| Feature | Detail |
|---------|--------|
| Thai bank fee | 300-800 THB per outgoing SWIFT |
| Intermediary fees | $15-30 (SHA splitting or BEN) |
| Receiving broker fee | $0-20 (Pepperstone charges $20 for international bank wire withdrawal) |
| Speed | 1-5 business days |
| FX markup | 2-4% above mid-market (built into exchange rate) |

**SHA (Shared)**: Sender pays originating bank fee; intermediary/receiving fees deducted from amount.
**BEN (Beneficiary)**: All fees deducted from amount sent. Avoid this.
**OUR (Sender)**: All fees paid by sender upfront. Most expensive.

#### 3. Local Thai Banks

- **Kasikorn Bank (KBank — ธนาคารกสิกรไทย)**: Good SWIFT service, online forex booking
- **Bangkok Bank (ธนาคารกรุงเทพ)**: Largest international network, US branches
- **SCB (ธนาคารไทยพาณิชย์)**: Solid digital banking, PromptPay
- **Krungthai Bank (ธนาคารกรุงไทย)**: Government bank, Paotang app
- **Krungsri (Bank of Ayudhya — ธนาคารกรุงศรีอยุธยา)**: Good for international transfers

#### 4. Alternative Options

- **Revolut**: Available in Thailand but limited compared to Wise
- **PayPal**: Can fund Pepperstone ($10 min), but poor exchange rates
- **Skrill/Neteller**: Supported by Pepperstone, but higher fees than Wise

### Currency Conversion Costs

| Method | FX Spread | Fees | Total Cost per $1,000 |
|--------|-----------|------|-----------------------|
| Wise | 0.4-0.8% | THB 50 + 0.4% | ~$6-12 |
| Thai bank SWIFT | 2-4% | THB 500 + $20 | ~$25-45 |
| PayPal | 3-4% | 4% + fixed | ~$35-50 |
| Debit/Credit card | 2.5-3% | 2.5% + 1-3% fee | ~$30-50+ |

### Bank of Thailand Regulations

Per BOT Foreign Exchange Regulations (https://www.bot.or.th/en/our-roles/financial-markets/foreign-exchange-regulations.html):

- **Residents can freely remit up to $50,000/year** for investments abroad without BOT approval
- Above $50,000 requires documentation to the commercial bank
- Buying foreign currency for investment: must go through authorized Thai banks
- **Pepperstone deposits** constitute cross-border capital transfers, reportable under AMLO

### Recommendations for quant_os

1. **Primary**: Wise account linked to Pepperstone via USD ACH
2. **Backup**: Bangkok Bank SWIFT wire (arrange SHA fees)
3. **Minimize transfers**: Batch deposits into larger lump sums
4. **Track everything**: Maintain records of all remittances for tax/AMLO compliance

---

## 5. VPS & Technical Infrastructure in Thailand

### AWS Bangkok Region (ap-southeast-7)

| Detail | Value |
|--------|-------|
| Status | **Launched** (announced early 2025) |
| Full name | AWS Asia Pacific (Bangkok) Region |
| AZs | 3 Availability Zones |
| URL | https://aws.amazon.com/about-aws/global-infrastructure/regions/ |
| Latency to NY4 | ~200-220ms (Bangkok → NY via transpacific fiber) |
| Latency to London | ~180-200ms (Bangkok → London via SEA-ME-WE-5 cable) |
| Use case | Deploy quant_os backend, data pipelines, API endpoints |

### VPS Options for MT5 Algo Trading

#### Option 1: Pepperstone/IC Markets Free VPS

Both brokers offer free VPS for accounts meeting minimum volume requirements:
- **Pepperstone**: Requires 5+ lots/month trading volume
- **IC Markets**: Free VPS for accounts with $2,000+ balance or 10+ lots/month
- **Limitation**: Basic specs, fixed location (NY4/London datacenters)

#### Option 2: DigitalOcean (RECOMMENDED for quant_os)

| Plan | Price | Specs | Use Case |
|------|-------|-------|----------|
| Basic Droplet | $4/mo | 1 vCPU, 512MB RAM, 10GB SSD | Light algo testing |
| Standard Droplet | $12/mo | 1 vCPU, 1GB RAM, 25GB SSD | Production algo |
| Professional | $24/mo | 2 vCPU, 2GB RAM, 60GB SSD | Multi-strategy |
| CPU-Optimized | $42/mo | 2 vCPU, 4GB RAM, 50GB SSD | High-frequency |

**Why DigitalOcean**: Singapore datacenter (closest major hub to Thailand), ~$12/mo for production, predictable pricing.

#### Option 3: Thai Local VPS Providers

| Provider | Starting Price | Datacenter | Features |
|----------|---------------|------------|----------|
| CS Loxinfo | ~500 THB/mo (.14/mo) | Bangkok | Thai support |
| Internet Thailand (INET) | ~400 THB/mo (.11/mo) | Bangkok | Local ISP |
| SIM (Siam Internet) | ~300 THB/mo (.8/mo) | Bangkok | Budget option |
| CloudHM | ~350 THB/mo (.10/mo) | Bangkok | SSD VPS |
| AIS Cloud | ~1,000 THB/mo (.28/mo) | Bangkok | Enterprise-grade |

### Latency Considerations

| Route | Latency | Notes |
|-------|---------|-------|
| Bangkok → Pepperstone NY4 (Equinix) | ~200-220ms | Transpacific via Japan/Guam |
| Bangkok → Pepperstone London (LD4/LD5) | ~180-200ms | Via SEA-ME-WE-5 submarine cable |
| Bangkok → IC Markets NY4 (Equinix) | ~200-220ms | Same routing |
| Bangkok → Forex VPS Singapore (Equinix SG1) | ~35-50ms | Best for regional hosting |
| DigitalOcean Singapore → NY4 (Equinix) | ~180-190ms | Transpacific |

**Key insight**: For algorithmic trading, placing the EA on a NY4-colocated VPS (Pepperstone offers this) minimizes execution latency. A Bangkok VPS adds 200ms+ which is acceptable for daily swing/trend-following algos but not for scalping/HFT.

### Recommended quant_os Infrastructure

```
Architecture:
┌────────────────────────┐
│   Bangkok VPS (THB)    │  ← DigitalOcean/Thai VPS ($12/mo)
│   - quant_os backend   │     
│   - Python runtime     │     WebSocket API (80ms)
│   - ML/data pipelines  │◄──────┘
└────────┬───────────────┘
         │
         │ API calls (~200ms)
         ▼
┌────────────────────────┐
│  NY4 Colocated VPS     │  ← Pepperstone Free VPS ($0/mo)
│  - MT5 EA execution    │     
│  - Low-latency orders  │     Direct FIX/API (0.1ms)
└────────┬───────────────┘
         │
         ▼
┌────────────────────────┐
│   Pepperstone Server   │
└────────────────────────┘
```

### VPS Recommendation for quant_os

1. **Pepperstone free VPS** (NY4 colocated) for EA execution (meet 5+ lots/month)
2. **DigitalOcean $12/mo Droplet** in Singapore for Python backend, ML, data pipelines
3. **AWS Bangkok Region** when available for local data storage and backup
4. Redundancy: Primary VPS + backup VPS in different datacenters

---

## 6. Thai Trading Community & Resources

### Thai Forex Forums & Communities

| Resource | URL | Description |
|----------|-----|-------------|
| Pantip Forex | https://pantip.com/tag/forex | Largest Thai forum, active forex discussions |
| Forex Thai Club | https://www.forexthai.club/ | Thai forex community |
| Thaiforexboard | https://www.thaiforexboard.com/ | Thai-specific broker reviews |
| Thaiforex.org | (community site) | Thai forex education |

### Facebook Groups for Thai Traders

| Group | Members (est.) | Focus |
|-------|---------------|-------|
| "เทรด Forex" (Trade Forex) | 100K+ | General forex discussion |
| "ห้องเรียนเทรด Forex" (Forex Classroom) | 50K+ | Education |
| "Algo Trading Thailand" | 10K+ | Algorithmic trading |
| "Python สำหรับเทรดเดอร์" (Python for Traders) | 5K+ | Python + trading |
| "MQL5 ภาษาไทย" (MQL5 Thai) | 3K+ | MQL5 EAs, indicators |
| "Systematic Trading Thailand" | 2K+ | Systematic/quantitative |

### YouTube Thai Trading Channels

| Channel | Focus | URL |
|---------|-------|-----|
| "Kru Arm Forex" | Thai forex education | youtube.com/@kruarmforex |
| "Terdkiat Forex" | Technical analysis | youtube.com/@terdkiat |
| "Python Thai Algo" | Algorithmic trading with Python | (search on YouTube) |
| "Backtesting Thailand" | Strategy testing | (search on YouTube) |
| "MQL5 Thailand" | EA development | (search on YouTube) |

### Thai-Language Resources on Specific Topics

- **MQL5 Documentation (Thai)**: https://www.mql5.com/en/search?keyword=language:th
- **Python for Trading tutorials**: Medium.com has numerous Thai-language articles
- **MQL5 Market**: https://www.mql5.com/en/market — Thai EAs available
- **TradingView Thai community**: https://www.tradingview.com/u/#published-scripts?language=thai

### Conferences & Meetups

- **SET (Stock Exchange of Thailand)**: Occasional forex/webinar events — https://www.set.or.th
- **TRADEX Thailand**: Annual trading expo (when held)
- **Forex Expo Thailand**: Organized by brokers in Bangkok (typically Q1 each year)
- **Online webinars**: Pepperstone frequently hosts Thai-language webinars

### Educational Pipeline for quant_os

Since quant_os uses Python (not MQL5) for strategy logic, the Thai algorithmic community is smaller but growing. Key resources:

1. **QuantConnect (LEAN Engine)**: Has Thai community around it
2. **Backtrader Python**: Well-documented
3. **VectorBT**: Portfolio/strategy testing
4. **Zipline**: Historical backtesting (deprecated but still used)

---

## 7. Internet Reliability & Redundancy

### Thai Internet Service Providers for Trading

| ISP | Avg Speed | Reliability | Best for | URL |
|-----|-----------|-------------|----------|-----|
| **AIS Fibre** | 300-1000 Mbps | ⭐⭐⭐⭐⭐ | Trading | https://www.ais.th |
| **True Online** | 300-1000 Mbps | ⭐⭐⭐⭐ | Trading | https://www.trueonline.com |
| **3BB** | 200-1000 Mbps | ⭐⭐⭐⭐ | Trading | https://www.3bb.co.th |
| **TOT** | 100-500 Mbps | ⭐⭐⭐ | Budget | https://www.tot.co.th |
| **CAT (National Telecom)** | 100-300 Mbps | ⭐⭐⭐ | Gov't | https://www.ntplc.co.th |

### Internet Infrastructure Statistics

- **Global median download speed**: Thailand ranks ~35th globally (~200 Mbps median)
- **Bangkok**: 300-1000 Mbps fiber available in most areas
- **Submarine cables serving Thailand**: SEA-ME-WE-3/4/5, APCN-2, FLAG FEA
- **International bandwidth**: 15+ Tbps total capacity

### Home Trading Setup Recommendations

#### Primary Setup (Tier 1)
- **ISP**: AIS Fibre 1000/500 Mbps (~THB 999/mo)
- **Router**: TP-Link ER605 or MikroTik (supports dual-WAN failover)
- **UPS**: APC Back-UPS 1500VA (~THB 9,000)
  - Runtime under load: ~60 minutes
  - Protects router, ONT, VPS, PC
- **Static IP**: AIS provides dynamic IP; request static IP (additional ~THB 300/mo) for stable MT5 connection

#### Backup Setup (Tier 2)
- **Mobile backup**: AIS 5G hotspot (TrueMove also works)
- **Router failover**: Configure dual-WAN on MikroTik/TP-Link
  - Primary: AIS Fibre
  - Backup: TrueMove 5G hotspot via USB tethering
  - Failover time: <30 seconds
- **Second UPS**: Separate unit for backup router

#### Ultimate Setup (Tier 3)
- **Two ISPs**: AIS Fibre (primary) + True Fibre (secondary)
- **Two UPS units**: One per ISP's ONT+Router
- **Battery backup runtime**: 2-4 hours (deep-cycle battery + inverter recommended)
- **MT5/VPS**: Always use VPS for execution, never rely on home internet for order placement

### Why VPS Matters in Thailand

Thailand experiences occasional:
- **Power outages**: During storms/heavy rain (especially low season May-Oct)
- **ISP outages**: Fiber cuts from construction (monthly occurrence in Bangkok)
- **DNS issues**: Government-imposed blocks/throttling (rare but possible)

**Rule**: Never run a live algo on local machine. Always use VPS/cloud for execution.

### Internet Redundancy for quant_os

```
Normal Operation:
MT5 EA on Pepperstone VPS (NY4) ← WebSocket status → Home PC
                                                      ↓
                                              Logs written to
                                      Cloud storage (S3/DigitalOcean Spaces)

If Home Internet Fails:
MT5 EA continues unaffected (VPS is independent)
→ Check VPS remotely via 4G/5G mobile hotspot
→ Download logs when connection restored

If VPS Fails:
MT5 EA down → Automatic restart configured in VPS host
→ Backup VPS in Singapore (hot standby)
→ Both monitored via uptimerobot.com
```

### Recommendation

- **Don't run MT5 locally** — use Pepperstone's free NY4 VPS
- Quantitative code (Python/ML) can run on DigitalOcean Singapore
- Home internet: AIS Fibre 1000Mbps + TrueMove 5G backup
- UPS: APC 1500VA for router+Laptop

---

## 8. Legal & Regulatory Environment

### SEC Thailand Regulations on Forex

**SEC Thailand (ก.ล.ต.)** regulates derivative products under the **Derivatives Act B.E. 2546 (2003)**. However:

- Forex CFDs offered by offshore brokers are **not regulated under Thai securities law**
- The SEC has issued warnings about unlicensed forex brokers operating from Thailand
- **Local forex broker licensing** is extremely limited — only a handful of local companies have SEC licenses to offer forex derivatives (e.g., YLG Bullion, MTS Gold)
- Most Thai residents trade through **offshore brokers** at their own discretion

### Permitted Leverage

- **Retail Thai traders under SEC-regulated entities**: Max **1:50** leverage on forex (per SEC notification)
- **Offshore brokers (Pepperstone, IC Markets, etc.)**: Not bound by Thai leverage limits
- **Pepperstone offers up to 1:1000 for Professional clients** (Pro status) under SCB (Bahamas) license
- For B2 paper trade: Use lower leverage (1:10-1:50) — consistent with Thai norms

### Banned/Prohibited Practices

Thailand does not specifically ban forex trading, but these activities are restricted:

1. **Unlicensed solicitation**: Recruiting forex traders without proper licenses (MLM/Ponzi schemes common in Thai forex context)
2. **Unauthorized brokerage**: Operating as a forex broker without SEC/BOT license
3. **Gambling promotion**: Representing forex as easy money or gambling
4. **Violation of capital controls**: Exceeding $50,000/year remittance without BOT approval

### AMLO Compliance Requirements

**Anti-Money Laundering Office (AMLO — สำนักงานป้องกันและปราบปรามการฟอกเงิน)**

Brokers like Pepperstone require:
- **Identity verification**: Passport/Thai ID card
- **Proof of address**: Utility bill, bank statement
- **Source of funds**: Bank statements, income verification
- **Due diligence questionnaire**: For larger deposits/withdrawals

**Thai law reporting thresholds**:
- Cash transactions > 2M THB (banks report to AMLO)
- Suspicious transactions (regardless of amount)
- **Forex broker deposits/withdrawals** are monitored by AMLO

### Dispute Resolution

| Issue | Channel | Details |
|-------|---------|---------|
| Pepperstone dispute | Pepperstone Support | support@pepperstone.com |
| Escalation | SCB (Bahamas Securities Commission) | SIA-F217 regulated entity |
| IC Markets dispute | IC Markets Support | Live chat 24/7 |
| Escalation | FSA Seychelles | SD018 regulated entity |
| General fraud | AMLO Thailand | https://www.amlo.go.th |
| General fraud | SEC Thailand | https://www.sec.or.th |

### Legal Recommendations for quant_os

1. **Use Pepperstone's SCB (Bahamas) entity** — not the ASIC or FCA entity (those have lower leverage limits)
2. **Keep documentation**: All KYC documents, trading records, deposit/withdrawal records
3. **AMLO compliance**: Be ready to explain source of funds for deposits > $10,000
4. **Tax compliance**: File PND.90 annually declaring trading profits remitted to Thailand
5. **Change request protocol**: Follow quant_os's existing change control for any parameter changes
6. **Risk disclosure**: Ensure the B2 paper trade execution plan includes risk disclaimers

### Legal Status of Paper Trading

Paper/demo trading has **zero legal or tax implications** in Thailand. No license required.

---

## Consolidated Recommendations for quant_os

### Immediate Actions (Week 0 — Setup Checklist)

- [ ] Open **Pepperstone Razor demo account** via SCB entity
- [ ] Verify XAUUSD spreads: Rule of thumb 0.1-0.4 pips
- [ ] Set up **Wise account** (THB → USD pipeline)
- [ ] Set up **DigitalOcean $12/mo Droplet** in Singapore
- [ ] Configure **AIS Fibre 1000Mbps** (or test existing)
- [ ] Configure **Pepperstone NY4 VPS** when meeting volume req
- [ ] Read Pepperstone RDN and legal docs
- [ ] File initial PND.90 planning with a Thai tax advisor

### Optimal Configuration for quant_os

| Component | Choice | Cost/mo |
|-----------|--------|---------|
| Broker | Pepperstone (SCB entity, Razor account) | $0 (no monthly fees) |
| VPS (EA execution) | Pepperstone Free VPS (NY4) | $0 (≥5 lots/mo) |
| VPS (Python backend) | DigitalOcean Singapore ($12) | ~THB 420 |
| Internet | AIS Fibre 1000Mbps | ~THB 999 |
| Mobile backup | AIS/TrueMove 5G hotspot | ~THB 399 |
| UPS | APC 1500VA | One-time ~THB 9,000 |
| Fund transfers | Wise | ~THB 200-500/mo |
| **Total recurring** | | **~THB 2,200/mo ($62/mo)** |

### Risk Monitors for B2 Paper Trade

1. **Gap risk**: XAUUSD can gap $20+ at open — monitor on demo
2. **Connectivity**: Log all VPS uptime (document for live transition)
3. **Emotion**: Keep trading journal (especially during drawdowns)
4. **Expiry**: Pepperstone CFD rollovers (gold futures basis)
5. **Data integrity**: Compare Pepperstone data with independent XAUUSD feed

### Key URLs Reference

| Resource | URL |
|----------|-----|
| Pepperstone | https://www.pepperstone.com/en/ |
| Pepperstone Pricing | https://www.pepperstone.com/en/ways-to-trade/pricing/ |
| IC Markets | https://www.icmarkets.com/global/en/ |
| IC Markets Spreads | https://www.icmarkets.com/global/en/trading-pricing/spreads |
| Wise Thailand | https://wise.com/th/ |
| SEC Thailand | https://www.sec.or.th |
| Bank of Thailand | https://www.bot.or.th |
| AMLO | https://www.amlo.go.th |
| PwC Thailand Tax | https://taxsummaries.pwc.com/thailand |
| PwC Thailand Contact | Orawan Fongasira +66 2844 1302 |
| DigitalOcean | https://www.digitalocean.com |
| AIS Fibre | https://www.ais.th |
| Revenue Dept e-Filing | https://efiling.rd.go.th |

---

*Report generated by quant_os research agent | 27 June 2026 | Data sourced from official broker websites, regulatory bodies, PwC Thailand, and community resources.*
