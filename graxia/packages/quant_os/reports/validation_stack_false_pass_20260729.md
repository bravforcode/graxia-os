# Validation Stack False-Pass Audit — 2026-07-29 (P1-6)

**Severity: HIGH — governance-integrity bug, confirmed already triggered historically, not just theoretical.**

## 1. `validation/pipeline/gates.py` + `runner.py` — exceptions silently remove gates from the aggregate

`GateEngine.evaluate()` (gates.py:74-95) only evaluates a workstream's gates if its result is not `None`:
```python
if wfa_result: gates.extend(self._eval_wfa(wfa_result))
if mc_result: gates.extend(self._eval_mc(mc_result))
if dsr_result: gates.append(self._eval_dsr(dsr_result))
if pbo_result: gates.append(self._eval_pbo(pbo_result))
...
if not gates: overall = GateStatus.SKIP
elif any(FAIL): overall = FAIL
elif any(WARN): overall = WARN
else: overall = GateStatus.PASS
```
`runner.py`'s `_run_*` methods each catch broad exceptions and return `success=False` (lines ~242-243, 286-287, 330-331, 395-396, 442-443, 507-508) which `_get_data()` turns into `None`. A workstream that *errors* therefore behaves identically to a workstream that was *never run* — its check is silently dropped from the aggregate rather than counted as FAIL or UNKNOWN.

**Concrete repro:** if `dsr`, `pbo`, `stress`, `bootstrap` all raise (missing import, a `ZeroDivisionError` in `_run_pbo`, dataset too short — any of these) while `wfa`/`monte_carlo` succeed and pass, `gates` contains only the WFA+MC results → `overall = PASS`, even though 4 of 6 checks never actually ran.

**This is live, not dead code:** `scripts/ci_validation_gate.py:79-86` exits 0 (CI green) whenever `overall.value == "PASS"`. A partial pipeline crash can produce a green CI gate.

**Already happened, confirmed on a real trial:** Trial #2012 (`TSM-PORTFOLIO-8ASSET-MULTILOOKBACK`, `research/trial_ledger_b.json`) — `scripts/tsm_portfolio.py:348` computed `n_trials = len(LOOKBACKS) * 2` (= 4, scoped far too narrowly vs. the project's true cumulative trial count of 1050+) fed into `deflated_sharpe_test()`, producing `significant_5pct: true, p_deflated: 0.0` — a real false-positive significance claim. Caught later by jackknife (in an earlier session), final status REJECTED. Trials 2009-2011 similarly produced false "GO" verdicts (`dk_t=+7.93`/`+4.95`) from a symbol-threading bug defaulting non-XAUUSD contract specs to gold-shaped values, also later reversed.

**Current state of the ledgers:** no entry in `trial_ledger.json`/`_b`/`_c` or `hypothesis_registry_b.json` is currently recorded as PASS/PASS_FEASIBILITY — everything is REJECTED/UNTESTED. The false-pass evidence found is at the script/computation layer (verdicts that were WRONG when first produced), not a currently-mislabeled ledger entry that's still standing.

## 2. `validation/myfxbook_screener.py` — missing data produces PASS, not "insufficient data"

Every red-flag rule (R1-R9) is gated behind `if stats.<field> is not None`. Verdict is computed only from triggered flags:
```python
max_sev = max((_SEV_RANK[f.severity] for f in flags), default=0)
if max_sev >= 3: FAIL
elif max_sev >= 1: REVIEW
else: verdict = Verdict.PASS
```
**Concrete repro:** `MyfxbookStats(source_url="x", fetched_at="2026-07-28")` with every other field (`drawdown`, `trades`, `sharpe`, `leverage`, etc.) left `None` satisfies the provenance check and produces `verdict=PASS, note="no red flags found"` — despite assessing zero actual data.

## 3. `validation/threshold_evaluator.py` — vacuous truth on empty result list

`all_passed()` returns `all(r.passed for r in self._results)`, which is `True` for an empty list. If `evaluate_all()` is called with `metrics`/`gates` dicts sharing no matching keys, `self._results` stays empty and `all_passed()` returns `True`. **Lower severity — confirmed dead code:** grep shows no importer of this class outside its own tests; not currently wired into a live verdict path.

## Recommendation

This is a design decision, not a one-line fix: when a workstream errors, should the gate become FAIL (safe-by-default, but may cause false alarms on legitimate skips/disabled features) or a new explicit `UNKNOWN`/`ERRORED` status that blocks the overall verdict from being PASS without a human looking at it? That distinction needs a decision before touching `gates.py`/`runner.py`, so this was NOT patched this session — flagging as the top-priority follow-up given how much of this project's trustworthiness rests on validation results being real.
