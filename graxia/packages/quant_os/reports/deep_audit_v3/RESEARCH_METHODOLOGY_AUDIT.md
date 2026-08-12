# Phase 17 - Research Methodology Audit

Status: PARTIAL

## 17.1 Hypothesis Log

Finding: A research log exists, but it records only one completed experiment and two pending ideas. It is not enough to reconstruct every historical hypothesis, parameter sweep, or failed trial.

Evidence:
- `RESEARCH_LOG.md:3-8` defines the intended hypothesis/method/result/verdict format.
- `RESEARCH_LOG.md:12-17` records EXP-001 as a failed XAUUSD H1 XGBoost walk-forward: net -$1,225 vs buy-and-hold +$2,888, Sharpe 0.3.
- `RESEARCH_LOG.md:19-27` records EXP-002 and EXP-003 as NOT STARTED.

Verdict: PARTIAL. Methodology discipline exists, but complete project-wide hypothesis count is unverified.

## 17.2 Experiment Registry

Finding: The code has an in-memory experiment registry with snapshot fields and trial budget metadata, but the implementation shown here is not durable by itself.

Evidence:
- `validation/experiment_registry.py:9-23` defines experiment metadata including git commit, strategy hash, parameter hash, dataset manifest IDs, contract snapshot ID, execution model ID, cost scenario ID, risk policy ID, trial number, budget, and seed.
- `validation/experiment_registry.py:37-47` stores experiments in process memory.
- `validation/experiment_registry.py:58-60` checks count against a budget but only for registry entries currently loaded in memory.

Verdict: PARTIAL. Good schema; persistence/enforcement across research sessions not proven in this file.

## 17.3 Multiple-Testing Control

Finding: The current audit cannot derive a complete number of independent hypotheses tested across the whole project. Any reported alpha remains vulnerable to selection bias until the complete trial ledger is reconstructed.

Evidence:
- `RESEARCH_LOG.md:12-17` has one completed experiment with a negative result.
- `validation/experiment_registry.py:20-22` includes `trial_number`, `trial_budget`, and `random_seed`, but no durable append-only storage is visible in the cited implementation.

Verdict: FAIL for complete project-level multiple-testing accounting.

## 17.4 Decision

No confirmed edge should be promoted from research to deployment based on this methodology state. Continue only if future experiments are pre-registered, persisted, and included in a cumulative multiple-testing correction ledger.

