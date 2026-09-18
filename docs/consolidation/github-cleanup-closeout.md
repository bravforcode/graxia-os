# GitHub cleanup closeout

Snapshot: 2026-09-18 11:10 UTC
Account: `bravforcode`
Canonical application: [`graxia-os`](https://github.com/bravforcode/graxia-os)

## Result

- 31 owned repositories were re-read from GitHub.
- 21 are archived, 10 remain active, and 0 were deleted.
- `auto-post` is already archived and its reviewed capability contract is
  recorded in `docs/consolidation/auto-post-capability-crosswalk.md`.
- `ai-factory` checkout integration is merged to default `master` in PR #4:
  [`c1d027f`](https://github.com/bravforcode/ai-factory/commit/c1d027f9482173cd74673aa5dffd13ff06cf1cfd).
- `krisphy` and `adminmate-ai` were not modified, archived, renamed, or
  deleted.

## Security gate

Graxia PR #52 is mergeable after the branch was synchronized with `main`, but
the required GitHub `Secret Scanning` check failed. The check reported a
verified Telegram bot-token finding in historical repository content. The
secret value is intentionally not copied into this record.

- No required security check was bypassed.
- No history rewrite or credential revocation was performed automatically.
- The exact remediation is to identify the owning bot, revoke/rotate its
  credential, remove the current-tree occurrence, and then plan any history
  rewrite with a verified private recovery bundle.
- The machine-readable redacted receipt is
  `docs/evidence/revenue-os/2026-09-18-github-security-gate/manifest.json`.

## Intentional active set

| Repository | Role | Current state | Next action |
|---|---|---|---|
| `graxia-os` | Canonical control plane / Revenue OS / Content Ops | active; 6 open PRs | review only money-path-related changes |
| `ai-factory` | Static storefront | active; checkout bridge merged | deploy/operate from default branch |
| `portfolio-production` | Public portfolio | active | keep verified claims only |
| `bravforcode` | Profile | active | link canonical products |
| `thaolai-web` | Separate client system | active | keep separate |
| `revenue-os` | Rollback donor | private, 1 open PR | freeze; archive only after soak/recovery gates |
| `vibescity-live` | Portfolio/prototype | public, 13 open PRs | do not auto-close; classify separately |
| `lotusdis` | Empty-repository quarantine candidate | private, no branches | re-check after quarantine; never delete without new approval |
| `krisphy` | Protected product | active | no action |
| `adminmate-ai` | Protected product | active | no action |

The remaining 21 repositories are already archived, including `auto-post`.
The exact machine-readable disposition remains in
[`docs/repository-inventory.yaml`](../repository-inventory.yaml).

## Closeout gates

Passed for this scope:

- production Vercel 504 fix deployed and verified with HTTP 200 health,
  product, checkout-creation, and hosted Checkout-page responses;
- local Revenue OS suite: 390 passed;
- funnel suite: 23 passed after the serverless logging/startup fixes;
- AI Factory contract suite: 7 passed, 8 subtests passed;
- no repository deletion performed.

Owner-waived, therefore not claimed as evidence:

- real Stripe payment;
- paid fulfillment/email/refund/replay proof;
- staging payment exercise.

Still intentionally open:

1. fourteen calendar days of production soak from 2026-09-18;
2. final recovery-bundle/inventory re-check before donor archive;
3. review of unrelated open PRs in `graxia-os`, `revenue-os`, and
   `vibescity-live`.
4. remediate the historical Telegram token finding before merging PR #52.

This file is a closeout record, not an authorization to delete repositories or
to represent an unperformed charge as completed.
