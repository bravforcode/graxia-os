# Deep Research: Gold XAUUSD H1 Trading Strategies
**Researcher Agent | 2026-07-25 | Evidence Quality: HIGH (codebase-audited + cross-referenced)**

---

## 1. GOLD PRICE DRIVERS & UNIQUE CHARACTERISTICS

### 1.1 Real Yields (DFII10) — **PRIMARY DRIVER**
- **Correlation:** −0.70 to −0.90 with gold (strongest negative correlation of any macro variable)
- **Mechanism:** Gold = zero-yield asset. When real yields fall, opportunity cost of holding gold drops → price rises
- **Current (2026):** DFII10 = 2.23% — still elevated, but declining from 2023 peaks
- **Actionable:** Monitor DFII10 direction daily. Rising real yields = gold headwind. Falling = tailwind.
- **Source:** FRED TIPS data, cross-validated 2026-06-26 (researcher_cross_asset_features.md)
- **Evidence:** HIGH

### 1.2 DXY (US Dollar Index)
- **Correlation:** −0.40 to −0.60 intraday, −0.60 to −0.80 monthly
- **Mechanism:** Gold priced in USD. Stronger dollar = gold more expensive for non-USD buyers = lower demand
- **Intraday divergence:** DXY and gold can decouple for hours during risk events (both can rise together during crises)
- **Actionable:** Track DXY direction as context filter. Gold trades best when DXY aligned (falling DXY + long gold)
- **Source:** DX-Y.NYB live correlation verified 2026-06-26
- **Evidence:** HIGH

### 1.3 VIX (Fear Index)
- **Correlation:** +0.30 to +0.50 episodic (only spikes during crises, zero during calm)
- **Gold as safe haven:** Activates when VIX > 25-30. Below that, VIX has no predictive power
- **Actionable:** Use VIX as regime gate: VIX > 25 = crisis mode (long bias only, wider stops). VIX < 20 = normal (both directions OK)
- **Source:** CBOE VIX data + WGC safe-haven research
- **Evidence:** MEDIUM

### 1.4 Central Bank Buying — **Structural Bull Driver**
- **Volume:** 1,000+ tonnes/year since 2022 (vs. ~450 tonnes/year historical average)
- **Key buyers:** China (PBOC), Poland, India, Turkey — all de-dollarizing reserves
- **Impact:** Creates permanent bid under gold, especially during dips
- **Market structure effect:** Pullbacks are shallower than pre-2022. $100 dips get bought aggressively
- **Actionable:** Long bias should structurally outperform short bias in current regime
- **Source:** World Gold Council (gold.org/goldhub), IMF reserve data
- **Evidence:** HIGH

### 1.5 Gold vs Other Assets — Key Differences
| Characteristic | Gold | FX Majors | Equities |
|---------------|------|-----------|----------|
| Daily ATR | $25-40 (2026) | 50-100 pips | 1-3% |
| Gap risk | Low (no market close) | Low | High (overnight) |
| Spread cost | 1.5-3.0 pips | 0.1-1.0 pips | $0.01/share |
| Correlation to rates | Very high (inverse) | Moderate | Moderate |
| Seasonality | Weak (Sep strongest) | Weak | Strong |
| Session behavior | London-dominant | London + NY | NY-dominant |
| Stop hunting | Common (liquidity sweeps) | Moderate | Rare |

---

## 2. MOST PROFITABLE GOLD TRADING PATTERNS (EVIDENCE-RANKED)

### 2.1 Liquidity Sweeps — **HIGHEST EVIDENCE (3/5 ICT)**
- **Pattern:** Price briefly breaks above equal highs / below equal lows, reverses
- **Why works on gold:** Stop hunting is institutional behavior on gold. Large players need liquidity.
- **quant_os implementation:** `liquidity_sweep.py` — detects equal highs/lows, confirms sweep reversal
- **Weight:** 1.3 (highest in ensemble)
- **Risk/Reward:** 2.5R (aggressive)
- **Key params:** 0.0005 threshold (0.05% = ~$1.60 at $3,200), scan 20 bars back
- **Session:** Works best during London/NY overlap (13:00-17:00 UTC) when liquidity is deepest
- **Source:** quant_os codebase + ICT/SMC literature, cross-referenced
- **Evidence:** MEDIUM-HIGH

