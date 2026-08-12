# Phase 22 — Defect Triage Guide

Systematic severity classification for AI Tester Lab findings.

## Severity Levels

### S0 — Hard Safety Stop

Must fix immediately, block all progress.

| Condition | Example |
|-----------|---------|
| Live provider call executed | Stripe charge, email send, content publish |
| Cross-org data leak | Org A sees Org B's data |
| Approval bypass | Action executed without human approval |
| Secret leak | Raw API key/token in output |
| Production readiness enabled | PRODUCTION_READY = true |

**Action:** Stop all testing, fix immediately, re-verify all safety gates.

### S1 — Critical Beta Blocker

Cannot run beta session until fixed.

| Condition | Example |
|-----------|---------|
| Session script cannot be followed | Missing step blocks flow |
| Kill switch fails to block | Beta accessible when locked |
| Production readiness false by default broken | PRODUCTION_READY somehow true |
| Workflow produces unsafe output | Draft contains live action |

**Action:** Fix before any human beta session.

### S2 — Major UX/Runtime Blocker

User cannot complete task.

| Condition | Example |
|-----------|---------|
| Confusing safety copy | User doesn't understand what's allowed |
| Approval unclear | User doesn't know do/skip/delay |
| Backend cannot boot | Environment issue |
| Workflow silently fails | No error, no output |

**Action:** Fix before expanding beta to more testers.

### S3 — Minor Improvement

Non-blocking usability issue.

| Condition | Example |
|-----------|---------|
| Wording improvement | Better label text |
| Helper text missing | Add tooltip/description |
| Empty state unhelpful | "No results" without guidance |
| Layout awkward | Visual polish needed |

**Action:** Batch into next fix pack.

### S4 — Backlog

Nice-to-have, later polish.

| Condition | Example |
|-----------|---------|
| Animation polish | Framer Motion transitions |
| Color scheme refinement | Aesthetic improvement |
| Additional persona tasks | More roleplay scenarios |
| Documentation expansion | Add more runbook detail |

**Action:** Add to backlog for future phases.

## Triage Process

1. **Identify** — Capture finding with evidence (request_id, screenshot, or code reference)
2. **Classify** — Assign severity S0-S4 using criteria above
3. **Document** — Record in fix pack recommendations doc
4. **Prioritize** — S0/S1 immediate, S2 next release, S3 batch, S4 backlog
5. **Verify** — After fix, re-run relevant tests to confirm resolution

## Phase 22 Findings

| ID | Finding | Severity | Evidence | Status |
|----|---------|----------|----------|--------|
| F001 | No browser E2E testing executed | S2 | `docs/PHASE22_BROWSER_E2E_DEFERRED.md` | Documented |
| F002 | No backend runtime testing | S2 | Terminal-only session | Documented |
| F003 | No real human UX feedback | S1 | AI roleplay only | Documented |
| F004 | accessibility_confidence = 0 | S2 | No UI available | Documented |
