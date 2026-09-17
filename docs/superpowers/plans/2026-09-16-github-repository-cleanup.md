# GitHub Repository Cleanup Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Reduce the `bravforcode` GitHub account to a small active product portfolio while preserving history, demos, attribution, recovery, and links.

**Architecture:** Keep seven intentional active repositories, selectively import unique capabilities from five donor repositories into Graxia OS, archive seventeen portfolio/prototype repositories with clear notices, leave the already archived placeholder unchanged, and quarantine one empty repository before optional deletion. Archiving is reversible and is the default action.

**Tech Stack:** Git, Git bundles, GitHub repositories/Issues/PRs/Actions/Pages/Releases, secret scanning, SHA-256 manifests.

## Global Constraints

- `krisphy` and `adminmate-ai` are protected: do not edit, rename, transfer, archive, delete, or change visibility.
- Re-fetch repository metadata immediately before each action. This classification is based on the 2026-09-16 audit and may become stale.
- Do not delete a non-empty repository as part of this plan.
- Do not archive a donor until its imported behavior passes parity and production soak gates.
- Backups must include every branch, tag, note, and Git LFS object where applicable and must pass restore verification.
- Public URLs, demos, package consumers, GitHub Pages, deployment hooks, webhooks, Actions schedules, branch protections, Releases, and open work must be inventoried before archive.
- Never place a secret into archive notices, manifests, bundles stored in public locations, or evidence.

---

## Repository Disposition

### Keep active

| Repository | Role | Required cleanup |
|---|---|---|
| `graxia-os` | Canonical product/control plane | Remove runtime/vendor artifacts, narrow workflows, document canonical boundaries |
| `ai-factory` | Storefront | Complete live-payment plan and remove secret/public-asset risk |
| `portfolio-production` | Sales portfolio | Keep claims evidence-backed and current |
| `bravforcode` | GitHub profile | Link only active products and verified case studies |
| `thaolai-web` | Client system | Keep separate; choose canonical PHP/Go path before normal development |
| `krisphy` | Protected | No action |
| `adminmate-ai` | Protected | No action |

### Import unique capability, then archive

| Repository | Import target | Archive gate |
|---|---|---|
| `revenue-os` | `graxia/packages/revenue_os`, `graxia/services/revenue_os_api` | Revenue production evidence + 14-day soak |
| `auto-post` | Graxia Content Ops | Content parity + bounded live canary + 14-day soak |
| `fastwork-promo-automation` | Graxia lead/content connector only | Connector tests and no standalone deployment dependency |
| `OBS-rag` | `graxia_knowledge` adapters/data contract only | Knowledge import and retrieval parity; no private vault data committed |
| `enterprise-agent-os` | Graxia runtime patterns only | Existing Graxia runtime proven to cover selected behavior |

### Archive as portfolio/prototype

| Repository | Pre-archive action |
|---|---|
| `vibescity-live` | Disable/fix the issue-spamming workflow, classify 22 duplicate security issues, resolve/close 13 stale/conflicting PRs |
| `gosoft` | Add demo status, limitations, and final artifact link |
| `mu-x-harvard` | Preserve competition result as an evidence-qualified case study |
| `Safescan-ai` | Add non-production/safety disclaimer and demo status |
| `flashfix-ai` | State that backend proxy/security/accessibility work is incomplete |
| `thaireview-platform` | Mark prototype and preserve architecture notes |
| `thailand-flood-monitor` | Mark prototype/grant asset and data limitations |
| `harvest-ecc` | Preserve partner/grant demo and license/provenance note |
| `sriracha-coast-watch` | State localStorage/demo-only behavior without backend |
| `Nasa-hackathon-2026` | Preserve contest submission, provenance, and computed-vs-heuristic disclosure |
| `climate-web` | State Supabase provisioning dependency and grant/B2G status |
| `jobshield-ai` | Preserve demo and mark buyer validation unproven |
| `Solven` | Preserve prototype and mark buyer/revenue validation unproven |
| `Intersite-Track` | Preserve generic PM prototype or link replacement internal tool |
| `graxia-trade` | Mark research-only and no live-trading authorization |
| `NIGHT_SALVAGE` | Preserve Roblox vertical slice and incomplete Studio playtest status |
| `prompt-perfected` | Preserve skeleton/prototype status |

