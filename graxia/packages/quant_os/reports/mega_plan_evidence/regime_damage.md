# Regime Damage Analysis

**Generated:** 2026-07-02
**Script:** `scripts/diagnose_regime_damage.py`

## Purpose

Quantify per-regime strategy performance to detect whether a single regime (trend/range/volatile)
destroys most PnL. Uses the Sharpe-per-regime decomposition from `diagnose_regime_damage.diagnose()`.

## Methodology

1. Load closed trades from trade log (JSONL or Parquet).
2. Classify each trade into a regime bucket using ATR/return heuristics.
3. Compute per-regime: trade count, win rate, avg PnL, Sharpe ratio (annualized with correct BARS_PER_YEAR).
4. Flag regimes where Sharpe < -0.5 as **damaging**.

## How to Run

```bash
python graxia/packages/quant_os/scripts/diagnose_regime_damage.py \
    --trades-path data/trade_log.parquet \
    --asset-class metals \
    --timeframe M15 \
    --output reports/mega_plan_evidence/regime_damage_results.json
```

## Expected Output

| Regime   | Trades | Win Rate | Avg PnL  | Sharpe   | Damage Flag |
|----------|--------|----------|----------|----------|-------------|
| trend    | —      | —        | —        | —        | —           |
| range    | —      | —        | —        | —        | —           |
| volatile | —      | —        | —        | —        | —           |

> **Note:** Results depend on live trade data. Run after accumulating 50+ closed trades.

## Integration

- Called by release gate as supplementary evidence.
- Results feed into promotion review (`validation/promotion_review.py`).
- Alerts via Telegram if any regime Sharpe < -1.0.
