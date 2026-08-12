# Research Summary: XAUUSD Trading Strategies

## Date: 2026-06-27

## Key Findings

### Strategy Rankings (by evidence + implementation)
1. **multi_tf_align** (75/100) — Best MTF approach, correct EMA alignment
2. **supply_demand** (72/100) — Good zone detection with ATR safeguards
3. **liquidity_sweep** (72/100) — Most tradeable ICT concept, aggressive R:R
4. **ema_cross** (70/100) — Strongest academic evidence, needs volume filter
5. **london_breakout** (68/100) — Targets best intraday pattern, needs session anchoring
6. **opening_range** (68/100) — Good M5 precision, needs actual timestamps
7. **bos_choch** (62/100) — Useful as filter, not standalone
8. **fibonacci** (60/100) — Needs H4 trend filter
9. **vwap_rejection** (58/100) — VWAP must be session-anchored
10. **order_block** (55/100) — Weak evidence, needs mitigation tracking
11. **fair_value_gap** (55/100) — Needs minimum gap size filter
12. **news_fade** (50/100) — Needs economic calendar API
13. **rsi_divergence** (45/100) — **MISNAMED** — detects RSI extremes, not true divergence

### Critical Gaps to Fix
- `rsi_divergence`: Implement true divergence or rename to `rsi_extremes`
- `london_breakout`/`opening_range`: Use actual London open timestamps (07:00 UTC)
- `vwap_rejection`: Use session-anchored VWAP (resets at London open)
- All strategies: Add DXY correlation filter for fundamental context
- `news_fade`: Integrate economic calendar for FOMC/NFP/CPI timing

### ICT/SMC Evidence Verdict
- Order Blocks: 2/5 (real zones, unfalsifiable narrative)
- Liquidity Sweeps: 3/5 (most tradeable, use as filter)
- Fair Value Gaps: 2/5 (contextual only)
- BOS/CHoCH: 2/5 (standard TA with jargon)

### Gold Market Context
- Price: $3,200-3,400 (June 2026, all-time highs)
- Structural bull: Central bank buying 1000+ tonnes/year
- Higher volatility: $25-40/day vs historical $15-25
- Long bias should outperform short bias

### Sources
- 6 academic papers from 2026 (Bilaisis, Bhatti, Yadav, Mehmood, Dahlfors, Winther)
- CME Group, World Gold Council, Wikipedia (Gold Fixing)
- All 13 strategy source files audited
