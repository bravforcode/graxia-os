# G0 Secret Scan — 2026-06-23

## Scope
- Branch: `phase0-baseline-safety-freeze-20260623`
- HEAD: `1b84e97054daabd6918dba2acb54311ee02fd8b6`
- Scanner: `scripts/secret_scan.py`
- Coverage:
  - git-tracked files under `graxia/packages/quant_os`
  - `graxia/packages/quant_os/shadow_results`
  - `graxia/packages/quant_os/artifacts`

## Command

```powershell
python scripts/secret_scan.py
```

## Result
- Git tracked files: `0 findings`
- Shadow results: `0 findings`
- Artifacts: `0 findings`
- Final status: `CLEAN — no secrets found`

## Notes
- Scan output is redacted by design and does not print secret values.
- This report does not prove operator-side credential rotation; see `reports/G0_CREDENTIAL_ROTATION_STATUS.md`.
