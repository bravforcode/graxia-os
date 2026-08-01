# Alternative Data Sources for Gold (XAU/USD) Prediction
> Researcher Agent — July 25, 2026
> Project: quant_os (Graxia OS)

---

## EXISTING DATA SOURCES (Baseline)

The project already has these gold-related data feeds:

| Source | Location | What's In It |
|--------|----------|--------------|
| **FRED** | `core/data/fred_client.py` (9 series), `data_pipeline/config.py` (9 series), `scripts/build_mega_features.py` (35 series) | DGS10, DGS2, DFII10 (real yield), T10YIE (breakeven), GVZCLS (gold vol), VIXCLS, DCOILWTICO (oil), DTWEXBGS (DXY broad), UNRATE, FEDFUNDS, CPIAUCSL, BAML credit spreads, TEDRATE, WALCL (Fed balance sheet), RRPONTSYD, etc. |
| **COT** | `core/data/cot_reports.py`, `data/cot/gold_cot_weekly.parquet` | Managed Money long/short, net positioning, open interest, 52w index, 3w trend, producer net short |
| **yfinance** | `data/market_data/yfinance/` (28 tickers) | GC=F (gold futures), GLD, IAU, SI=F, SLV, DX-Y.NYB (DXY), ^VIX, ^TNX, ^FVX, ^TYX, TLT, IEF, SHY, SP500, DJIA, NASDAQ, BTC, ETH, DBA, UUP |
| **MT5** | `data/XAUUSD_M15.csv` | M15 OHLCV for microstructure features (ATR, RSI, Bollinger, ADX, VWAP, candle patterns, volume ratios) |
| **MetaTrader 5** | `mt5_connector/` | Live spread, tick data, swap rates via Pepperstone |

---

## 1. MACRO INDICATORS — MISSING FROM PROJECT

### Already Covered
- DXY (via yfinance DX-Y.NYB + FRED DTWEXBGS)
- US10Y (DGS10), US2Y (DGS2), 10-2 spread (T10Y2Y)
- TIPS/real yield (DFII10)
- Breakeven inflation (T10YIE, T5YIE, T5YIFR)
- VIX (VIXCLS)
- Fed funds rate (FEDFUNDS)

### Missing — HIGH PRIORITY

| Series | FRED ID | Why It Matters | Cost |
|--------|---------|---------------|------|
| **5y5y Forward Inflation Swap** | `T5YIFR` | Market's long-term inflation view — already in build script but NOT in fred_client SERIES_CATALOG | Free |
| **Fed Funds Futures (Dec 2025/2026)** | `FF_CME` series | Rate-cut probability — could scrape CME FedWatch or use `FEDFUNDS` with FedWatchTool | Free |
| **US TIPS 5Y** | `DFII5` | Short-end real yield vs 10Y term structure | Free |
| **US TIPS 30Y** | `DFII30` | Long-end real yield | Free |
| **MOVE Index (Bond Vol)** | `MOVE` via yfinance | Bond market implied vol — complements VIX+GVZ | Free |
| **Trade Weighted USD: Advanced** | `DTWEXAFEGS` | Narrower DXY that includes gold-heavy trade partners | Free |

### How to Integrate
```python
# Add to SERIES_CATALOG in core/data/fred_client.py:
"DFII5": "5-Year TIPS Real Yield",
"DFII30": "30-Year TIPS Real Yield",
"T5YIFR": "5-Year, 5-Year Forward Inflation Expectation",
"DTWEXAFEGS": "Trade Weighted USD: Advanced Foreign Economies",
"MOVE": "ICE BofA MOVE Index (bond vol) — via yfinance ^MOVE",
```

---

## 2. POSITIONING DATA

### Already Covered
- COT gold futures (Managed Money long/short, producer short, OI, 52w percentile)
- COT loaded weekly via `cot_reports` library + `data/cot/gold_cot_weekly.parquet`

### Missing — HIGH PRIORITY

