"""Hyperoptable parameters from Freqtrade pattern"""

from __future__ import annotations

import random
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

import optuna

# Global flag for optimization mode
_optimization_mode = False


def set_optimization_mode(enabled: bool):
    global _optimization_mode
    _optimization_mode = enabled


def is_optimizing() -> bool:
    return _optimization_mode


@dataclass
class HyperParam:
    """A parameter that can be optimized by hyperopt"""

    value: Any
    low: Any
    high: Any
    space: str = "buy"
    optimize: bool = True
    step: Any | None = None

    @property
    def current(self):
        """Returns full range during optimization, single value otherwise"""
        if is_optimizing() and self.optimize:
            if self.step is not None:
                return list(range(int(self.low), int(self.high) + 1, int(self.step)))
            return (self.low, self.high)
        return self.value

    def sample(self):
        """Sample a random value from the range"""
        if is_optimizing() and self.optimize:
            if isinstance(self.low, float):
                return random.uniform(self.low, self.high)
            return random.randint(int(self.low), int(self.high))
        return self.value


@dataclass
class IntParameter(HyperParam):
    """Integer parameter for optimization"""

    step: int = 1


@dataclass
class RealParameter(HyperParam):
    """Float parameter for optimization"""

    pass


@dataclass
class CategoricalParameter(HyperParam):
    """Categorical parameter for optimization"""

    categories: list[Any] = None

    def sample(self):
        if is_optimizing() and self.optimize and self.categories:
            return random.choice(self.categories)
        return self.value


# ── Optuna integration (B4) ─────────────────────────────────────────


def apply_trial_params(strategy: Any, trial: optuna.trial.Trial) -> dict[str, Any]:
    """Suggest values from *trial* for every key in ``strategy.hyperparameters()``,
    then apply them via ``strategy.from_hyperparameters()``.

    Returns the flat dict of suggested values for logging/inspection.
    """

    ranges = strategy.hyperparameters()
    suggested: dict[str, Any] = {}
    for name, hp_range in ranges.items():
        dist = hp_range.to_optuna_distribution()
        if "choices" in dist:
            suggested[name] = trial.suggest_categorical(name, dist["choices"])
        else:
            log_flag = dist.get("log", False)
            step = dist.get("step", None)
            suggested[name] = trial.suggest_float(
                name,
                dist["low"],
                dist["high"],
                step=step,
                log=log_flag,
            )
    strategy.from_hyperparameters(suggested)
    return suggested


def create_study_from_strategy(
    strategy: Any,
    objective_fn: Callable[[optuna.trial.Trial], float],
    n_trials: int = 100,
    *,
    direction: str = "minimize",
    study_name: str | None = None,
    sampler: optuna.samplers.BaseSampler | None = None,
) -> optuna.study.Study:
    """Create and run an Optuna study whose search space mirrors
    ``strategy.hyperparameters()``.

    Parameters
    ----------
    strategy:
        A ``Strategy`` subclass instance (or any object exposing
        ``hyperparameters()`` and ``from_hyperparameters()``).
    objective_fn:
        ``f(trial) -> float``.  The function **must** call
        ``apply_trial_params(strategy, trial)`` inside the objective to
        populate each trial's values on *strategy* before evaluating.
    n_trials:
        Number of trials to run (default 100).
    direction:
        ``"minimize"`` or ``"maximize"``.
    study_name:
        Optional human-readable study name.
    sampler:
        Optional custom Optuna sampler.

    Returns
    -------
    optuna.study.Study
        The completed study object.
    """
    study = optuna.create_study(
        direction=direction,
        study_name=study_name,
        sampler=sampler,
    )
    study.optimize(objective_fn, n_trials=n_trials)
    return study