### 2.2 Multi-Timeframe Alignment — **STRONGEST ACADEMIC EVIDENCE**
- **Pattern:** EMA20 > EMA50 on M15, H1, H4 simultaneously = trend confirmation
- **Tiers:** 3/3 aligned = score 85, 2/3 = score 75
- **quant_os implementation:** `multi_tf_align.py` — needs all 3 TFs or 2/3 minimum
- **Weight:** 1.2
- **Risk/Reward:** 1.5R (wider stops for M15 noise on gold)
- **Academic backup:** Dahlfors & Winther (2026), Yadav (2026) — MTF confirmation reduces false signals 60%+
- **Source:** 6 academic papers cited in researcher_xauusd.md
- **Evidence:** HIGH

### 2.3 London Breakout — **BEST SESSION-BASED PATTERN**
- **Pattern:** London open (07:00 UTC) first 4 M15 candles form range → breakout trade
- **Direction:** Above range = long, below = short
- **Target:** 2.5x range extension (historically good PF on gold)
- **quant_os implementation:** `london_breakout.py` — M15, approximate session detection
- **Gap:** Currently uses relative bar index, not actual UTC timestamp. Needs anchoring.
- **Volume filter:** 1.3x average volume confirmation
- **Weight:** 1.1
- **Source:** CME Group volume profile data + Myfxbook gold systems
- **Evidence:** MEDIUM-HIGH

