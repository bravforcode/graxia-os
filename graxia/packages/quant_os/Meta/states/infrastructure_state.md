# Infrastructure State — Graxia Bridge Scheduled Tasks

**Generated:** 2026-06-26T19:48:00+07:00

## Registered Scheduled Tasks (6)

| Task | State | Schedule | Command |
|------|-------|----------|---------|
| Graxia-Bridge-Daily | Ready | Daily @ 03:00 ICT | `run_bridge.ps1 -Mode full` |
| Graxia-Bridge-Research | Ready | Daily @ 04:00 ICT | `run_bridge.ps1 -Mode pull-only` |
| Graxia-Bridge-Sync | Ready | Every 30 min (started 14:10) | `run_bridge.ps1 -Mode sync` |
| Graxia-Bridge-Upgrade | Ready | Every 6h (started 16:21) | `run_bridge.ps1 -Mode upgrade` |
| Graxia-Bridge-Upgrade-Quick | Ready | Every 6h (started 19:21) | `run_bridge.ps1 -Mode upgrade-q` |
| GraxiaBot_RunNow | Ready | Once 07:52 (manual trigger) | `start_bot.bat` |

## MT5 Terminal

- **Status:** Running (2 instances)
- **Processes:**
  - `terminal64` — started 2026-06-26 14:15:30
  - `terminal64` — started 2026-06-25 16:16:38

## Errors

- None encountered. All 6 tasks registered and enabled.
- Script auto-elevated on first run (initial launch was non-admin).
