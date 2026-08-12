# Beta Tester Selection Criteria

## Objective
Select 1–3 manual beta testers for the Graxia OS Limited Beta Pilot. All selection is **operator-led** — no self-serve signup, no automated invite.

---

## Eligibility Criteria

### Required (MUST meet all)
- [ ] Operator has a direct existing relationship with the tester (trusted contact)
- [ ] Tester understands this is a **controlled beta** — not a production system
- [ ] Tester agrees that **no live payment, no real send, no real publish** will occur
- [ ] Tester can dedicate 30–60 minutes for the first guided session
- [ ] Tester has a clear business need that Graxia OS addresses (lead gen, opportunity tracking, content drafting)
- [ ] Tester signs the Beta Tester Agreement (see `BETA_LAUNCH_POLICY.md` — Appendix A)
- [ ] Tester's data is low-sensitivity (no PII/PHI/classified data during beta)
- [ ] Tester agrees to provide structured feedback after each session

### Preferred (strongly recommended)
- [ ] Tester is technically literate (can navigate a web app, understand "draft" vs "live")
- [ ] Tester is willing to report bugs and confusion promptly
- [ ] Tester has used similar tools (CRM, deliverable management, AI assistants)
- [ ] Tester can tolerate rough edges and incomplete features
- [ ] Tester can commit to at least 2 sessions over 1–2 weeks

### Excluded (MUST NOT)
- [ ] No competitors or parties with conflicting interests
- [ ] No individuals who cannot sign a basic confidentiality/non-disclosure agreement
- [ ] No high-risk or regulated industries (healthcare, finance, legal) without explicit legal review
- [ ] No minors
- [ ] No automated accounts or bots
- [ ] No external vendors or partners without explicit operator approval
- [ ] No one who expects production-grade SLAs, uptime guarantees, or data durability

---

## Tester Vetting Process

1. **Identify candidate** — Operator selects from existing network
2. **Review criteria** — Operator confirms candidate meets all Required criteria
3. **Send invite** — Use `BETA_MANUAL_INVITE_TEMPLATE.md`
4. **Receive signed agreement** — Get written (email/DocuSign) acknowledgment of beta terms
5. **Register in BetaRegistry** — Operator adds tester via in-memory registry
6. **Schedule session** — Use `BETA_SESSION_SCRIPT.md` for the first session
7. **Pre-session verification** — Operator runs `PHASE21_STARTING_BASELINE.md` pre-session checklist

---

## Tester Limits (Phase 21)

| Parameter | Limit |
|---|---|
| Max testers | 3 |
| Sessions per tester per day | 1 |
| Workflows per session | 5 |
| MCP calls per session | 20 |
| Session duration | 60 minutes max |
| Total beta duration | 4 weeks (from first session) |

---

## Tester Status Lifecycle

```
invited → active → paused → removed
                ↓
          completed (graduated)

invited:   Invite sent, awaiting signed agreement
active:    Signed, registered, session in progress
paused:    Temporarily suspended (operator decision)
removed:   Permanently removed from beta
completed: Tester has completed their beta participation
```

---

## What to Screen For in First Interaction

- **Expectation management**: Does the tester understand "draft-only", "no live payment", "no SLA"?
- **Technical readiness**: Can the tester access the staging URL? Can they log in?
- **Feedback willingness**: Is the tester willing to give structured feedback?
- **Domain fit**: Does the tester's use case match Graxia OS capabilities?

---

## Post-Selection Record

After selecting a tester, operator records:

```json
{
  "tester_id": "tester-001",
  "selected_at": "2026-05-29T00:00:00Z",
  "criteria_checked": true,
  "agreement_signed": true,
  "status": "active",
  "notes": "Brief note on why this tester was selected"
}
```

This record is kept in the operator's session notes (not in code, not in the BetaRegistry).
