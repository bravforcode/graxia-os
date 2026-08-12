# Beta Operator Runbook

> Controlled External Beta — Operator Daily Procedure.
> **PRODUCTION_READY = false** · Live providers remain blocked.
> All outward actions require human approval.

## Daily Checklist

### Before Session
- [ ] Verify `git status --short` is clean
- [ ] Verify `production_ready = false` via `/api/v1/health/readiness/production`
- [ ] Verify beta kill switch is active (`KILL_SWITCH_ALL_EXTERNAL_BETA = true`)
- [ ] Verify live provider gates are still closed
- [ ] Check `/api/v1/health` returns `status: ok`
- [ ] Review backlog of pending approvals

### During Session
- [ ] Review each AI recommendation before acting on it
- [ ] Approve or reject each draft — never auto-send
- [ ] Monitor safe error count — investigate spikes
- [ ] Check rate-limit events — adjust limits if needed
- [ ] Review org-boundary denials — investigate anomalies
- [ ] Watch workflow failures — triage as needed

### End of Session
- [ ] Approve or explicitly reject all pending items
- [ ] Return pending items that need more context
- [ ] Check beta feedback inbox and triage
- [ ] Log session metrics (manual or via dashboard)
- [ ] Verify no unintended live provider calls occurred

## How To Review AI Recommendations

1. Open the recommendation in the UI or via API
2. Read the context and rationale
3. Check the confidence score
4. Decide: **Approve** / **Reject with feedback** / **Request revision**
5. If rejecting, include specific reason to improve model

## How To Approve / Reject

| Action | API Endpoint | Effect |
|--------|-------------|--------|
| Approve | `POST /api/v1/approvals/{id}/approve` | Marks approved; enables downstream action |
| Reject | `POST /api/v1/approvals/{id}/reject` | Rejects with optional feedback |
| Request Revision | `POST /api/v1/approvals/{id}/revise` | Returns item for AI revision |
| Skip | `POST /api/v1/approvals/{id}/skip` | Removes item without action |

## How To Pause a Beta Tester

```bash
# Via API
curl -X POST /api/v1/beta/testers/{tester_id}/pause \
  -H "Authorization: Bearer $API_KEY"

# The tester will immediately be unable to make new requests.
# Existing workflows complete, but no new ones start.
```

## How To Trigger Kill Switch

The global kill switch (`KILL_SWITCH_ALL_EXTERNAL_BETA`) is `true` by default.
To **enable** beta (explicit operator action):

```bash
# Set KILL_SWITCH_ALL_EXTERNAL_BETA=false in .env
# Set BETA_ENABLED=true in .env
# Restart the application
```

To **disable** beta immediately (emergency):

```bash
# Set KILL_SWITCH_ALL_EXTERNAL_BETA=true in .env
# Restart the application
# All beta APIs return safe disabled response
# No new workflows start
# MCP beta tools blocked
# Operator UI shows beta disabled
```

## How To Rollback

See `docs/ROLLBACK_RUNBOOK.md` for full rollback procedures.

Quick rollback:
1. Revert to previous deploy: `git revert HEAD && git push`
2. Verify rollback: `curl /api/v1/health/readiness/beta` shows beta closed
3. Confirm: `production_ready = false`, `kill_switch = true`

## What Metrics To Watch

| Metric | Warning | Critical |
|--------|---------|----------|
| Safe error count | > 5/hour | > 20/hour |
| Rate-limit events | > 10/hour | > 50/hour |
| Org-boundary denials | > 2/hour | > 10/hour |
| Workflow failures | > 2/hour | > 5/hour |
| MCP failures | > 5/hour | > 15/hour |
| Approval backlog | > 10 items | > 25 items |
| Support tickets (high+) | > 2/day | > 5/day |

## What To Do When Safe Errors Spike

1. Check `/api/v1/health/readiness/beta` for any gate changes
2. Check the most recent safe errors for patterns
3. Check if errors correlate with specific beta testers
4. If pattern is found, pause affected testers
5. If widespread, trigger kill switch
6. File bug report with correlation IDs

## What To Do When Org-Boundary Denials Spike

1. Investigate the source requests
2. Check if testers are accessing wrong organizations
3. Check if auth context is misconfigured
4. Pause affected testers temporarily
5. File critical incident if cross-org data leak suspected

## What To Do When Approval Backlog Grows

1. Sort by priority (oldest first)
2. Batch process similar items
3. If backlog > 20 items, allocate dedicated session
4. Consider increasing approval capacity or reducing AI output volume
5. Review if criteria thresholds are too loose

## Emergency Contacts

- **Security incident:** Immediate kill switch + pause all testers
- **Data breach suspicion:** Kill switch + pause all + begin incident response (see `docs/INCIDENT_RESPONSE_RUNBOOK.md`)
- **Live provider accidental call:** Kill switch + verify gate + rotate compromised keys (see `docs/PRODUCTION_SECRETS_RUNBOOK.md`)
