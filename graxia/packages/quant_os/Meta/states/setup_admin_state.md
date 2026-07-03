# Setup Admin State — 2026-06-26 18:17 ICT

## Files Created
| File | Status |
|------|--------|
| `scripts/setup_admin.ps1` | Created — auto-elevates, full Python path, removes old tasks, creates 6 new |
| `scripts/run_as_admin.bat` | Created — double-click to run setup_admin.ps1 as admin |
| `scripts/notebooklm_refresh.py` | Created — auto-refreshes NotebookLM auth every 12h |

## OBSIDIAN_VAULT_PATH
Set to: `C:\Users\menum\quant\quant bot` (User env var)

## Current Scheduled Tasks (pre-admin-fix)
| Task | State | Trigger | Python |
|------|-------|---------|--------|
| Graxia-Data-Download | Ready | Once/PT15M | `python.exe` (wrong) |
| Graxia-Bridge-Sync | Ready | Once/PT15M | `python.exe` (wrong) |
| Graxia-Bridge-Upgrade | Ready | Once/PT6H | `python.exe` (wrong) |
| Graxia-Bridge-Upgrade-Quick | Ready | Once/PT2H | `python.exe` (wrong) |
| Graxia-Bridge-Daily | Ready | Daily 03:00 | `python.exe` (wrong) |
| Graxia-Bridge-Research | Ready | Daily 04:00 | `python.exe` (wrong) |

**Issue**: Tasks use `python.exe` (not full path) — Task Scheduler returns 0x80070002 (file not found).
**Fix**: Run `scripts/setup_admin.ps1` as admin to recreate with full Python path.

## NotebookLM Auth
- Auth: VALID
- API: WORKING
- State saved to `Meta/states/notebooklm_auth_state.json`

## Next Steps
1. **Run `scripts/run_as_admin.bat` as admin** — this will:
   - Remove all 6 old tasks
   - Recreate with full Python path: `C:\Users\menum\AppData\Local\Programs\Python\Python312\python.exe`
   - Set OBSIDIAN_VAULT_PATH
2. **Verify**: `Get-ScheduledTask -TaskName "Graxia*" | Select TaskName, State`
3. **Test**: `Start-ScheduledTask -TaskName "Graxia-Bridge-Sync"` — should return Result: 0
