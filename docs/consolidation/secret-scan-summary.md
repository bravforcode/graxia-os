# Pre-Consolidation Secret Scan Summary

Date: 2026-09-17
Status: FINDINGS — LIVE GATE BLOCKED

This file records the safety boundary before repository consolidation. It does
not claim that the repositories are secret-free.

## Redacted scan evidence

On 2026-09-17, `scripts/secret_scan.py` scanned tracked files and reachable
history blobs for the following local repositories:

| Repository | Candidate findings | History scope |
|---|---:|---|
| `graxia os` | 311 | up to 10 commits / 100 blobs; truncated |
| `revenue-os` | 69 | up to 10 commits / 100 blobs; truncated |
| `auto-post` | 66 | up to 10 commits / 100 blobs; truncated |
| `ai-factory` | 8 | up to 10 commits / 100 blobs; truncated |

Evidence: `docs/consolidation/secret-scan-2026-09-17.json`. The report stores
only rule IDs, paths, line numbers, and opaque Git object references; it does
not store matched values. These are candidate matches and may include test,
example, archived, or false-positive material. Untracked and ignored files
were not included in this baseline because donor trees contain large generated
and runtime surfaces; they require a separate bounded review.

Observed risk categories from root-level repository state:

- Environment files and timestamped environment backups exist in donor worktrees.
- Virtual environments, local databases, scheduler state, generated artifacts,
  logs, screenshots, and reports exist in donor worktrees.
- Provider credentials, OAuth material, and API keys may exist outside tracked
  source; values were not read or copied.
- A broader history-aware scan and reviewed untracked/ignored candidate scan
  are still required before any import, bundle publication, deployment, or
  archive.

Required next scan:

1. Scan tracked history and reviewed untracked candidates in each donor.
2. Record file paths, rule IDs, commit IDs, and remediation state only.
3. Rotate/revoke any confirmed or uncertain live credential before Ai Factory
   live mode.
4. Remove secrets from current source and prepare history rewrite only with
   explicit approval if a confirmed live secret appears in Git history.

Blocked until scan and remediation complete:

- live payment enablement;
- production deployment or migration;
- donor import containing unclassified files;
- GitHub archive or deletion;
- public release of evidence bundles.