### 2.4 Supply/Demand Zones — **CONSISTENT PERFORMER**
- **Pattern:** Price returns to zone of prior heavy buying/selling → reacts
- **quant_os implementation:** `supply_demand.py` — M15, 20-bar zone detection, 0.12 proximity threshold
- **Min SL:** 28.0 points (ATR-adaptive, ~$28 minimum for gold's daily range)
- **Zones tighten:** 0.12 proximity threshold (was 0.20 — reduced for fewer, higher-quality entries)
- **Volume conf:** 1.4x average for confirmation
- **Weight:** 1.1
- **Evidence:** MEDIUM

### 2.5 EMA Cross (9/21) — **SIMPLEST, MOST TESTED**
- **Pattern:** EMA 9 crosses above/below EMA 21 on M15
- **Confirmation:** EMA 50 trend filter + optional H4 trend
- **quant_os implementation:** `ema_cross.py` — M15, H4 optional, 1.5R SL, 3.0R TP
- **Weight:** 1.0
- **Evidence:** HIGH (decades of backtest data across all markets)
- **Issue:** Lagging indicator — signals come late in fast gold moves. Use with volume spike filter.

### 2.6 Opening Range Breakout — **M5 PRECISION**
- **Pattern:** First hour (12 × M5 candles) forms range → break above/below
- **Time filter:** Reduces score after 12:00 UTC (late entries worse)
- **quant_os implementation:** `opening_range.py` — M5, 2.0R target, 1.3x vol confirmation
- **Weight:** 1.1
- **Evidence:** MEDIUM

### 2.7 RSI Divergence (Extremes) — **MISCONFIGURED**
- **NOTE:** Currently detects RSI extremes (oversold/overbought), NOT true divergence
- **Bullish:** RSI < 35 (score 65), RSI < 25 (score 80)
- **Bearish:** RSI > 65 (score 65), RSI > 75 (score 80)
- **Gap:** Needs true divergence implementation (price lower low + RSI higher low)
- **Weight:** 1.0
- **Evidence:** MEDIUM (RSI overbought/oversold alone has weak standalone edge on gold)

### 2.8 News Fade — **MEAN REVERSION**
- **Pattern:** +0.4% spike in 10 M1 candles → fade reversal
- **Confirmation:** RSI must confirm (overbought for short fade, oversold for long fade)
- **Risk:** News spikes can extend much further than expected on gold during FOMC/CPI/NFP
- **Gap:** No economic calendar integration — needs to know WHY the spike happened
- **Weight:** 0.9 (lowest)
- **Evidence:** LOW-MEDIUM

### 2.9 ICT/SMC Strategies — **MIXED EVIDENCE**
| Strategy | Score | Verdict | Actionable? |
|----------|-------|---------|-------------|
| Liquidity Sweeps | 3/5 | Most tradeable ICT concept | YES — use as primary filter |
| Order Blocks | 2/5 | Real zones, unfalsifiable narrative | Marginally |
| Fair Value Gaps | 2/5 | Contextual only, needs size filter | As confirmation only |
| BOS/CHoCH | 2/5 | Standard TA with new jargon | As trend filter |
| Fibonacci | 60/100 | Works on gold, needs H4 filter | YES with trend filter |

---

## 3. TIME-OF-DAY / SESSION PATTERNS

### 3.1 Session-Based Spread Model (quant_os implementation)
| Session | UTC Hours | Spread (pips) | Characteristics |
|---------|-----------|---------------|-----------------|
| Asian | 00:00-07:00 | 3.0 | Low liquidity, wide spreads, avoid trading |
| London | 07:00-13:00 | 1.5 | Highest gold volume, best breakout patterns |
| London/NY Overlap | 13:00-17:00 | **1.2 (tightest)** | Maximum liquidity, best for entries |
| NY Only | 17:00-21:00 | 1.5 | US data releases, good for news-based |
| Closed | 21:00-00:00 | 5.0 | Do not trade |

### 3.2 Key Gold Fixing Times
- **LBMA Gold Price AM:** 10:30 UTC (London morning fix)
- **LBMA Gold Price PM:** 15:00 UTC (London afternoon fix, historically the benchmark)
- **COMEX settlement:** 17:30 UTC (NY close — can cause volatility)
- **Actionable:** Avoid entering 5 min before/after fix times. Wait for fix-related volatility to settle.

### 3.3 Best Trading Windows for Gold H1
1. **07:00-11:00 UTC** (London morning): Highest volume, best trend days
2. **13:00-17:00 UTC** (London/NY overlap): Tightest spreads, best entries
3. **12:30-14:30 UTC** (US data releases): FOMC, NFP, CPI — volatile 30-min windows
4. **Avoid 21:00-07:00 UTC**: Low volume, wide spreads, random walk dominate

### 3.4 Day of Week Effects
- **Monday:** Asian session often gaps from Friday close — wait for London open
- **Wednesday:** No consistent pattern
- **Friday:** Afternoon profit-taking can reverse weekly trends
- **Month-end:** Portfolio rebalancing flows can move gold $20-30

---

## 4. INDICATORS & FEATURES WITH PREDICTIVE POWER

### 4.1 Tier 1 — Proven Predictive (use as primary features)
| Feature | Type | Lag | Predicts | Correlation |
|---------|------|-----|----------|-------------|
| 10Y Real Yield (DFII10) | Daily macro | t-1 day | 1-5 day direction | −0.70 to −0.90 |
| DXY direction (DX-Y) | Hourly | t-1 hour | Same-day direction | −0.40 to −0.60 |
| Gold ETF flows (GLD/IAU) | Daily | t-1 day | 1-3 day direction | +0.60 |
| COT positioning | Weekly | t-1 week | 1-2 week extremes | +0.50 (contrarian at extremes) |
| ATR(14) on H1 | Intraday | Real-time | Stop distance, regime | — |

### 4.2 Tier 2 — Contextual (use as regime gates)
| Feature | Type | Gate Condition |
|---------|------|----------------|
| VIX | Daily | VIX > 25 → crisis mode (long only, wider stops) |
| Gold implied vol (GVZCLS) | Daily | GVZ > 20 → high volatility (reduce size 50%) |
| 10Y-2Y yield spread | Daily | Inversion → recession signal (gold bullish, but volatile) |
| WTI crude | Daily | $80+ → inflation concern (gold bullish) |

### 4.3 Tier 3 — Weak/Noisy (avoid relying on alone)
- WTI correlation: unstable, <0.20 r²
- USDJPY: redundant with DXY (DXY already captures yen)
- BTC: only correlated during risk-on/risk-off extremes
- Equity indices (SPX): inverse correlation only during crashes

### 4.4 Technical Features that Work on Gold H1
| Feature | Effectiveness | Notes |
|---------|--------------|-------|
| EMA 20/50 alignment | HIGH | Multi-TF confirmation |
| Equal highs/lows | HIGH | Liquidity sweep entry triggers |
| VWAP (session-anchored) | MEDIUM | Reset at London open (07:00 UTC) |
| Support/resistance zones | MEDIUM | Prior day/week levels respected on gold |
| Volume spikes | MEDIUM | 1.3-1.4x average confirms breakout validity |
| RSI extremes (14 period) | LOW | Gold stays overbought/oversold for extended periods |
| MACD | LOW | Too lagging for gold's fast moves |

---

## 5. COMMON FAILURE MODES FOR GOLD STRATEGIES

### 5.1 Overfitting — **CRITICAL (EVIDENCE: HIGH)**
- **Symptom:** ML model 100% train accuracy, 47-63% OOS
- **Root cause:** XGBoost with default params overfits small gold datasets
- **quant_os status:** Documented in `researcher_loss_drivers.md` — MRB + MLB strategies produce zero signals
- **Fix:** Regularization (max_depth=3, learning_rate=0.01, subsample=0.7, reg_lambda=5.0)
- **Validation:** Walk-forward optimization with at least 3 folds, 200+ trades minimum

### 5.2 Regime Shift Death — **CRITICAL (EVIDENCE: HIGH)**
- **Symptom:** -155.3% PnL degradation, 631% max drawdown during regime change
- **Root cause:** Strategies trained in low-vol regime, trade same way when vol spikes
- **quant_os status:** No regime-aware position sizing (identified as R3 in loss_drivers)
- **Fix:** Reduce position size 75% when VIX > 25 or ATR > 2x normal
- **Source:** Stress test results in `researcher_loss_drivers.md`

### 5.3 Cost Structure Eats Edge — **MAJOR**
- **Symptom:** WFO gross PnL ~0 but cost = -658, net = -658
- **Root cause:** Gold spread (1.5-3.0 pips on Pepperstone) vs typical move (1.18 pips signal)
- **quant_os status:** Dynamic spread model implemented but not integrated into signal filter
- **Fix:** Signal must overcome net cost. Filter: expected_move > spread + slippage * 3

### 5.4 Low Trade Frequency — **MAJOR**
- **Symptom:** 62 trades over entire backtest period with confidence ≥0.75
- **Stat issue:** 62 trades = not statistically significant (need 200+)
- **Root cause:** Confidence thresholds too high, MRB/MLB producing zero signals
- **Fix:** Lower thresholds, focus on trade frequency over per-trade accuracy

### 5.5 Long Bias Under-Utilization — **MODERATE**
- **Symptom:** In structural gold bull, neutral strategies miss bull trend
- **Root cause:** No structural long bias in allocation
- **Evidence:** Central bank buying 1000+ tonnes/year creates permanent floor
- **Fix:** Add structural long bias score (+10 to buy scores, −10 to sell scores)

### 5.6 Session Misalignment — **MODERATE**
- **Symptom:** London breakout strategy uses bar index, not UTC timestamp
- **Root cause:** `london_breakout.py` and `opening_range.py` don't know actual London open time
- **Fix:** Anchor to `datetime.utcnow().hour` with the session map from `dynamic_spread_model.py`

### 5.7 RSI Divergence Misnamed — **MODERATE**
- **Symptom:** Strategy name says "divergence" but code detects RSI extremes
- **Root cause:** No true divergence logic (price lower low + RSI higher low)
- **Fix:** Either implement true divergence or rename to `rsi_extremes`

### 5.8 Missing Cross-Asset Context — **MODERATE**
- **Symptom:** Strategies trade purely on price action, no fundamental context
- **Fix:** Add DXY filter: only long when DXY is falling (or flat), only short when DXY is rising

---

## 6. STRATEGY ENSEMBLE ANALYSIS

### 6.1 Current Architecture
```
13 Strategies → Individual Scores (0-100) → Weighted Aggregation → 4-Layer Risk → MT5
```
- **Weights:** liquidity_sweep(1.3) > order_block/multi_tf_align/fair_value_gap(1.2) > others(0.9-1.1)
- **Min score to trade:** 350 (sum of weighted strategy scores)
- **Min active strategies:** 3 must agree on direction
- **League system:** Auto-benches losing strategies (3 consecutive losses)
- **AI validation:** Claude validates signals before execution

### 6.2 Strategy Synergies & Anti-Synergies
| Pair | Synergy | Notes |
|------|---------|-------|
| London Breakout + Supply/Demand | +++ | Both zone-based, different time anchors |
| Liquidity Sweep + Multi-TF Align | ++ | Sweep confirms level, MTF confirms trend |
| EMA Cross + Fibonacci | ++ | Cross gives entry, Fib levels give targets |
| RSI + News Fade | + | Both mean-reversion on extremes |
| Order Block + Fair Value Gap | 0 | Both ICT, highly correlated (redundant) |
| Opening Range + London Breakout | − | Both session-based, can conflict |

### 6.3 Recommended Strategy Subset for H1 Focus
For H1-only trading (not M15/M5), keep these 8:
1. **liquidity_sweep** (H1) — best standalone ICT strategy
2. **multi_tf_align** (M15/H1/H4) — strongest academic evidence
3. **supply_demand** (H1 adapted) — consistent zone-based
4. **ema_cross** (H1) — simplest, well-tested
5. **fibonacci** (H1) — already H1-native
6. **order_block** (H1) — already H1-native
7. **bos_choch** (H1 adapted) — trend filter
8. **london_breakout** (H1 adapted) — session-anchored

Remove/adapt for H1: opening_range (M5), news_fade (M1), vwap_rejection (M15), rsi_divergence (M15)

---

## 7. ACTIONABLE RECOMMENDATIONS FOR quant_os

### 7.1 Immediate (This Week)
1. **Fix RSI strategy:** Rename to `rsi_extremes` or implement true divergence
2. **Anchor sessions:** Add UTC timestamp checks to london_breakout and opening_range
3. **Add DXY filter:** Minimum context gate for all gold signals
4. **Lower thresholds:** MRB/MLB need lower P(success) thresholds (0.55-0.60)

### 7.2 Short-Term (Next Sprint)
1. **Regime-aware sizing:** Reduce position 75% when VIX > 25 or ATR > 2x normal
2. **Cross-asset pipeline:** Implement DFII10/DXY/VIX data fetching + alignment
3. **Net-cost filter:** Only trade when expected move > spread + slippage * 3
4. **Session-anchored VWAP:** Reset VWAP at London open (07:00 UTC)

### 7.3 Medium-Term (Next Phase)
1. **True divergence logic:** Price/RSI divergence with lookback windows
2. **Economic calendar integration:** Skip news_fade during FOMC/NFP/CPI
3. **Deflated Sharpe Ratio:** Implement ONC clustering for effective N
4. **Full CSCV PBO:** Replace simplified heuristic with full probability of backtest overfitting

### 7.4 H1-Specific Configuration
```
Config for H1-only mode:
  primary_timeframe: "H1"
  timeframes: ["H1", "H4", "D1"]  (not M1/M5/M15)
  cycle_interval_seconds: 300  (5 min, not 30 sec)
  min_score_to_trade: 250  (lower since fewer strategies)
  sl_distance_points: 50  (wider for H1 bars)
  max_positions: 1
  max_risk_per_trade_pct: 0.5  (slightly higher, fewer trades)
```

---

## 8. SOURCES & REFERENCES

### Codebase Sources
- `gold_bot/strategies/*.py` — All 13 strategy implementations
- `gold_bot/core/engine.py` — Ensemble scoring engine + League system
- `gold_bot/core/config.py` — Risk parameters and strategy weights
- `gold_bot/core/risk_bridge.py` — 4-Layer risk engine bridge
- `backtest/dynamic_spread_model.py` — Session-aware spread/slippage
- `Meta/states/researcher_xauusd.md` — Previous strategy audit (2026-06-27)
- `Meta/states/researcher_edge_detection.md` — Edge detection research
- `Meta/states/researcher_loss_drivers.md` — Loss driver analysis (PRIORITY)
- `Meta/states/researcher_cross_asset_features.md` — Cross-asset feature research

### Academic Papers (cited in researcher_xauusd.md)
- Bilaisis (2026) — Gold algorithmic trading
- Bhatti (2026) — Gold price prediction
- Yadav (2026) — Multi-TF confirmation
- Mehmood (2026) — Machine learning for gold
- Dahlfors & Winther (2026) — Gold trading strategies
- Federal Reserve (2023) — FEDS 2023-077 on gold and real rates

### Web Sources
- World Gold Council (gold.org/goldhub) — Gold spot prices, central bank data
- CME Group — Gold futures volume and open interest
- Wikipedia: "Gold as an investment" — Comprehensive gold market overview
- TradingView (tradingview.com/symbols/XAUUSD) — Gold technical analysis
- FRED (fred.stlouisfed.org) — DFII10, DXY, VIX, WTI data series

### Market Data
- XAUUSD 1H bars in quant_os data warehouse (parquet, MT5 source)
- ATR research: `_scripts/atr_research.py` — M15 ATR stats in dollars and points
- Download scripts: `download_xauusd_multi_tf.py`, `download_mt5.py`

---

**Report saved by researcher agent. Delegate to architect for implementation planning.**
