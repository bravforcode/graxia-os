---
title: "FRED DFII5 — 5Y TIPS Real Yield"
type: data
status: missing
category: macro
gold_relevance: high
cost: free
update_freq: daily
source: "core/data/fred_client.py (add to SERIES_CATALOG)"
quant_os_integration: "Add 'DFII5': '5-Year TIPS Real Yield' to SERIES_CATALOG in core/data/fred_client.py"
tags: [type/data, domain/macro, status/missing, priority/p0]
---

# FRED DFII5 — 5Y TIPS Real Yield

## What it is
5-Year US inflation-protected real yield. Short-end of the real-rate curve. Pierdzioch (2016) ranks **real interest rates as gold's #2 predictor** (after USD). Currently quant_os has DFII10 (10Y) but NOT DFII5 / DFII30.

## Why it matters for quant_os
- Completes the real-yield *term structure* (5Y / 10Y / 30Y) → better regime + level signals.
- Directly informs a *level* real-yield hypothesis — the variant RYDC (EXP-1001) never tested (it only tested the *lag*).
- Free from FRED.

## Integration
```python
# Add to SERIES_CATALOG in core/data/fred_client.py:
"DFII5": "5-Year TIPS Real Yield",
"DFII30": "30-Year TIPS Real Yield",
```

## Status
- **Currently:** missing (not in fred_client SERIES_CATALOG — confirmed in [alternative_gold_data_sources.md](../research/alternative_gold_data_sources.md) §1)
- **Effort:** low (one-line catalog add)
- **Blocks:** any *level* real-yield hypothesis; strengthens macro-regime classifiers
- **Source note:** [alternative_gold_data_sources.md](../research/alternative_gold_data_sources.md)
