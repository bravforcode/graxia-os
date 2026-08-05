---
title: "{{DATA-NAME}}"
type: data
status: available            # available | missing | planned | rejected
category: macro              # macro | positioning | sentiment | physical | central-bank | mining | geopolitical | onchain | microstructure | seasonality
gold_relevance: high       # high | medium | low
cost: free                 # free | freetier | paid
update_freq: daily         # realtime | daily | weekly | monthly | quarterly
source: "{{where to pull from}}"
quant_os_integration: "{{exact code/step to wire in}}"
tags: [type/data, domain/macro, status/available]
---

# {{DATA-NAME}}

## What it is
{{description + why it matters for gold/XAUUSD}}

## Why it matters for quant_os
{{signal it would add; which rejected hypothesis it might rescue}}

## Integration
```python
{{exact snippet from alternative_gold_data_sources.md or your own}}
```

## Status
- **Currently:** {{available|missing|planned}}
- **Effort:** {{low|medium|high}}
- **Blocks:** {{which hypothesis/feature depends on it}}
- **Source note:** [alternative_gold_data_sources.md](../research/alternative_gold_data_sources.md)
