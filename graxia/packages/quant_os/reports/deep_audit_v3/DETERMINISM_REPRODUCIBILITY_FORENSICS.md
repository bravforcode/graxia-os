# Phase 19 - Determinism and Reproducibility Forensics

Status: PARTIAL

## 19.1 Reproducibility Harness

Finding: A dual-run reproducibility script exists, but the cited implementation appears path-fragile when run from the package root because it invokes `graxia/packages/quant_os/scripts/run_release_truth.py` while setting `cwd=root`.

Evidence:
- `scripts/verify_reproducibility.py:9-16` runs `run_release_truth.py` in a subprocess and returns stderr on failure.
- `scripts/verify_reproducibility.py:11-13` hardcodes `graxia/packages/quant_os/scripts/run_release_truth.py` relative to `cwd=root`.
- `scripts/verify_reproducibility.py:34-54` compares git commit, full bundle hash, and dependency lock hash.
- `scripts/verify_reproducibility.py:57-83` performs two runs and returns pass/fail.

Verdict: PARTIAL. Reproducibility concept exists; exact runnable invocation must be verified from monorepo root.

## 19.2 Random Seeds and Trial Identity

Finding: Experiment records include a default random seed and fingerprint logic.

Evidence:
- `validation/experiment_registry.py:20-23` defines trial number, trial budget, and default `random_seed = 42`.
- `validation/experiment_registry.py:25-34` fingerprints experiment ID, strategy snapshot hash, parameter snapshot hash, dataset manifest IDs, trial number, and random seed.

Verdict: PARTIAL. Seed metadata exists; full deterministic training/backtest replay was not proven.

## 19.3 Current Environment

Observed during this audit:
- Python: 3.12.10.
- OS: Windows 11, build family `Windows-11-10.0.26200-SP0`.

## 19.4 Required Next Proof

Run from the monorepo root and archive artifacts:

```powershell
python graxia/packages/quant_os/scripts/verify_reproducibility.py .
```

If it fails due path handling, fix the script path first, then rerun two clean release captures.