| Data | Source | Why It Matters | Cost | Update |
|------|--------|---------------|------|--------|
| **COT Silver** | Same CFTC pipeline | Gold-silver ratio positioning divergence signals | Free | Weekly (Fri) |
| **Gold ETF flows (GLD, IAU)** | `yfinance` already has GLD/IAU price — need **volume** and **shares outstanding** for flow calculation | Retail/institutional sentiment — major driver | Free | Daily |
| **CME futures total OI change** | CME Daily Bulletin or scrape | OI growth/decline = trend strength confirmation | Free | Daily |
| **Managed Money Net Long % (z-score)** | Compute from existing COT data | Normalize positioning vs history | Free (compute) | Weekly |

### How to Integrate
```python
# ETF flows from yfinance — already have GLD/IAU price
# Add: compute daily flow = (shares_outstanding_t - shares_out_t-1) * price_t
# yfinance Ticker.info has 'sharesOutstanding' (quarterly) — better: scrape from etf.com

# Silver COT: duplicate gold COT pipeline for SI futures
# COT silver code: 084691 (CME Silver Futures)
```

---

## 3. SENTIMENT DATA

### Already Covered
- Basic: not much. `news_events/macro_policy.py` has RESEARCH tier but no live sentiment pipeline.

### Missing — HIGH PRIORITY

| Source | How to Access | Why It Matters | Cost | Update |
|--------|--------------|---------------|------|--------|
| **NewsAPI** | `newsapi.org` — query="gold" OR "XAUUSD" | Headline sentiment → short-term direction | Free tier: 100 req/day | Real-time |
| **GDELT Project** | `gdeltproject.org` API — tone/volume for "gold" | Global gold-related media tone — academic-grade | Free | Every 15 min |
| **Fear & Greed Index** | `alternative.me/crypto/fear-and-greed-index/` via their API | Gold correlates with risk-off sentiment — this proxies it | Free | Daily |
| **AAII Sentiment Survey** | FRED: `BULLISH`, `BEARISH` series or scrape AAII | Equity sentiment → spillover to gold | Free | Weekly |
| **Twitter/X Sentiment** | X API v2 (paid) or `snscrape` (free, no API key) | $GOLD, $XAUUSD, @GoldTelegraph_ mentions | Free-$100/mo | Real-time |
| **Reddit r/gold** | Reddit API (free) — post volume, comment sentiment | Retail crowd sentiment | Free | Daily |

### How to Integrate
```python
# NewsAPI integration — add to data_pipeline/sources/
import requests
NEWSAPI_KEY = os.environ.get("NEWSAPI_KEY")
url = f"https://newsapi.org/v2/everything?q=gold+price&apiKey={NEWSAPI_KEY}"

# GDELT integration — tone query
url = "https://api.gdeltproject.org/api/v2/doc/doc?query=gold+price&mode=timelinevol&format=json"

# AAII via FRED (already have FRED client):
# Series: BULLISH (individual investor bullish %), BEARISH
# Add to SERIES_CATALOG or build_mega_features FRED_DAILY
```

---

## 4. PHYSICAL MARKET DATA

### Already Covered
- None directly.

### Missing — HIGH PRIORITY

| Data | Source | Why It Matters | Cost | Update |
|------|--------|---------------|------|--------|
| **LBMA Gold Price (AM/PM Fix)** | World Gold Council API or LBMA directly | Physical benchmark — the actual price underlying futures | Free | Twice daily |
| **Shanghai Gold Exchange (SGE)** | `sge.com.cn` — daily benchmark, Au99.99 premium | China physical demand premium vs LBMA — major signal | Free (scrape) | Daily |
| **India Gold Imports** | `commerce.gov.in` or Bloomberg/Reuters via API | India = #2 consumer. Import data = demand proxy | Free (govt reports) | Monthly |
| **Swiss Gold Exports** | Swiss Customs (ezv.admin.ch) | Switzerland refines ~70% of world gold — export data shows demand flows | Free | Monthly |
| **COMEX warehouse inventory** | CME Group daily reports | Inventory drawdowns = physical delivery demand | Free | Daily |
| **Gold ETF physical holdings (tons)** | World Gold Council API | GLD, IAU, SGE ETFs actual gold bars held | Free | Daily |
| **LBMA Clearing Statistics** | LBMA (lbma.org.uk) | Daily clearing volumes — market depth signal | Free | Monthly (with lag) |

