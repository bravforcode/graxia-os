# Worst Folds Analysis — XAUUSD v3_fixed

Top 3 worst folds all have **accuracy < 0.5** (model WRONG in those periods). No single session dominates — spread across NY, London, Asia.

## Key pattern
- Worst: acc=0.44-0.46, avg win $6-25, avg loss -$12 to -$33
- Best:  acc=0.77-0.82, avg win $10-14, avg loss -$12 to -$14
- **Accuracy is the differentiator**, not avg win/loss ratio
- Magnitude filter can't fix wrong direction — it only filters small moves

## Dates (3 worst)
| Fold | Date | Session | Net | Accuracy |
|------|------|---------|-----|----------|
| 138 | 2026-02-04 | NY | -$954 | 0.46 |
| 147 | 2026-03-18 | NY | -$616 | 0.45 |
| 155 | 2026-04-27 | London | -$504 | 0.44 |

## Suggested next investigation
Join these fold periods with:
1. ForexFactory calendar (ingested in Week 3) — check for high-impact news
2. ATR percentile during these periods — were they high-vol regimes?
3. Session cross-product: NY+London overlap vs single session

If the model consistently fails during certain macro conditions → regime filter that avoids trading those conditions → reduces tail risk → increases t-stat. This is the only path that addresses root cause, not symptoms.
