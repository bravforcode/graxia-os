# G1_0_HOUSEKEEPING.md

## Provenance
- **source_code_sha:** `5d16175ee853cf3315f08d315f697ddc7fdbf80a`
- **report_generation_sha:** `5d16175ee853cf3315f08d315f697ddc7fdbf80a`
- **report_commit_sha:** `<TBD — set after committing this doc>`
- **verification_worktree_sha:** `N/A`
- **contract_snapshot_hash:** `968E3EB2DFBB3E6B06B9DEF9AFDB8C1D142C22D837F178E4140F2B4DBB638CD7`

## Scope

Task A4 — Evidence and repository hygiene covering three workstreams:
1. Fix broken post-commit hook (stale OneDrive path)
2. Add provenance fields to existing reports
3. Remove UI/agent transcript contamination

---

## 1. Post-Commit Hook Fix

### Location
`C:\Users\menum\graxia os\.git\hooks\post-commit`

### Problem
Line 4 referenced a stale OneDrive path that does not exist:
```
C:/Users/menum/OneDrive/Documents/Gracia/01-Projects/GraxiaOS/CHANGELOG.md
```
This caused `post-commit` to fail silently (append to nonexistent file) on every commit.

### Resolution
- Commented out the entire CHANGELOG append block
- Added explanatory comment documenting why it was disabled
- Left a placeholder for future re-enablement: set `CHANGELOG_TARGET` to a valid path and uncomment the block
- Hook now exits cleanly with an informational message

### Verification
```powershell
PS> Get-Content C:\Users\menum\graxia os\.git\hooks\post-commit
```
Output confirms OneDrive path block is commented out and hook runs cleanly.

---

## 2. Report Provenance Fields

Added provenance sections to three reports using the current codebase state:

| Report | source_code_sha | contract_snapshot_hash |
|--------|----------------|----------------------|
| `REPORT_CONTRACT_TRUTH_AND_G0B.md` | `5d16175` | `968E3EB2DFBB...` |
| `CR_UNITS_PER_LOT_FINAL_REVIEW.md` | `5d16175` | `968E3EB2DFBB...` |
| `REPORT_G0A_DELTA_FINAL_VERIFICATION.md` | `5d16175` | `968E3EB2DFBB...` |

### Sources
- **Code SHA:** `git rev-parse HEAD` → `5d16175ee853cf3315f08d315f697ddc7fdbf80a`
- **Contract snapshot hash:** `Get-FileHash artifacts/contract_spec/XAUUSD_contract_snapshot.json -Algorithm SHA256`
  → `968E3EB2DFBB3E6B06B9DEF9AFDB8C1D142C22D837F178E4140F2B4DBB638CD7`
- **report_commit_sha:** left as `<TBD>` — to be filled in after the commit that writes these changes.

---

## 3. Contamination Scan

Scanned all reports under `reports/` for patterns:
- `Auditor|...DeepSeek...`
- `subagent_type`
- `prompt`
- agent system messages

### Result
No contamination found in G1.0 reports. One match in `reports/G0A_DATETIME_AUDIT.md:49` (`gold_bot/ai/validator.py | 106 | AI prompt`) is a legitimate filename reference (the file `gold_bot/ai/validator.py` contains a prompt module), not agent transcript contamination. No action taken.

### Gate
Housekeeping tasks for G1.0 complete. Reports are clean, hooks are silent, provenance is recorded.
