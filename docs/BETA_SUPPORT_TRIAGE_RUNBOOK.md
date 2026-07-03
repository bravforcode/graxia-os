# Beta Support Triage Runbook

> Phase 19 — Controlled External Beta support triage procedures.
> **No auto-send · No auto-publish · No real charges.**

## Feedback Flow

Beta testers submit feedback via the in-app feedback form or API.

```json
{
  "feedback_type": "bug | confusion | value | missing_feature | safety_concern",
  "severity": "low | medium | high | critical",
  "message": "Description of the issue or feedback",
  "request_id": "req_xxx (if available)",
  "correlation_id": "corr_xxx (if available)"
}
```

**Safety Rule:** Feedback messages must never contain secrets, passwords, API keys, or personally identifiable information.

## Triage Priority Matrix

| Severity | Response Time | Action |
|----------|---------------|--------|
| **Critical** | < 1 hour | Immediate investigation — pause affected tester(s) if needed |
| **High** | < 4 hours | Investigation within same session — fix or workaround |
| **Medium** | < 24 hours | Triage within 1 business day — prioritize by impact |
| **Low** | < 72 hours | Log for iteration planning |

## Triage by Feedback Type

### Bug
1. Check `request_id` and `correlation_id` for tracing
2. Reproduce in staging environment
3. Determine if isolated or systemic
4. Fix or file with reproduction steps
5. Update tester when resolved

### Confusion
1. Check error logs for related safe errors
2. Review UI flow or prompt wording
3. Provide clarification to tester
4. Log as UX improvement opportunity

### Value
1. Acknowledge to tester within 24 hours
2. Log as positive signal for go/no-go decision
3. Track in beta success metrics

### Missing Feature
1. Check if already planned in roadmap
2. Add to feature request tracking
3. Respond to tester with timeline if available

### Safety Concern
1. **Escalate immediately to operator**
2. Review system logs around the reported incident
3. Check for cross-org data leaks or auth boundary violations
4. If confirmed: pause tester, trigger kill switch if needed
5. Begin incident response (see `docs/INCIDENT_RESPONSE_RUNBOOK.md`)

## Escalation Path

```
Tester submits feedback
  └→ Automated triage by severity
       ├→ LOW/MEDIUM: Logged, operator reviews daily
       ├→ HIGH: Notify operator within 4 hours
       └→ CRITICAL: Notify operator immediately
            └→ Operator reviews and decides:
                 ├→ Pause affected tester(s)
                 ├→ Continue monitoring
                 ├→ Trigger kill switch
                 └→ Escalate to incident response
```

## Secrets Check

Before confirming any feedback:
- [ ] No raw emails in message body
- [ ] No API keys or tokens
- [ ] No passwords
- [ ] No session tokens
- [ ] No private keys
- [ ] No credentials of any kind

If secrets are found in feedback:
1. Delete the feedback record
2. Ask tester to resubmit without secrets
3. Check if related to a security incident

## Feedback Data Retention

- Feedback retained for duration of beta + 90 days
- After beta ends: anonymize or delete per data retention policy
- `request_id`/`correlation_id` retained for traceability only
