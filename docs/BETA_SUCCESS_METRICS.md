# Beta Success Metrics & Exit Criteria

> Phase 19 — Controlled External Beta measurement and go/no-go criteria.
> Tracked during beta to determine when to proceed to Phase 20 (Limited Launch).

## Usage Metrics

| Metric | Definition | Target |
|--------|-----------|--------|
| Activation Rate | % of invited testers who complete first session | > 60% |
| Session Count | Total beta tester sessions per day | > 3 / tester |
| Task Completion Rate | % of initiated workflows that complete successfully | > 85% |
| Active Tester Count | Number of testers with activity in last 7 days | > 1 (pilot), > 3 (full) |

## Quality Metrics

| Metric | Definition | Target |
|--------|-----------|--------|
| Approval Acceptance Rate | % of AI recommendations approved | > 70% |
| False-Positive Rate | % of recommendations rejected as incorrect | < 20% |
| Safe Error Count | Total safe errors returned to testers | < 10 / day |
| Rate-Limit Events | Times testers hit rate limits | < 5 / day |
| Org-Boundary Denials | Cross-org access attempts denied | 0 (or investigated) |

## Reliability Metrics

| Metric | Definition | Target |
|--------|-----------|--------|
| Workflow Failure Rate | % of workflows that fail | < 5% |
| MCP Failure Rate | % of MCP tool calls that fail | < 3% |
| API Uptime | % of time API responds successfully | > 99.5% |
| Database Connectivity | Successful queries / total queries | > 99% |

## Operational Metrics

| Metric | Definition | Target |
|--------|-----------|--------|
| Operator Time Per Day | Time spent reviewing/approving | < 30 min / day |
| Approval Backlog | Max pending approvals at end of session | < 10 |
| Support Tickets by Severity | LOW / MEDIUM / HIGH / CRITICAL | < 2 HIGH / day |
| Feedback Response Time | Time to first response | < 4 hours HIGH, < 24 hours LOW |
| Beta Tester Retention | % of testers active in week 2+ | > 50% |

## Exit Criteria for Phase 19 → Phase 20

All criteria must be met before deciding to proceed to Phase 20 (Limited Launch).

### Security Gates (MANDATORY — all must pass)

| Criterion | Evidence Required |
|-----------|------------------|
| No critical security incidents | Incident log review |
| Zero cross-org data leaks | Auth boundary audit log |
| No live provider accidental calls | Provider gate audit |
| Kill switch tested and verified | Drill completion report |
| Rollback drill passed | Rollback verification |
| Production readiness still false | Health endpoint check |
| Live provider flags still false | Config verification |

### Operational Gates (MANDATORY — all must pass)

| Criterion | Evidence Required |
|-----------|------------------|
| Operator can complete daily workflow under 30 min | Time tracking |
| Approval drill completed successfully | Drill report |
| Beta smoke script passes | Smoke test log |
| Safe error rate within target | Metrics dashboard |
| Rate-limit events within target | Metrics dashboard |

### Quality Gates (RECOMMENDED — review before proceeding)

| Criterion | Evidence Required |
|-----------|------------------|
| Approval acceptance rate > 70% | Metrics dashboard |
| False-positive rate < 20% | Metrics dashboard |
| Beta users provide actionable feedback | Feedback inbox review |
| At least 2 weeks of beta data | Calendar timeline |
| No major confusion patterns | UX log review |

## Decision Process

```
Collect metrics (daily)
  └→ Review exit criteria (weekly)
       ├→ ALL security gates PASS
       ├→ ALL operational gates PASS
       ├→ Quality gates reviewed
       └→ Go/No-Go decision by operator
            ├→ PASS → Phase 20 Limited Launch
            └→ FAIL → Continue beta with fixes
```

## Metrics Collection

Metrics are collected:
- Automatically: via API request logs, safe error counters, workflow execution logs
- Manually: operator time tracking, feedback review annotations

No secrets, PII, or credentials are logged in metrics collection.
