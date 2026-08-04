# Myfxbook Collector

Nightly-batch collector for public Myfxbook account pages. **Hypothesis feed only** —
nothing here trades, and nothing here bypasses `governance/validation_stack.py` gates.

## Run

```powershell
python scripts/collect_myfxbook.py --dry-run     # live fetch, no writes
python scripts/collect_myfxbook.py --limit 2     # pilot subset, writes DB + report
python scripts/collect_myfxbook.py               # full pilot (8 accounts)
```

Outputs: `data/myfxbook.db` (SQLite) + `reports/myfxbook/YYYY-MM-DD.md`.

## Rules

- Min 5 s between requests (`config.REQUEST_DELAY_SECONDS`). Public pages only, no auth.
- Never commit `data/myfxbook.db`.
- Report artifacts are auditable evidence — keep them, don't overwrite locked outputs.
- Follow-up phases (separate plans): trade-history reverse-engineering into
  strategy hypotheses, then wiring PASS accounts into the existing edge-search /
  validation / trial-ledger pipeline, then external account drift monitoring.
