# Phase 21.5 → Phase 22 Gap Analysis

## What Phase 21.5 Delivered

- Pre-session evidence freeze with 20+ checks ✅
- Tester selection record (AI tester) ✅
- Session notes covering 5 script steps ✅
- Session evidence (15 items) ✅
- Operator decision (CONTINUE_BETA) ✅
- Post-session regression (59/59, compileall, frontend, alembic) ✅
- Closeout report (PASS with caveats) ✅

## What Phase 21.5 Did NOT Cover

| Gap | Impact | Phase 22 Action |
|-----|--------|-----------------|
| No AI tester lab infrastructure | Can't replay or systematize testing | Build synthetic_tester package with personas, tasks, evidence model |
| No structured persona definitions | Roleplay was ad-hoc, not repeatable | Create SyntheticPersona models with 12 personas |
| No task library | Testing was unstructured, not scoped | Create SyntheticTask models with 30 tasks across 11 categories |
| No evidence model | Evidence was doc-only, not code-enforced | Create SyntheticEvidence model with type-driven fields |
| No honesty gate | No automated guard against overclaiming | Create HonestyGate with 12 rules and downgrade table |
| No confidence scoring | No way to measure synthetic vs real confidence | Create ConfidenceScorer with cap logic |
| No runner | Tests were ad-hoc, not orchestrated | Create SyntheticTestRunner |
| No API smoke scripts | No way to verify runtime behavior | Create API smoke scripts for health/readiness/endpoints |
| No MCP synthetic tests | MCP behavior unvalidated at scale | Create test_ai_tester_mcp_synthetic.py |
| No workflow synthetic tests | Workflow execution unvalidated | Create test_beta_workflow_synthetic_run.py |
| No operator simulation | Operator workflow untested | Create test_operator_simulation.py |
| No adversarial tests | Security boundaries untested by AI | Create test_adversarial_beta_safety.py |
| No browser E2E | UI never tested | Create deferred doc or Playwright tests |
| No UX heuristic review | UX not evaluated systematically | Create UX heuristic report |
| No UX metrics framework | No goals-signals-metrics | Create UX metrics GSM doc |
| No defect triage system | No systematic issue classification | Create defect triage guide |
| No roleplay reports | Only one generic session report | Create 8 roleplay reports + evidence audit + fix pack |

## Key Design Decisions for Phase 22

1. **Synthetic tester is code, not docs.** Personas, tasks, evidence, honesty gate, scoring are all Python models with tests. This makes them repeatable, auditable, and evolvable.

2. **Honesty gate is automated.** Rules are enforced at the evidence level, not just documented as guidelines.

3. **Confidence scoring is formula-based.** Scores can be calculated from evidence, not estimated by the AI.

4. **All roleplay reports are labeled SYNTHETIC.** No claim of human validation.

5. **Browser E2E is either executed or explicitly deferred.** No ambiguous claims about UI testing.
