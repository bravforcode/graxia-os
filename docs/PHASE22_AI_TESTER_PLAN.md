# Phase 22 — AI Tester Lab Operating System

**Version:** 1.0
**Commit:** `ea2328e`
**Date:** 2026-05-29

## 0. Mission

Build a complete **AI Tester Lab Operating System** for Graxia OS.

The AI must become the tester itself, but in an enterprise-grade, evidence-driven way:

```
what was tested
how it was tested
which mode was used
which persona performed it
which evidence was captured
which risks remain
which claims are downgraded
which fixes should happen next
```

## 1. Current Context

After Phase 21.5:

```text
Phase 16 — Enterprise Security Boundary = PASS
Phase 17 — Staging Runtime Gate = PASS
Phase 18 — Production Dry-Run / Hardening = PASS
Phase 19 — Controlled External Beta Gate = PASS
Phase 20 — Limited Beta Launch Packet = PASS
Phase 21 — Pre-session documentation readiness = PASS
Phase 21.5 — AI-led terminal-only first-session rehearsal = PASS with caveats
```

Known caveats from Phase 21.5:

- AI-led, not real human
- terminal-only (no backend running)
- no proven interactive browser session
- no proven live local backend runtime session
- workflows mostly verified by tests/code inspection
- no real human UX feedback
- production remains disabled

## 2. Target State

```text
AI_TESTER_LAB_READY = true
SYNTHETIC_BETA_VALIDATED = true if gates pass
REAL_HUMAN_BETA_VALIDATED = false unless real human session occurs
PRODUCTION_READY = false
LIVE_PROVIDERS_ENABLED = false
```

## 3. Test Mode Taxonomy

| Mode | Description | Can Claim |
|------|-------------|-----------|
| STATIC_REVIEW | Reads docs/code/tests only | Copy review, docs review, test coverage review |
| TEST_HARNESS | Runs pytest, compileall, frontend build | Engineering confidence only |
| API_RUNTIME | Sends actual HTTP requests to backend | API runtime tested |
| BROWSER_E2E | Uses Playwright on frontend | UI tested |
| SYNTHETIC_ROLEPLAY | AI acts as user/operator/adversary | Synthetic persona feedback only |
| ADVERSARIAL_SECURITY | Safe abuse cases with test data | Security boundary tested |
| EVIDENCE_AUDIT | Reviews evidence, downgrades claims | Evidence quality assessment |

## 4. AI Tester Roles

| ID | Role | Output |
|----|------|--------|
| R01 | Test Director AI | Test plan, mission, pass criteria |
| R02 | Novice User AI | Synthetic novice user report |
| R03 | Founder/Power User AI | Synthetic founder user report |
| R04 | Busy Operator AI | Operator AI report |
| R05 | Privacy-Conscious User AI | Privacy user report |
| R06 | Thai/English Mixed User AI | TH/EN user report |
| R07 | Accessibility/UX Heuristic AI | Accessibility/UX report |
| R08 | Adversarial Security Tester AI | Adversarial safety report |
| R09 | QA Automation AI | QA automation report |
| R10 | Evidence Auditor AI | Evidence auditor report |
| R11 | Fix Pack Planner AI | Fix pack recommendations |

## 5. Hard Safety Rules

Never:
- read .env, print secrets, git push, enable production readiness
- call live providers, send real email, charge real money
- bypass approval, claim human feedback without human
- claim UI tested without browser evidence
- claim API tested without runtime calls

## 6. Honesty Gate Rules

| Rule | Condition | Enforcement |
|------|-----------|-------------|
| H001 | browser_used=false | UI_TESTED claim forbidden |
| H002 | api_calls empty | API_TESTED claim forbidden |
| H003 | workflow_runs empty | WORKFLOW_EXECUTED claim forbidden |
| H004 | role is synthetic | HUMAN_FEEDBACK claim forbidden |
| H005 | backend_running=false | RUNTIME_TESTED claim forbidden |
| H006 | no request_id/correlation_id | Evidence quality capped |
| H007 | production_ready=true | Hard fail |
| H008 | any live provider flag true | Hard fail |
| H009 | approval bypass observed | Hard fail |
| H010 | raw token/secret in evidence | Hard fail |

## 7. Confidence Score Caps

| Score | Max Without Runtime Evidence |
|-------|------------------------------|
| human_ux_confidence | 40 (no real human) |
| ui_confidence | 50 (no browser used) |
| api_confidence | 50 (backend not running) |
| workflow_confidence | 60 (tests only) |
| mcp_confidence | 60 (no runtime MCP call) |
| evidence_quality | 60 (no request_id/correlation_id) |

## 8. Lanes

| Lane | Deliverable |
|------|-------------|
| A | Baseline + Gap Analysis |
| B | Personas + Task Library |
| C | Evidence + Honesty + Scoring |
| D | Runner + API Smoke |
| E | MCP + Workflow Synthetic |
| F | Operator + Adversarial |
| G | Browser/UI E2E |
| H | UX/Accessibility/Metrics/Triage |
| I | Roleplay Reports |
| J | Verification |
| K | Closeout |
