---
title: "{{LIB-NAME}}"
type: tool
status: not-used             # not-used | evaluating | adopted | rejected
category: technical-analysis # backtesting|data|technical-analysis|ml-stats|portfolio|viz|prod|quant-finance|sentiment|optimization
value: 9                    # 0-10 value/effort ratio
effort: low                # low | medium | high
priority_rank: 1          # from DEEP_RESEARCH_QUANT_STRATEGIES top-10
pypi: "{{pypi-name}}"
quant_os_use: "{{what it replaces / enables}}"
tags: [type/tool, status/not-used, priority/p0]
---

# {{LIB-NAME}}

## What it does
{{one paragraph from DEEP_RESEARCH_QUANT_STRATEGIES.md}}

## Value vs Effort
- **Value:** {{/10}}  **Effort:** {{low|med|high}}  **Priority:** #{{rank}}
- **Why:** {{rationale}}

## quant_os Integration
- **Replaces:** {{custom TA / scipy.optimize / nothing}}
- **Enables:** {{multi-asset, econometrics, sentiment, ...}}
- **Source row:** [DEEP_RESEARCH_QUANT_STRATEGIES.md](../DEEP_RESEARCH_QUANT_STRATEGIES.md)

## Decision
- [ ] Evaluate  → [ ] Adopt (pip install + wrap)  → [ ] Reject (with reason)
