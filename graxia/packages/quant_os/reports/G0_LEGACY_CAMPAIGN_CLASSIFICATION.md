# G0 Legacy Campaign Classification

## Classification
- Legacy campaign label: `LEGACY_EXPLORATORY_SHADOW_TELEMETRY`
- Qualification status: `NOT_QUALIFICATION_EVIDENCE`
- Promotion status: `BLOCKED`

## Scope
- Canonical reference: implementation pack `00_README.md`
- Current code references reviewed:
  - `shadow/pepperstone_campaign.py`
  - `demo_campaign/campaign.py`
  - `demo_campaign/drills.py`

## Rules
- Legacy campaign output may be used for telemetry, runtime observation, and failure analysis only.
- Legacy campaign output may not be relabeled as shadow qualification evidence, demo-canary evidence, or live-readiness proof.
- Any P&L or hit-rate derived from this lane must be labeled `SIMULATED / NOT REALIZED / NOT EXECUTION EVIDENCE`.

## Current Verdict
- The repo contains legacy-campaign code paths, but no current Phase 0 artifact previously labeled them explicitly.
- This file is the explicit Phase 0 classification record required by the implementation pack.
