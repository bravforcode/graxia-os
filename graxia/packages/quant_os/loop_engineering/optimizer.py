"""
optimizer.py — OPTIONAL constrained Optuna helper (Spec Part 4).

This module is NOT imported by the loop automatically. It exists only to make the
spec's Part 4 rules enforceable IF tuning is used. All three rules are hard:

  Rule 1: Optuna may only run within ONE pre-registered hypothesis, with the
          parameter range LOCKED in PreRegistration before any result is seen.
          (Enforced: raises if pre_reg.parameter_space_locked is False.)
  Rule 2: The number of Optuna trials is the number of multiple-testing
          comparisons; it must be fed into the DK-test / DSR correction. We
          surface `n_optuna_trials` so the caller corrects the verification.
  Rule 3: The best parameters MUST be re-validated through label-shuffle (not just
          "backtest once says Sharpe improved"). The caller must re-run
          adapters.run_label_shuffle on the best params before calling it a candidate.

optuna is a lazy import — if it is not installed, this raises loudly (no silent
fallback, no fake tuning).
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from .pre_register import PreRegistration
from .validation import ValidationAdapters


def run_constrained_optuna(
    pre_reg: PreRegistration,
    objective: Callable[[dict[str, float]], float],
    adapters: ValidationAdapters,
    n_trials: int | None = None,
) -> dict[str, Any]:
    """Run Optuna ONLY under the locked pre-registration. Returns best params + trial count.

    `objective(params) -> float` is the scalar to MAXIMIZE (e.g. out-of-sample Sharpe).
    The caller is responsible for Rule 2 (correcting verification by n_optuna_trials)
    and Rule 3 (re-running label-shuffle on the returned best_params).
    """
    try:
        import optuna  # lazy: dependency only required if tuning is actually used
    except ImportError as e:  # pragma: no cover - depends on environment
        raise RuntimeError(
            "optuna is not installed. Cannot run tuning. Install optuna or set "
            "optuna_max_trials=0 and skip tuning (Spec Part 4)."
        ) from e

    # Rule 0: pre_reg MUST be loaded from a committed file, not constructed ad-hoc at
    # runtime. source_path is stamped by load_pre_registration(); ad-hoc construction
    # leaves it empty. This prevents an agent from handing the optimizer a freshly-
    # minted PreRegistration with different bounds than what was committed.
    if not pre_reg.source_path:
        raise RuntimeError(
            "PreRegistration was not loaded from a committed file (source_path is empty). "
            "Build via load_pre_registration() from a committed pre-registration document. "
            "Ad-hoc construction at runtime is not allowed."
        )

    # Rule 1: ranges must be locked in pre-registration before any run.
    if not pre_reg.parameter_space_locked:
        raise RuntimeError(
            "Spec Part 4 Rule 1 violated: Optuna param ranges MUST be locked in "
            "PreRegistration (optuna_param_ranges) before any backtest. Refusing to tune."
        )

    n_trials = n_trials or pre_reg.optuna_max_trials
    if n_trials <= 0:
        raise ValueError("n_trials must be > 0 when tuning.")

    ranges = pre_reg.optuna_param_ranges or {}

    def objective_fn(trial):  # type: ignore[no-untyped-def]
        params = {
            name: trial.suggest_float(name, float(lo), float(hi))
            for name, (lo, hi) in ranges.items()
        }
        return float(objective(params))

    study = optuna.create_study(direction="maximize")
    study.optimize(objective_fn, n_trials=n_trials)

    # Rule 2: surface trial count for multiple-testing correction by the caller.
    # Rule 3: caller must re-run adapters.run_label_shuffle on best_params.
    return {
        "best_params": dict(study.best_params),
        "best_value": float(study.best_value),
        "n_optuna_trials": n_trials,
    }
