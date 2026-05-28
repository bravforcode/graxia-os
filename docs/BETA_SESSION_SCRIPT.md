# Beta Session Script

> Phase 20 — Limited Beta Launch Packet
> Guided first-session script for operator-led onboarding.
> **Approximately 30 minutes.**

## Pre-Session Check (Operator, 2 min)

```bash
# 1. Verify system health
curl /api/v1/health

# 2. Verify beta readiness
curl /api/v1/health/readiness/beta

# 3. Verify production gate remains closed
curl /api/v1/health/readiness/production

# 4. Confirm no pending approvals from previous sessions
```

Expected:
- Health: `status: ok`
- Beta readiness: all checks present (may have blockers — expected)
- Production readiness: `production_ready: false`
- Kill switch: `kill_switch_enabled: true`

## Session Start (Operator + Tester, 3 min)

**Operator says:**
> "Welcome to the Graxia OS beta pilot. This is a guided first session.
>
> Before we start, I want to make three things clear:
> 1. **Everything is draft-only.** The AI may suggest actions, but nothing is sent or published without my approval. You'll see this in action.
> 2. **No real money involved.** Any payment features you see are in sandbox/test mode.
> 3. **Your feedback is the goal.** What works, what's confusing, what's missing — all valuable.
>
> Ready? Let's start with the dashboard."

## Step 1: Dashboard Overview (Operator + Tester, 5 min)

**Operator demonstrates:**
1. Navigate to `/opportunities` — show the opportunity list
2. Show an AI-scored opportunity
3. Show the score and rationale
4. Click through to opportunity details

**Tester tries:**
1. Browse the opportunity list
2. Open one opportunity
3. Read the AI's scoring rationale
4. Say whether the score matches their intuition

**Feedback prompt:** "Does this opportunity look relevant? Is the score reasonable?"

## Step 2: AI Recommendation + Approval (Operator + Tester, 5 min)

**Operator demonstrates:**
1. Navigate to an opportunity with a draft recommendation
2. Show the draft (subject, body, call-to-action)
3. Show the approve/reject/revise options
4. **Demonstrate: selecting "Approve" does NOT send anything** — it just records approval
5. Show the item moves to "approved" status

**Tester tries:**
1. Review one AI recommendation
2. Read the draft
3. Submit an approval decision
4. Confirm the item is still in draft/no-send state

**Feedback prompt:** "Does the draft match what you would write? What would you change?"

## Step 3: Session Flow Simulation (Operator + Tester, 5 min)

**Scenario:** "You find an interesting opportunity and want the AI to draft a follow-up."

1. Select an opportunity marked "follow-up needed"
2. View the AI-generated follow-up draft
3. Check the approval status (should be "pending")
4. Submit your approval decision
5. Confirm: the system recorded the decision but did NOT send anything

**Safety check:**
- Open a new browser tab
- Check the email outbox (or equivalent)
- **Confirm zero emails sent**
- **Confirm zero content published**

**Feedback prompt:** "Does this flow match how you work? What's missing?"

## Step 4: Feedback Submission (Operator + Tester, 5 min)

**Operator demonstrates:**
1. Show the feedback form
2. Submit a sample feedback: "Confusion — the score explanation was too technical"
3. Show the feedback was recorded

**Tester tries:**
1. Submit one piece of feedback about anything seen so far
2. Classify it (bug / confusion / value / missing feature / safety concern)
3. Set severity

**Operator confirms:**
- Feedback received
- No secrets or credentials in the feedback message
- Feedback linked to correlation ID if available

## Step 5: Session Close (Operator + Tester, 5 min)

**Operator says:**
> "That's the guided session. Here's what happens next:
>
> - You can use the system on your own schedule
> - All AI output remains draft-only — nothing is sent without approval
> - I'll review and approve/reject items daily
> - Please submit feedback for anything notable (good or bad)
> - If something breaks or looks wrong, stop and message me
>
> Any final questions before we wrap up?"

**Tester final questions**

**Operator post-session:**
- [ ] Check approval backlog cleared
- [ ] Verify no unintended actions occurred
- [ ] Log session metrics (duration, workflows, feedback)
- [ ] Review feedback for actionable items
- [ ] Confirm tester activated for self-service use
- [ ] Schedule follow-up check-in (24-48 hours)

## Post-Session Verification (Operator, 2 min)

```bash
# 1. Confirm no email was sent
curl /api/v1/health/readiness/production | grep -i "email"

# 2. Confirm no Stripe charge was made
curl /api/v1/health/readiness/production | grep -i "stripe"

# 3. Confirm no Google mutation occurred
curl /api/v1/health/readiness/production | grep -i "google"

# 4. Confirm production readiness still false
curl /api/v1/health/readiness/production | grep "production_ready"

# 5. Confirm kill switch still active
curl /api/v1/health/readiness/beta | grep "kill_switch"
```

All should confirm "blocked" / "false" / "true" as appropriate.
