# G0 — Repository Reconciliation Report

**Date**: 2026-06-22
**Task**: Resolve 46-vs-56 inventory discrepancy in repository registry

## Source Counts

| Source | Count |
|--------|-------|
| `repositories.yml` | 56 |
| `quarantined_repositories.yml` | 4 |
| `repository_decisions.yml` | 56 |
| `approved_references.yml` | 52 |
| `test_repo_intelligence.py` EXPECTED_REPO_IDS | 56 |
| `test_repo_intelligence.py` QUARANTINED_IDS | 4 |

## Reconciliation

**All five sources are consistent. There is no 46-vs-56 discrepancy.**

- `repositories.yml` contains 56 entries.
- `EXPECTED_REPO_IDS` in the test file contains the same 56 repo IDs — perfect match.
- `repository_decisions.yml` covers all 56 repos (52 PENDING_REVIEW + 4 QUARANTINED).
- `quarantined_repositories.yml` lists exactly 4 repos, which are a subset of the 56.
- `approved_references.yml` lists 52 repos — the 52 non-quarantined repos. This is correct by design (quarantined repos are excluded).

### Where did the "46" come from?

The 46 count likely came from a **pre-reconciliation snapshot** — possibly from an earlier version of the master plan (Section 4.4) that only listed 46 repos before the HFT/arbitrage/quarantine section was added. The 10 additional repos in Section F (nkaz001_hftbacktest, algotraders_stock_analysis_engine, gazbert_bxbot, plus 4 Solana/BSC quarantined, plus 3 others from the sentiment/data group) may have been added in a later pass, bringing the total to 56. The test file and `repositories.yml` were updated to 56, but the original plan document may still reference 46.

## Reconciled Canonical

- **File**: `repositories_canonical.yml`
- **Count**: **56 repositories**
- **Schema**: Flat list with standardized fields: `repo_id`, `canonical_url`, `owner`, `name`, `asset_scope`, `language`, `license_spdx`, `pinned_commit`, `observed_at_utc`, `allowed_role`, `execution_permission`, `credential_permission`, `network_permission`, `quarantine_status`
- **Quarantined repos**: Included in canonical with `quarantine_status: true` and all permissions `false`
- **Decision fields**: Omitted from canonical (deferred to `repository_decisions.yml` which remains as the audit trail)

## Role Distribution

| Role | Count |
|------|-------|
| APPROVED_DIFFERENTIAL_ORACLE | 4 |
| APPROVED_ARCHITECTURE_REFERENCE | 7 |
| APPROVED_HYPOTHESIS_CORPUS | 8 |
| APPROVED_DATA_REFERENCE | 1 |
| CRYPTO_ONLY_REFERENCE | 10 |
| VERIFY_IDENTITY_ONLY | 22 |
| QUARANTINED | 4 |
| **Total** | **56** |

## Overlap Analysis

- Quarantined IDs (4) are fully contained within the 56 — no orphaned entries.
- No repos appear in `approved_references.yml` but not in `repositories.yml`.
- No repos appear in `repositories.yml` but not in `EXPECTED_REPO_IDS`.

## Files Preserved (no deletion per constraint)

- `repositories.yml` — original master registry (56 entries)
- `quarantined_repositories.yml` — quarantine detail (4 entries)
- `repository_decisions.yml` — audit trail (56 entries)
- `approved_references.yml` — approval detail (52 entries)
- `repositories_canonical.yml` — **new single source of truth** (56 entries)