### How to Integrate
```python
# World Gold Council has a public API
# https://www.gold.org/goldhub/data/gold-prices
# They publish daily LBMA prices and ETF holdings in CSV/JSON

# SGE premium = SGE Au99.99 price - LBMA AM fix (converted to CNY)
# This premium reflects Chinese physical demand
# Normal range: -5 to +30 USD/oz
#>30 = extreme Chinese demand (bullish signal)
# <0 = weak Chinese demand (bearish signal)

# COMEX warehouse data: scrape from CME Group daily gold stocks report
# https://www.cmegroup.com/delivery_reports/gold_stocks.xls
```

---

## 5. CENTRAL BANK DATA

### Already Covered
- None directly. (WALCL = Fed total assets is in FRED — broader than gold.)

### Missing — HIGH PRIORITY

| Data | Source | Why It Matters | Cost | Update |
|------|--------|---------------|------|--------|
| **Central Bank Gold Reserves (IMF IFS)** | IMF International Financial Statistics | CB buying/selling = structural floor/ceiling | Free | Quarterly |
| **World Gold Council CB Survey** | gold.org | Forward-looking buying intentions | Free | Annual + mid-year |
| **CB Gold Agreement (CBGA)** | ECB website | European CB selling caps — though dormant since 2019 | Free | Annual |
| **Individual CB Reports** | PBoC (China), RBI (India), CBR (Russia), TCMB (Turkey) | Top 5 gold buyers publish monthly reserve changes | Free | Monthly |

### How to Integrate
```python
# IMF IFS — available through World Bank API (free)
# https://api.worldbank.org/v2/country/all/indicator/FI.RES.TOTL.CD?format=json
# Gold reserves specifically: use IMF data via Quandl/Data Link (free tier)

# Alternative: WGC GoldHub provides CB buying data in charts — needs scrape
# https://www.gold.org/goldhub/data/gold-reserves

# Key series: PBoC gold reserves (monthly, published ~7th of month)
# Each PBoC gold purchase over 5 tonnes → typically precedes 3-month rally
```

---

## 6. MINING DATA

### Already Covered
- No mining data currently.

### Missing — MEDIUM PRIORITY

| Data | Source | Why It Matters | Cost | Update |
|------|--------|---------------|------|--------|
| **Gold Miner AISC (All-In Sustaining Cost)** | Company quarterly reports (Newmont, Barrick, Agnico Eagle) | Production cost floor for gold price — below AISC = miner capitulation | Free (scrape) | Quarterly |
| **GDX / GDXJ ETF** | yfinance (already have tickers available) | Gold miner equity index — leads gold price | Free | Daily |
| **Gold Forward Offered Rate (GOFO)** | LBMA (discontinued 2015) — replaced by LBMA Gold Forward Rates | Negative GOFO = backwardation = physical shortage | Free | Daily |
| **Miner Hedging Book** | World Gold Council / GFMS | Forward selling by miners = supply overhang | Paid ($) | Quarterly |

### How to Integrate
```python
# GDX/GDXJ already accessible via yfinance — just add to YF_TICKERS in build script:
# YF_TICKERS already has many stock/ETF tickers
# Add: "GDX": "gdx_miners", "GDXJ": "gdxj_junior_miners", "NEM": "newmont", "GOLD": "barrick"

# AISC: can approximate with quarterly data from World Gold Council
# Miners sell below AISC → capitulation → bottom signal
# AISC for top producers currently ~$1300-1450/oz
```

---

## 7. GEOPOLITICAL RISK DATA

### Already Covered
- VIX (VIXCLS in FRED), GVZ (GVZCLS in FRED)
- Gold-Silver ratio: can compute from existing SI and GC data

### Missing — HIGH PRIORITY

