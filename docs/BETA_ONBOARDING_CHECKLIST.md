# Beta Onboarding Checklist

> Phase 20 — Limited Beta Launch Packet
> Operator-led onboarding for each new beta tester.
> **Manual process only** — no self-serve onboarding.

## Pre-Onboarding (Operator)

- [ ] Tester confirmed interest (replied to invite)
- [ ] Tester added to `BetaRegistry` via `add_tester()`
- [ ] Tester activated via `activate_tester()`
- [ ] Limits configured (sessions/day, workflows/day, MCP calls/day)
- [ ] Onboarding session scheduled (30 minutes)
- [ ] Test environment verified:
  - [ ] `/api/v1/health` returns `status: ok`
  - [ ] `/api/v1/health/readiness/beta` returns with appropriate checks
  - [ ] `KILL_SWITCH_ALL_EXTERNAL_BETA = true` (locked)
  - [ ] `production_ready = false` confirmed
  - [ ] `NO_LIVE_PAYMENT_MODE = true` confirmed
  - [ ] No live provider flags enabled

## During Onboarding (Operator + Tester)

### Setup (5 min)
- [ ] Tester receives access credentials (if applicable)
- [ ] Tester confirms they can log in / access the system
- [ ] Tester understands: **all output is draft-only**

### First Guided Workflow (15 min)
- [ ] Walk through one complete workflow:
  1. Browse opportunities (/opportunities)
  2. Review an AI recommendation
  3. Approve or reject the recommendation
  4. See that no real action was taken without approval
  5. Submit feedback on the recommendation
- [ ] Confirm tester understands the approval flow
- [ ] Show tester how to submit feedback

### Safety Briefing (5 min)
- [ ] "Nothing is sent or published automatically"
- [ ] "All AI output is draft-only until I (operator) approve it"
- [ ] "If something looks wrong, stop and submit feedback"
- [ ] "If something looks dangerous, stop and contact me immediately"
- [ ] "No real money — all payment features are in sandbox/test mode"

### Q&A (5 min)
- [ ] Tester asks questions
- [ ] Tester knows how to reach operator
- [ ] Confirm next session (if needed)

## Post-Onboarding (Operator)

- [ ] Session metrics recorded (duration, workflows completed, feedback submitted)
- [ ] Any issues from session logged
- [ ] Tester's limits reviewed (adjust if needed)
- [ ] Onboarding notes added to operator log

## Onboarding Success Criteria

- [ ] Tester completed at least one full workflow cycle
- [ ] Tester submitted at least one piece of feedback
- [ ] Tester confirmed understanding of draft-only / approval policy
- [ ] No security or safety incidents during onboarding
