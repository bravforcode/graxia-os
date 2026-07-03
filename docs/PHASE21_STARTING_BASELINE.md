# Phase 21 — Starting Baseline

## Evidence Freeze (captured before Phase 21 execution)

| Check | Result |
|---|---|
| Latest commit | `750abd5` |
| Git status | Clean (unrelated line_agent/contact/scraper/Leads.tsx changes only) |
| Phase 20 tests | 65/65 pass |
| Phase 19 regression | 80/80 pass |
| Total gate tests | 145/145 pass |
| compileall | ✅ |
| Frontend build | ✅ |
| Alembic head | `021_add_funnel_v5_models` |
| Production readiness | `false` |
| Live providers enabled | `false` |
| NO_LIVE_PAYMENT_MODE | `true` (locked) |
| KILL_SWITCH_ALL_EXTERNAL_BETA | `true` (locked) |
| LIMITED_BETA_PILOT_READY | `false` |
| /readiness/beta | Available, 11 checks |
| /readiness/limited-beta-pilot | Available, 17 checks |
| Beta registry | In-memory, no DB migration |
| Human approval drill | ✅ (5 scenarios) |
| Feedback safety | ✅ (12 tests) |
| Kill switch drill | ✅ (10 tests) |
| Operator runbook | `BETA_OPERATOR_RUNBOOK.md` |
| Support triage runbook | `BETA_SUPPORT_TRIAGE_RUNBOOK.md` |
| Launch policy | `BETA_LAUNCH_POLICY.md` |
| Invite template | `BETA_MANUAL_INVITE_TEMPLATE.md` |
| Onboarding checklist | `BETA_ONBOARDING_CHECKLIST.md` |
| Session script | `BETA_SESSION_SCRIPT.md` |
| Smoke scripts | `beta_smoke.sh` + `beta_smoke.ps1` |

## Phase 21 Scope

Phase 21 is an **operational trial**, not a coding sprint. It does not add code, config, or tests. It produces:

- Tester selection criteria
- Session prep checklist
- Session observation sheet
- Kill switch standby check doc
- Feedback summary template
- Closeout report

## Hard Rules (inherited from Phase 19/20)

- Production readiness remains `false`
- Live providers remain disabled
- No real payments
- No auto-send / auto-publish / auto-invite
- All AI output remains draft-only until approved
- Kill switch remains locked

## Pre-Session Checklist (operator must verify)

- [ ] `git status --short` shows only expected changes
- [ ] 145+ gate tests pass
- [ ] compileall passes
- [ ] Frontend build passes
- [ ] Alembic head is `021_add_funnel_v5_models`
- [ ] /health returns 200
- [ ] /readiness/beta returns expected fields
- [ ] /readiness/limited-beta-pilot returns expected fields
- [ ] Kill switch is `true` and documented
- [ ] Beta tester has signed consent (per BETA_LAUNCH_POLICY.md)
- [ ] Beta tester is registered in BetaRegistry (in-memory)
- [ ] Operator has reviewed BETA_KILL_SWITCH_STANDBY_CHECK.md
- [ ] Operator has reviewed BETA_OPERATOR_RUNBOOK.md
- [ ] Operator has reviewed BETA_SESSION_SCRIPT.md
- [ ] Operator has BETA_SESSION_OBSERVATION_SHEET.md ready
- [ ] Feedback collection mechanism is ready
- [ ] Rollback plan is confirmed (see DEPLOYMENT.md / RUNBOOK.md)