| Data | Source | Why It Matters | Cost | Update |
|------|--------|---------------|------|--------|
| **GPR Index (Caldara & Iacoviello)** | `https://matteoiacoviello.com/gpr.htm` | Academic geopolitical risk index — top-tier signal for gold | Free | Monthly |
| **GPR Daily** | Same source — daily version | Day-to-day geopolitical tension scoring | Free | Daily |
| **Economic Policy Uncertainty (EPU)** | `policyuncertainty.com` | Global EPU index — gold loves uncertainty | Free | Monthly |
| **Gold-Silver Ratio** | Compute from GC=F / SI=F | >90 = extreme risk-off, <50 = risk-on | Free (compute) | Daily |
| **Gold-Oil Ratio** | Compute from GC=F / CL=F | Gold vs energy — purchasing power metric | Free (compute) | Daily |
| **US Treasury CDS spread** | Bloomberg/Refinitiv (paid) or FRED `BAMLH0A0HYM2` (credit spread proxy) | Sovereign credit risk → gold bid | Free | Daily |

### How to Integrate
```python
# GPR Index — free CSV download
# https://www.matteoiacoviello.com/gpr_files/data_gpr_export.csv
# Contains: GPR (monthly), GPRD (daily), historical back to 1900
# Daily version: GPRD index — already merged into one CSV

# EPU Index — policyuncertainty.com
# US EPU: FRED series 'USEPUINDXD' (daily news-based)
# Global EPU: policyuncertainty.com/all_monthly.html

# Add to FRED:
"USEPUINDXD": "Economic Policy Uncertainty Index for United States",
"GEPUCURRENT": "Global Economic Policy Uncertainty Index",
```

---

## 8. ON-CHAIN DATA (TOKENIZED GOLD)

### Already Covered
- None

### Missing — MEDIUM PRIORITY

| Data | Source | Why It Matters | Cost | Update |
|------|--------|---------------|------|--------|
| **PAXG (PAX Gold)** | `etherscan.io` API — token supply, holder count, transfers | On-chain gold demand proxy — growing fast | Free | Real-time |
| **XAUT (Tether Gold)** | `etherscan.io` + Tron/Ton explorers | XAUT now ~$700M market cap — multi-chain | Free | Real-time |
| **PAXG/XAUT Premium** | DEX pricing vs LBMA spot | >1% premium = crypto-native gold demand surge | Free | Real-time |
| **DeFi Gold TVL** | DefiLlama API | Gold in DeFi protocols = institutional on-chain demand | Free | Daily |
| **Stablecoin market cap** | DefiLlama / CoinGecko API | Stablecoin supply growth = dry powder → gold bid | Free | Daily |

### How to Integrate
```python
# PAXG token supply (proxy for on-chain gold demand):
# Etherscan API: https://api.etherscan.io/api?module=stats&action=tokensupply&contractaddress=0x45804880De22913dAFE09f4980848ECE6EcbAf78
# Free tier: 5 calls/sec

# DefiLlama API (free, no key):
# https://api.llama.fi/protocols — filter for gold-related protocols
# https://stablecoins.llama.fi/stablecoins — all stablecoin market caps

# CoinGecko API (free, already used in project for BTC):
# PAXG: coingecko ID = "pax-gold"
# XAUT: coingecko ID = "tether-gold"
```

---

## 9. ORDER BOOK / MARKET MICROSTRUCTURE

### Already Covered
- MT5 M15 OHLCV with derived microstructure (ATR, ADX, volume, VWAP, candle patterns)
- Live MT5 spread data via `mt5_connector/`

### Missing — MEDIUM PRIORITY

| Data | Source | Why It Matters | Cost | Update |
|------|--------|---------------|------|--------|
| **Tick-level bid/ask** | MT5 `copy_ticks_range()` — already possible with existing MT5 connector | Order flow imbalance, absorption patterns | Free (MT5) | Real-time |
| **Depth of Market (DOM)** | MT5 `market_book_add()` | Order book depth at price levels = support/resistance | Free (MT5) | Real-time |
| **CME options data** | CME Datamine (paid) or free EOD reports | Put/call ratio, options OI by strike | Free-$500/mo | Daily |
| **Futures term structure** | Quandl/Data Link (CME gold futures) | Contango/backwardation shape — physical tightness | Free tier | Daily |

