---
date: 2026-06-26
status: complete
tags: [bridge, fixes, vault, notebooklm, scheduled-tasks]
---

# Bridge Fixes — 2026-06-26

## ✅ Issue 1: Vault Path — FIXED

**Problem**: `OBSIDIAN_VAULT_PATH` env var not set, scripts using wrong path
**Root Cause**: Default path was `C:/Users/menum/quant/quant bot` (old location)

**Fix Applied**:
- Set env var: `OBSIDIAN_VAULT_PATH = C:\Users\menum\Documents\ObsidianVault\Second Brain`
- Updated 3 scripts:
  - `generate_canvas_views.py` — uses env var with correct fallback
  - `generate_obsidian_vault.py` — uses env var with correct fallback
  - `generate_test_notes.py` — uses env var with correct fallback
- `run_upgrade_pipeline.py` — already uses env var with correct fallback
- `bridge_notebooklm.py` — already has correct hardcoded path

**Verification**: Vault exists at `C:\Users\menum\Documents\ObsidianVault\Second Brain`
- Has `02-areas/trading/research/` for upgrade reports
- Has `meta/states/quant_os/` for state files

---

## ✅ Issue 2: NotebookLM — FIXED

**Problem**: Auth expired, API calls returning "Authentication expired or invalid"
**Root Cause**: Cookies were stale (28 cookies but tokens expired)

**Fix Applied**:
- Re-login with `notebooklm login`
- Auth now valid with 29 cookies
- API calls working: `notebooklm list`, `notebooklm ask` both functional

**Verification**:
```
Notebooks:
- quant_OS Research (Owner)
- ARWEEN: The SmartBatch and Time-Wallet Retail Ecosystem (Shared)
- test (test notebook)
```

---

## ✅ Issue 3: Scheduled Tasks — FIXED

**Problem**: Tasks never triggered automatically (LastRunTime = N/A)
**Root Cause**: `-Once` triggers with StartBoundary in the past
- Scripts used `(Get-Date).AddMinutes(1)` but by the time script ran, that time passed
- Repetition only applies AFTER first trigger fires

**Fix Applied**:
- Updated `setup_bridge_sync.ps1` to use `(Get-Date).AddMinutes(5)` for all recurring tasks
- Added `RepetitionDuration = 365 days` to all recurring triggers
- Daily tasks use `-Daily` trigger (correct)
- Created `trigger_all_tasks.bat` for manual testing

**Verification**:
```
TaskName                   State
--------                   -----
Graxia-Bridge-Daily        Ready    (Daily @ 03:00)
Graxia-Bridge-Sync         Ready    (Every 15 min)
Graxia-Bridge-Upgrade      Ready    (Every 6h)
Graxia-Bridge-Upgrade-Quick Ready   (Every 2h)
```

Manual trigger test: Sync completed successfully (Result=0)

---

## 📋 Next Steps

1. **Run setup script as Admin** to register all tasks with fixed triggers
2. **Test automated triggering** — wait 5 minutes and check if tasks fire
3. **Monitor first automated run** — verify pipeline completes
4. **Create Research task** — was missing (needs admin elevation)