### Already archived / deletion quarantine

| Repository | Decision |
|---|---|
| `Train-llm` | Leave archived; no action |
| `lotusdis` | Empty-repository deletion candidate after verified empty bundle and 30-day quarantine |

### Task 1: Create a machine-readable inventory

**Files:**
- Create: `docs/repository-inventory.yaml`
- Create: `scripts/repository_inventory.py`
- Test: `tests/test_repository_inventory.py`

**Interfaces:**
- One entry per owned repository with visibility, default branch, HEAD, size, archived state, Pages, Releases, open issues/PRs, workflows, deployments, secrets disposition, bundle path/hash, owner, action, gate, and replacement URL.

- [ ] **Step 1: Write a failing inventory test** requiring exactly the 31 audited repository names and forbidding `archive/delete` actions for `krisphy` and `adminmate-ai`.
- [ ] **Step 2: Implement read-only inventory collection** from GitHub and local Git where available.
- [ ] **Step 3: Record unknown/unauthorized fields as `unknown`** rather than assuming no resource exists.
- [ ] **Step 4: Generate `repository-inventory.yaml`** and manually review every visibility/action field.
- [ ] **Step 5: Commit** as `docs(github): add governed repository inventory`.

### Task 2: Build and verify recovery bundles

**Files:**
- Create: `docs/consolidation/archive-receipts/bundles.json`
- Create: `scripts/verify_repo_bundle.ps1`
- Test: `tests/test_verify_repo_bundle_script.py`

**Interfaces:**
- Bundle receipt includes repository, source HEAD, refs count, bundle SHA-256, LFS status, storage location ID, verification time, and restore-test result.

- [ ] **Step 1: Create a mirror clone in a task-specific temporary directory** for each repository scheduled for archive/delete.
- [ ] **Step 2: Fetch all branches, tags, notes, and LFS objects** without exposing credentials in command output.
- [ ] **Step 3: Create a `.bundle` and SHA-256 checksum** and store it in the approved private backup location.
- [ ] **Step 4: Verify the bundle** and clone one disposable restore copy to prove refs and HEAD.
- [ ] **Step 5: Record receipts** and remove only the verified temporary mirror/restore directories.

### Task 3: Prepare donor repositories for consolidation

**Files:**
- Modify: `revenue-os/README.md`
- Modify: `auto-post/README.md`
- Modify: `fastwork-promo-automation/README.md`
- Modify: `OBS-rag/README.md`
- Modify: `enterprise-agent-os/README.md`

**Interfaces:**
- Donor notice fields: status, canonical target, frozen source SHA, imported capability list, intentionally rejected components, migration date, rollback bundle receipt, and support location.

- [ ] **Step 1: Complete the corresponding import/parity work** before changing status to archived.
- [ ] **Step 2: Tag the final donor state** and ensure the tag exists in its bundle.
- [ ] **Step 3: Add a factual archive notice** without deleting historical documentation.
- [ ] **Step 4: Disable Actions schedules, deployments, webhooks, bots, and provider credentials** only after the canonical replacement is verified.
- [ ] **Step 5: Keep the donor writable during the 14-day rollback window** and prohibit new feature work there.

### Task 4: Repair noisy/stale GitHub state before archive

**Files:**
- Modify: `.github/workflows/**` in affected repositories only
- Create: `docs/consolidation/archive-receipts/issue-pr-cleanup.json`

**Interfaces:**
- Produces a reasoned disposition for each open issue/PR; no silent bulk closure.

- [ ] **Step 1: In `vibescity-live`, disable the loop creating duplicate `[Ops Agent][CRITICAL] security-gate` issues** and prove a dry run creates at most one deduplicated issue.
- [ ] **Step 2: Label duplicate issues, link the canonical issue, and close duplicates** with a factual automation-cleanup comment.
- [ ] **Step 3: Review every open PR** for unique commits, conflicts, dependency value, and security impact.
- [ ] **Step 4: Merge only independently reviewed green work; otherwise close with the exact archival reason.**
- [ ] **Step 5: Repeat issue/PR classification** for every repository before archive and record counts plus URLs.