### How to Integrate
```python
# MT5 tick data pipeline — already have infrastructure
# Add: tick_imbalance = buy_ticks_at_ask / total_ticks
# Rolling 5-min tick imbalance predicts short-term direction

# CME options: scrape free EOD report
# https://www.cmegroup.com/tools-information/quikstrike.html
# Put/Call ratio > 0.9 = gold bearish (options market hedging)
# Put/Call ratio < 0.5 = gold bullish

# Gold futures term structure:
# (GC front month - GC 6-month forward) / front month
# Positive = contango (normal), Negative = backwardation (physical squeeze)
```

---

## 10. SEASONALITY DATA

### Already Covered
- None (build_mega_features has no calendar features)

### Missing — MEDIUM PRIORITY

| Data | Source | Why It Matters | Cost | Update |
|------|--------|---------------|------|--------|
| **Monthly seasonality** | Compute from historical XAUUSD | Sep = best month (+1.8% avg), Mar = worst (-0.8% avg) | Free (compute) | Static |
| **Day-of-week effects** | Compute from historical XAUUSD | Friday close positioning, Monday gap | Free (compute) | Static |
| **Indian calendar** | `pypi: hindu_calendar` or scrape from web | Diwali, Dhanteras, Akshaya Tritiya = peak gold demand | Free | Annual |
| **Chinese New Year** | Date easily computed | Gold demand spike pre-holiday in Jan/Feb | Free | Annual |
| **US Fed meeting dates** | FRED or `federalreserve.gov` | FOMC = highest-volatility gold events | Free | 8x/year |
| **US CPI/NFP release dates** | BLS schedule | Macro surprise days for gold | Free | Monthly |
| **COMEX options expiration** | CME calendar | Option expiry = gamma effects on gold | Free | Monthly |
| **Futures roll period** | CME calendar | Contract roll = spread volatility | Free | Quarterly |

### How to Integrate
```python
# Add to feature pipeline:
import calendar
df['month'] = df.index.month
df['day_of_week'] = df.index.dayofweek
df['is_friday'] = (df.index.dayofweek == 4).astype(int)
df['is_month_end'] = (df.index.day >= 25).astype(int)
df['is_diwali'] = is_indian_festival(df.index)  # custom function

# FOMC dates: manually maintain list or use FRED calendar
# FRED series: 'FEDFUNDS' changes map to meeting dates
# FOMC dot-plot dates: scrape from federalreserve.gov

# CPI release: typically 10-12th of each month
# Create 'is_cpi_day' boolean feature
```

---

## COMPLETE API & INTEGRATION REFERENCE

### FRED — Need to Add (ALL FREE)

| Series ID | Name | Gold Relevance |
|-----------|------|---------------|
| `DFII5` | 5-Year TIPS | Short-end real yield |
| `DFII30` | 30-Year TIPS | Long-end real yield |
| `T5YIFR` | 5Y5Y Forward Breakeven | Market's long-term inflation view |
| `DTWEXAFEGS` | USD: Advanced Economies | Better gold-specific DXY |
| `USEPUINDXD` | US Economic Policy Uncertainty | Uncertainty → gold bid |
| `BOGMBASE` | Monetary Base | Already in build script — ensure API integration |
| `M2SL` | M2 Money Supply | Inflation/Liquidity signal |
| `TEDRATE` | TED Spread | Already in build script |
| `BAA10Y` | Baa-10Y Spread | Already in build script |
| `WALCL` | Fed Total Assets | Already in build script |
| `RRPONTSYD` | ON RRP Facility | Liquidity drain signal |

### CFTC COT — Enhance Existing

- **Already have**: Gold futures (Managed Money) via `cot_reports` library
- **Add**: Silver futures COT (code `084691`) — identical pipeline
- **Add**: Gold options COT (supplemental report) — reveals option-driven positioning
- **Add**: COT index normalization across both gold + silver (combined z-score)

