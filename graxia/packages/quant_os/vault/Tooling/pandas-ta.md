---
title: "pandas-ta"
type: tool
status: not-used
category: technical-analysis
value: 9
effort: low
priority_rank: 1
pypi: "pandas-ta"
quant_os_use: "Replace custom RSI/EMA/Bollinger implementations (tests/test_ema_rsi.py, scripts) with 130+ battle-tested indicators as df.ta.* extension"
tags: [type/tool, status/not-used, priority/p0]
---

# pandas-ta

## What it does
130+ technical indicators as Pandas DataFrame extensions (`df.ta.rsi()`). Pure Python (no C compilation). Maintained, actively developed.

## Value vs Effort
- **Value:** 9/10 — eliminates error-prone custom TA (RSI, EMA, Bollinger, ADX, SMC/ICT detectors) in `tests/` + `scripts/`.
- **Effort:** LOW — `pip install pandas-ta`, then wrap.
- **Priority:** #1 of the Top-10.

## quant_os Integration
- **Replaces:** custom indicators in `tests/test_ema_rsi.py`, `scripts/*`
- **Enables:** consistent, tested TA across strategies; faster feature iteration
- **Source row:** [DEEP_RESEARCH_QUANT_STRATEGIES.md](../DEEP_RESEARCH_QUANT_STRATEGIES.md) §3.1

## Decision
- [ ] Evaluate (import + smoke test on XAUUSD_M15) → [ ] Adopt (pip install + wrapper) → [ ] Reject (with reason)
