# Pre-Registration: Sentiment-vs-Price Predictive Power
# Trial #2002 — Formal Hypothesis Registration

## Hypothesis
**H1**: LLM-generated sentiment scores from financial news headlines predict next-day price movements for the same ticker.

**H0 (null)**: LLM sentiment scores have no predictive power beyond random chance.

## Pre-Registered Parameters (FROZEN)

### Trial Identity
- **trial_number**: 2002
- **name**: "LLM News Sentiment Price Prediction"
- **registered_at**: 2026-07-31
- **instrument**: Multi-ticker (US equities + crypto + commodities)
- **model**: qwen3.5:9b (local, quantized)

### Hypothesis Specification
- **Direction of causality**: Sentiment → Price (sentiment precedes price movement)
- **Horizon**: Next-day close-to-close return (T+1)
- **Hit definition**: Sentiment direction matches return direction (positive sentiment → positive return, negative → negative)
- **Minimum samples**: 100 sentiment-price pairs before evaluation

### Statistical Constraints
- **Significance bar**: p < 0.05 (two-tailed)
- **Multiple testing correction**: Bonferroni against cumulative trial count (2001 prior trials)
  - Adjusted α = 0.05 / 2002 = 0.000025
  - This is extremely conservative — reflects the reality that we've already run 2001 trials
- **Required evidence**: p-value < 0.000025 AND effect size (Cohen's d) > 0.2

### Data Collection
- **Source**: realtime_daemon.py → DuckDB llm_news_sentiment table
- **Price data**: Yahoo Finance API (existing quant_os infrastructure)
- **Match method**: Ticker + date alignment
- **Minimum headlines per ticker-day**: 1 (any headline mentioning the ticker)
- **Sentiment aggregation**: Simple majority vote (more positive headlines = positive day sentiment)

### What Counts as a "Hit"
- If sentiment is "positive" and next-day return > 0: HIT
- If sentiment is "negative" and next-day return < 0: HIT
- If sentiment is "neutral": EXCLUDED (no prediction made)
- If sentiment is "positive" and next-day return < 0: MISS
- If sentiment is "negative" and next-day return > 0: MISS

### What Does NOT Count
- Same-day correlation ( lookahead bias)
- Intraday movements (we only have daily data)
- Headlines without tickers (no price to match)
- Tickers not in our price database

## Constraints Inherited from quant_os

### From CONSTITUTION.md INV-012
- Edge claim must cite: (1) trial_number=2002, (2) p-value or dk_t, (3) artifact path
- Without citations: UNTESTED HYPOTHESIS, not finding

### From CHANGE_CONTROL.md
- Statistical validation: purged+embargo CV, early stopping, PBO/deflated Sharpe, multiple testing correction
- Registry captures hashes

### From BACKTEST_VALIDATION_INTEGRITY.md
- Walk-forward with purge/embargo gaps (12 bars default)
- Entry at next bar open (realistic execution)
- Transaction costs subtracted

## Artifact Paths (to be filled after backtest)
- **Walk-forward result**: `reports/sentiment_price_walkforward_2002.json`
- **Validation report**: `reports/sentiment_price_validation_2002.md`
- **Hypothesis registry**: `research/hypothesis_registry.json` (trial 2002 entry)

## Decision Criteria
- **PROCEED** if: p < 0.000025 AND Cohen's d > 0.2 AND direction consistency > 55%
- **REJECT** if: p >= 0.000025 OR Cohen's d <= 0.2
- **INCONCLUSIVE** if: insufficient samples (< 100 pairs) after 30 days of collection

## Notes
- This is a PRE-REGISTRATION, not a result
- No data has been collected yet
- No backtest has been run
- All parameters are frozen as of 2026-07-31
- The daemon is collecting data in the background
- Backtest will run after 100+ sentiment-price pairs are available
