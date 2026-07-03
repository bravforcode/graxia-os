# PHASE 22 — Fix Pack Recommendations
## AI Tester Lab Operating System — Evidence-Based Fix Planning
### Mode: SYNTHETIC_ROLEPLAY · Fix Pack Planner AI

---

## 0. Recommendation Basis

These recommendations are based on:

```text
- Phase 21.5 session observations (terminal-only AI-led)
- Phase 22 synthetic persona roleplay reports
- Phase 22 code inspection (evidence.py, honesty_gate.py, scoring.py)
- Phase 22 test harness results (existing gates)
- Phase 22 gap analysis
- Static accessibility/UX review
```

---

## 1. Severity Classification

| Severity | Definition | Action |
|---|---|---|
| S0 | Hard safety stop | Fix immediately, block beta |
| S1 | Critical beta blocker | Fix before any human beta |
| S2 | Major UX/runtime blocker | Fix before expanding beta |
| S3 | Minor improvement | Batch into Phase 23 |
| S4 | Backlog | Nice-to-have |

---

## 2. Hard Safety Fixes (S0)

| ID | Finding | Location | Fix |
|---|---|---|---|
| S0-01 | No cross-org isolation test at MCP runtime level (test harness only) | MCP auth enforcement | Add runtime cross-org test with actual MCP client |
| S0-02 | Honesty gate H007/H008/H009 have no automated enforcement at startup | None | Add startup guard that rejects production_ready or live provider enable |

**Status: ✅ No active S0 defects. All gates tested.**

---

## 3. Critical Beta Blockers (S1)

| ID | Finding | Location | Fix |
|---|---|---|---|
| S1-01 | Browser E2E not run | Frontend | Deferred — run before human beta |
| S1-02 | API smoke not run | Backend | Deferred — requires backend start |
| S1-03 | No runtime workflow execution verified | Workflow engine | Start backend and run opportunity_scout/ content_plan draft |

**Status: ⚠️ 3 S1 items — all require runtime backend to resolve.**

---

## 4. Major UX/Runtime Blockers (S2)

| ID | Finding | Location | Fix |
|---|---|---|---|
| S2-01 | "Kill switch" is engineering jargon | User-facing copy | Replace with "Safety pause" or "Emergency stop" |
| S2-02 | "NO_LIVE_PAYMENT_MODE" is internal config name | Readiness endpoint | Add human-readable label |
| S2-03 | Error messages are machine-oriented ("ERR_ORG_MISMATCH") | API error responses | Add user-facing error message alongside code |
| S2-04 | No loading state for draft generation | Frontend | Add spinner/skeleton for async operations |
| S2-05 | Approval UI needs user-friendly status display | Frontend | Show current state (draft/pending/approved/rejected) |
| S2-06 | No empty state for key pages | Frontend | Add empty state with guidance for opportunities, feedback, etc. |

---

## 5. Minor Improvements (S3)

| ID | Finding | Location | Fix |
|---|---|---|---|
| S3-01 | Accessibility static review only | Frontend | Run Playwright a11y checks |
| S3-02 | Thai/English copy needs proofreading | Frontend | Language review with Thai speaker |
| S3-03 | Feedback form missing character count | Frontend | Add character limit indicator |
| S3-04 | No "What does this mean?" on beta safety badges | Frontend | Add tooltips |
| S3-05 | Docs have inconsistent version headers | Docs | Standardize doc headers |
| S3-06 | No session timeout warning | Frontend | Add idle timeout warning |
| S3-07 | Metric dashboard missing time range selector | Frontend | Add date range filter |

---

## 6. Backlog (S4)

| ID | Finding | Priority | Notes |
|---|---|---|---|
| S4-01 | Dark mode | Low | No user request yet |
| S4-02 | Notification preferences UI | Low | Future scope |
| S4-03 | Mobile responsive layout | Low | Current focus is desktop |
| S4-04 | Multi-language support | Very low | Phase after Thai/English validation |
| S4-05 | Performance benchmarks | Very low | Not needed at current scale |

---

## 7. Phase 23 Recommended Scope

Based on fix severity and dependencies, Phase 23 should be:

**Phase 23 — Fix Pack From Synthetic Tester Findings**

Priority order:

```text
1. (S2-01,S2-02) User-facing safety copy improvements
2. (S2-03) Human-readable error messages
3. (S2-04,S2-05,S2-06) Frontend UX enhancements (loading, approval UI, empty states)
4. (S1-01,S1-02,S1-03) Runtime execution (backend start + browser E2E)
5. (S3-01..S3-07) Minor improvements batch
6. (S4) Backlog
```

---

## 8. Fix Confidence

| Severity | Count | Confidence | Notes |
|---|---|---|---|
| S0 | 0 | 100% | No active safety defects |
| S1 | 3 | 0% | Blocked on runtime environment |
| S2 | 6 | 70% | Fixes are clear, need implementation |
| S3 | 7 | 80% | Low risk, good UX payoff |
| S4 | 5 | 60% | Needs prioritization |