### Task 5: Add archive notices and redirects

**Files:**
- Modify: `README.md` in each archive candidate
- Modify: GitHub repository description/homepage/topics
- Create: `docs/consolidation/archive-notice-template.md`

**Interfaces:**
- Every public archive states what it is, why it is archived, whether it is production-ready, where active work moved, license/provenance status, and how to view the demo.

- [ ] **Step 1: Generate a repository-specific notice** from the reviewed inventory; do not use unsupported performance/user/revenue claims.
- [ ] **Step 2: Preserve portfolio screenshots/releases** and mark broken live demos clearly.
- [ ] **Step 3: Point successor projects to the exact active repository/page.**
- [ ] **Step 4: Verify all links from both the archive README and the GitHub profile.**
- [ ] **Step 5: Create a final release/tag** only when it adds recovery value and does not expose generated secrets/assets.

### Task 6: Archive in controlled batches

**Files:**
- Update: `docs/repository-inventory.yaml`
- Create: `docs/consolidation/archive-receipts/batch-1.json`
- Create: `docs/consolidation/archive-receipts/batch-2.json`
- Create: `docs/consolidation/archive-receipts/batch-3.json`

**Interfaces:**
- Produces reversible GitHub archive actions with before/after metadata.

- [ ] **Step 1: Request explicit approval** listing exact repositories in the batch and their current visibility.
- [ ] **Step 2: Batch 1 — archive low-risk prototypes** only after bundles and notices pass.
- [ ] **Step 3: Verify read access, Releases, Pages behavior, profile links, and bundle recovery.**
- [ ] **Step 4: Batch 2 — archive portfolio/hackathon repositories** after the same checks.
- [ ] **Step 5: Batch 3 — archive donor repositories** only after their system-specific soak gates.
- [ ] **Step 6: Record the GitHub actor, timestamp, repository URL, before/after archived state, and inventory commit SHA.**

### Task 7: Quarantine and optionally delete the empty repository

**Files:**
- Create: `docs/consolidation/archive-receipts/lotusdis-quarantine.json`

**Interfaces:**
- Produces a 30-day no-use quarantine and a separate deletion approval request.

- [ ] **Step 1: Verify `lotusdis` has no branches/tags/releases/issues/PRs/Packages/Pages/deployments/webhooks or unique commits beyond initialization.**
- [ ] **Step 2: Create and restore-verify its bundle even if empty.**
- [ ] **Step 3: Archive it and record the quarantine start date.**
- [ ] **Step 4: After 30 days, re-fetch all state and search profile/docs/deployments for references.**
- [ ] **Step 5: Ask for a second explicit confirmation naming only `bravforcode/lotusdis`.**
- [ ] **Step 6: Delete only after confirmation and record that GitHub deletion may require support/recreation for recovery; retain the private bundle.**

### Task 8: Verify the cleaned account

**Files:**
- Finalize: `docs/repository-inventory.yaml`
- Create: `docs/consolidation/github-cleanup-closeout.md`

**Interfaces:**
- Produces a closeout report with active/archived/deleted counts and unresolved exceptions.

- [ ] **Step 1: Re-list all owned repositories** and compare against the approved disposition.
- [ ] **Step 2: Verify protected repositories are byte/state unchanged** except normal independent user activity.
- [ ] **Step 3: Verify active repositories have green/default workflows, correct descriptions, and current replacement links.**
- [ ] **Step 4: Verify archived repositories are read-only and recoverable from bundles.**
- [ ] **Step 5: Update `bravforcode` and `portfolio-production`** so only active products and selected archived case studies are prominent.

## Exit Criteria

- Exactly seven repositories remain intentionally active unless the user approves a revised inventory.
- `krisphy` and `adminmate-ai` were not mutated by this cleanup.
- All donor capabilities required by Graxia have parity evidence before archive.
- Every archived/deleted candidate has a verified private bundle and an accurate notice.
- No non-empty repository is deleted; `lotusdis` deletion requires a second explicit approval after quarantine.
- GitHub profile and portfolio no longer direct visitors to broken or misleading active projects.
