# Integration Test Results — 2026-06-26

## 1. Upgrade Pipeline (Quick Mode)

| Metric | Value |
|--------|-------|
| Duration | 3m 31s |
| Phases run | 5/6 (market_data, ml_retrain, backtest, notebooklm, upgrade_report) |
| Data downloaded | 45 files, 90 cached, 1,715,639 bars |
| ML Drift | False (not retrained) |
| Backtested | 1 strategy (MTM) |
| NotebookLM | 3 questions asked, 0 saved |
| Pipeline manifest | ✅ Saved at `Meta/upgrade_pipeline_manifest.json` |

## 2. Vault Report

- **NOT FOUND** on disk — vault path `C:\Users\menum\Documents\ObsidianVault\Second Brain` does not exist
- Documents folder is redirected to OneDrive (`C:\Users\menum\OneDrive\Documents`)
- No Obsidian vault detected at OneDrive path either
- Pipeline log indicates report was saved; OBSIDIAN_VAULT_PATH env var is not set

## 3. Pipeline Manifest

```json
{
  "last_run": "2026-06-26 09:46 UTC",
  "phases": ["market_data", "ml_retrain", "backtest", "notebooklm", "upgrade_report"],
  "summary": {"market_data_downloaded": 45, "ml_retrained": false, "strategies_tested": 1, "insights_saved": 0}
}
```

## 4. Bridge Data Mode Test

| Metric | Value |
|--------|-------|
| Mode | `-Mode data` → mega_download.py --quick --direct |
| Duration | 0s (cached) |
| Downloaded | 45 OK, 0 Fail, 0 new bars |
| Data store | 135 CSVs, 162.8 MB |
| Result | ✅ PASS |

## 5. Scheduled Tasks

| TaskName | State | NextRun | LastRun |
|----------|-------|---------|---------|
| Graxia-Bridge-Daily | Ready | N/A | N/A |
| Graxia-Bridge-Research | Ready | N/A | N/A |
| Graxia-Bridge-Sync | Ready | N/A | N/A |
| Graxia-Bridge-Upgrade | Ready | N/A | N/A |
| Graxia-Bridge-Upgrade-Quick | Ready | N/A | N/A |
| GraxiaBot_RunNow | Ready | N/A | N/A |

**Status:** All 6 tasks Registered + Ready. None have run yet (NextRun/LastRun = N/A).

## 6. Script File Verification

| File | Status | Size |
|------|--------|------|
| `scripts/health_check.py` | ✅ | 3,425 B |
| `scripts/telegram_dashboard.py` | ✅ | 3,992 B |
| `scripts/data_quality_monitor.py` | ✅ | 3,796 B |
| `scripts/pipeline_alert.py` | ✅ | 1,186 B |
| `scripts/backtest_suite.py` | ✅ | 8,387 B |
| `scripts/mega_download.py` | ✅ | 7,816 B |
| `scripts/multi_symbol_bot.py` | ✅ | 7,304 B |
| `scripts/download_everything.py` | ✅ | 14,803 B |
| `download_mt5_symbols.py` | ✅ | 3,502 B |

All 9 files verified present.

## 7. Script Count

| Metric | Value |
|--------|-------|
| Total Python scripts | 79 |
| Non-Python files | 13 (.ps1, .sh, .bat, .toml) |
| Modified today (Jun 26) | 25 scripts |

## 8. NotebookLM Auth Status

| Check | Status |
|-------|--------|
| Storage exists | ✅ pass (file) |
| JSON valid | ✅ pass |
| Cookies present | ✅ 28 cookies |
| SID cookie | ✅ domains: .google.co.th, .google.com, .notebooklm.google.com |
| Token fetch | ⊘ skipped (use `--test` to verify) |

Overall: Authentication is **valid**.

## Summary

| Component | Result |
|-----------|--------|
| Upgrade pipeline (5 phases) | ✅ Completed 3m 31s |
| Data download (45 files) | ✅ Succeeded |
| ML drift check | ✅ No drift detected |
| Backtest (1 strategy) | ✅ MTM run |
| NotebookLM research | ⚠️ 3 asked, 0 saved (API responses empty) |
| Upgrade report | ⚠️ Reported saved but vault path missing |
| Pipeline manifest | ✅ Written |
| Bridge data mode | ✅ Cached 45 files, 135/162.8 MB total |
| Scheduled tasks (6) | ✅ All Registered + Ready |
| Script files (9) | ✅ All present |
| NotebookLM auth | ✅ Valid |
| Data coverage | 135 CSV files |