### World Gold Council

- **API/GoldHub**: `https://www.gold.org/goldhub/data/`
- **Free data**: Daily LBMA prices, monthly ETF flows, central bank reserves, mine production
- **Format**: CSV downloads available — can script automated scraping
- **Key endpoints**:
  - Gold prices (daily AM/PM fix)
  - Gold-backed ETF flows (monthly, per region)
  - Central bank gold reserves (quarterly)
  - Mine production (quarterly)
  - Gold demand trends report (quarterly PDF/Excel)

### Quandl / Nasdaq Data Link

- **URL**: `https://data.nasdaq.com/`
- **Free tier**: 50 calls/day
- **Key gold datasets** (all free):
  - `LBMA/GOLD` — daily LBMA gold price
  - `WGC/GOLD_DAILY_USD` — World Gold Council daily price
  - `CHRIS/CME_GC1` — CME gold futures continuous #1
  - `CHRIS/CME_GC2` through `GC12` — individual contract months
  - `FRED/*` — all FRED series available through Quandl as well
  - `ODA/PGOLD_USD` — IMF primary commodity gold price

### Free/Cheap Gold-Specific APIs

| API | URL | What You Get | Cost | Rate Limit |
|-----|-----|-------------|------|------------|
| **Metals-API** | `metals-api.com` | Real-time XAU, XAG, XPT, XPD prices | Free: 50 req/mo, paid: $39/mo | 50/month (free) |
| **GoldAPI.io** | `goldapi.io` | Real-time + historical gold prices | Free: 50 req/mo, paid: $29/mo | 50/month |
| **GoldFeed** | `github.com/nickpoorman/goldfeed` | Free gold price data | Free | Unlimited |
| **CoinGecko** | `coingecko.com/api` (already used in project!) | Gold token prices (PAXG, XAUT), also supports XAU | Free | 10-30/min |
| **Alpha Vantage** | `alphavantage.co` | Commodities including gold, FX | Free: 25/day | 5/min |
| **Twelve Data** | `twelvedata.com` | XAU/USD, gold futures, ETFs | Free: 800/day | 8/min |

---

## PRIORITY IMPLEMENTATION ROADMAP

### Phase 1 (Quick Wins — 1-2 days)
1. **Add missing FRED series** (DFII5, DFII30, USEPUINDXD, DTWEXAFEGS) to `fred_client.py`
2. **Add GDX, GDXJ to yfinance tickers** in `build_mega_features.py`
3. **Compute gold-silver ratio, gold-oil ratio** from existing data
4. **Add day-of-week, month, FOMC week, NFP day** calendar features
5. **Add MOVE index** (bond volatility) via yfinance

### Phase 2 (Medium Effort — 1 week)
6. **Integrate GPR Index** (free CSV from matteoiacoviello.com)
7. **ETF flow calculation** (GLD/IAU daily from yfinance volume × shares data)
8. **Silver COT** (duplicate gold COT pipeline)
9. **CoinGecko gold tokens** (PAXG, XAUT price + market cap)
10. **NewsAPI or GDELT** basic headline sentiment pipeline

### Phase 3 (Higher Effort — 2-3 weeks)
11. **World Gold Council data scraper** (ETF holdings, CB reserves, mine production)
12. **SGE premium calculation** (Shanghai Gold Exchange benchmark minus LBMA)
13. **CME options data** (put/call ratio from daily EOD reports)
14. **Indian/Chinese calendar features** (festival demand cycles)
15. **On-chain metrics** (PAXG/XAUT token supply via Etherscan API)

---

## NOTATION LEGEND

| Priority | Symbol | Definition |
|----------|--------|-----------|
| HIGH | 🔴 | Should add immediately — high signal-to-noise |
| MEDIUM | 🟡 | Adds value but less critical |
| LOW | 🟢 | Nice to have, diminishing returns |
| DONE | ✅ | Already in the project |

---

*Generated by Ruflow Researcher Agent for quant_os Phase 10+ extension. All APIs listed are either free, have free tiers, or can be scraped at zero cost.*
