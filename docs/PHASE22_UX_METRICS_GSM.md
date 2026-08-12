# Phase 22 — UX Metrics: Goals → Signals → Metrics (GSM)

**Honesty Gate Note:** These metrics are synthetic estimates from AI roleplay.
Only real humans can validate human UX metrics. All values are labeled SYNTHETIC.

## G1: User Understands Safety Boundaries

| Component | Description |
|-----------|-------------|
| **Signal** | Can explain safety boundaries in own words |
| **Metric** | safety_clarity_score (1-5) |
| **Synthetic Value** | 4/5 (based on STATIC_REVIEW of policy docs) |
| **Measurement** | Roleplay: ask persona to explain "what is NOT allowed" |

## G2: User Reaches First Useful Draft

| Component | Description |
|-----------|-------------|
| **Signal** | Time to first useful output |
| **Metric** | time_to_first_value_minutes |
| **Synthetic Value** | ~5-10 min estimated (not measured — no runtime) |
| **Measurement** | Requires API_RUNTIME or BROWSER_E2E mode |

## G3: Operator Can Decide Do/Skip/Delay Confidently

| Component | Description |
|-----------|-------------|
| **Signal** | Approval confusion count |
| **Metric** | operator_intervention_count |
| **Synthetic Value** | 0-2 interventions estimated per session |
| **Measurement** | Requires operator simulation or real session |

## G4: User Trusts No Payment/Send/Publish

| Component | Description |
|-----------|-------------|
| **Signal** | User reports trust in safety |
| **Metric** | trust_rating_1_5 |
| **Synthetic Value** | 5/5 (system is locked down — no risk) |
| **Measurement** | Roleplay: ask persona "do you trust this system?" |

## G5: Feedback Becomes Actionable Fixes

| Component | Description |
|-----------|-------------|
| **Signal** | Feedback leads to concrete improvements |
| **Metric** | actionable_feedback_ratio |
| **Synthetic Value** | N/A (Phase 22 is roleplay, no real fix cycle) |
| **Measurement** | Requires real fix-pack iteration |

## Aggregated Synthetic UX Metrics

| Metric | Synthetic Value | Notes |
|--------|----------------|-------|
| task_success_rate | ~85% | Estimated from persona task completion |
| time_to_first_value_minutes | ~5-10 | Not runtime-measured |
| operator_intervention_count | 0-2 | Per session estimate |
| approval_confusion_count | 0-1 | Safety copy is clear |
| trust_rating_1_5 | 5 | All safety gates locked |
| usefulness_rating_1_5 | 3-4 | Depends on persona/use case |
| critical_safety_issue_count | 0 | No issues found (Phase 22) |
| actionable_feedback_ratio | N/A | No real feedback cycle yet |

## Limitations

- All metrics are synthetic estimates from AI roleplay
- No real human UX data was collected
- time_to_first_value requires runtime measurement
- actionable_feedback_ratio requires real feedback
- trust_rating requires real human session
