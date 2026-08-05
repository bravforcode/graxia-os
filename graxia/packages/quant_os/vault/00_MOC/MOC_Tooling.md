# MOC — Tooling

> Open-source Python libs quant_os does NOT yet use. Source: [DEEP_RESEARCH_QUANT_STRATEGIES.md](../DEEP_RESEARCH_QUANT_STRATEGIES.md).
> Why here: a missing *tool* (e.g. statsmodels for cointegration) can be why a hypothesis couldn't be tested properly.

## All Tools (auto)
```dataview
TABLE category, value, effort, status
FROM "Tooling"
SORT value DESC, effort ASC
```

## Not-Yet-Adopted, Ranked by Value/Effort
```dataview
LIST priority_rank, value, effort
FROM "Tooling"
WHERE status = "not-used"
SORT priority_rank ASC
```

## Top-10 Priority (from source report)
1. **pandas-ta** (TA) — replace custom RSI/EMA/Bollinger · `pip install pandas-ta`
2. **ccxt** (Data) — unlock 100+ crypto exchanges
3. **statsmodels** (ML/Stats) — ADF, cointegration, GARCH
4. **PyPortfolioOpt** (Portfolio) — Markowitz + Black-Litterman + HRP
5. **Riskfolio-Lib** (Portfolio) — CVaR, CDaR, hierarchical
6. **vaderSentiment** (Sentiment) — instant news sentiment, no GPU
7. **alpaca-py** (Data) — US equities + options
8. **nevergrad** (Optimization) — derivative-free, complements optuna
9. **nautilus_trader** (Backtesting) — Rust-native engine (HIGH effort)
10. **mpl-finance** (Viz) — candlestick charts

## Quick Jump
- Data → [[MOC_Data]] · Hypotheses → [[MOC_Hypotheses]] · README → [[README]]
