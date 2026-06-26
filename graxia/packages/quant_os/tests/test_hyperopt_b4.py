"""Tests for B4: Hyperparameter helpers and Optuna integration."""

from __future__ import annotations

import optuna

from graxia.packages.quant_os.core.hyperopt import apply_trial_params, create_study_from_strategy
from graxia.packages.quant_os.strategies.base import HyperparameterRange, Strategy

# ── Fixture: a minimal Strategy subclass with hyperparameters ────────


class DummyStrategy(Strategy):
    """Minimal strategy that exposes two hyperparameters."""

    ema_fast: int = 10
    atr_mult: float = 1.5

    def hyperparameters(self):
        return {
            "ema_fast": HyperparameterRange("ema_fast", 5, 20, step=1),
            "atr_mult": HyperparameterRange("atr_mult", 1.0, 3.0, step=0.1),
        }

    def from_hyperparameters(self, params):
        super().from_hyperparameters(params)

    def generate_signal(self, symbol, ohlcv_data, indicators=None, regime=None, **kwargs):
        return None

    def required_features(self):
        return []


class EmptyStrategy(Strategy):
    """Strategy with no hyperparameters."""

    def hyperparameters(self):
        return {}

    def from_hyperparameters(self, params):
        super().from_hyperparameters(params)

    def generate_signal(self, symbol, ohlcv_data, indicators=None, regime=None, **kwargs):
        return None

    def required_features(self):
        return []


# ── Tests ─────────────────────────────────────────────────────────────


def test_apply_trial_params_populates_strategy():
    strategy = DummyStrategy()
    study = optuna.create_study()
    trial = study.ask()

    suggested = apply_trial_params(strategy, trial)

    assert "ema_fast" in suggested
    assert "atr_mult" in suggested
    # values should be applied to the strategy instance
    assert strategy.ema_fast == suggested["ema_fast"]
    assert strategy.atr_mult == suggested["atr_mult"]


def test_apply_trial_params_empty_hyperparameters():
    strategy = EmptyStrategy()
    study = optuna.create_study()
    trial = study.ask()

    suggested = apply_trial_params(strategy, trial)
    assert suggested == {}


def test_create_study_from_strategy_runs():
    strategy = DummyStrategy()

    def objective(trial):
        apply_trial_params(strategy, trial)
        return abs(strategy.ema_fast - 12) + abs(strategy.atr_mult - 2.0)

    study = create_study_from_strategy(strategy, objective, n_trials=10, study_name="b4_test")

    assert study is not None
    assert len(study.trials) == 10
    # best params should exist
    assert "ema_fast" in study.best_params
    assert "atr_mult" in study.best_params


def test_create_study_from_strategy_empty_params():
    strategy = EmptyStrategy()
    call_count = 0

    def objective(trial):
        nonlocal call_count
        apply_trial_params(strategy, trial)
        call_count += 1
        return 0.0

    study = create_study_from_strategy(strategy, objective, n_trials=5, direction="minimize")
    assert len(study.trials) == 5
    assert call_count == 5


def test_apply_trial_params_categorical():
    """Strategy with a categorical parameter."""

    class CatStrategy(Strategy):
        mode: str = "fast"

        def hyperparameters(self):
            return {
                "mode": HyperparameterRange("mode", 0, 0, choices=["fast", "slow", "adaptive"]),
            }

        def from_hyperparameters(self, params):
            super().from_hyperparameters(params)

        def generate_signal(self, symbol, ohlcv_data, indicators=None, regime=None, **kwargs):
            return None

        def required_features(self):
            return []

    strategy = CatStrategy()
    study = optuna.create_study()
    trial = study.ask()

    suggested = apply_trial_params(strategy, trial)
    assert suggested["mode"] in ["fast", "slow", "adaptive"]
    assert strategy.mode == suggested["mode"]


def test_create_study_optimizes_direction():
    """Verify direction=maximize picks the highest value."""
    strategy = DummyStrategy()

    def objective(trial):
        apply_trial_params(strategy, trial)
        return strategy.ema_fast  # maximize ema_fast

    study = create_study_from_strategy(strategy, objective, n_trials=20, direction="maximize")
    # best should be near the high end (20)
    assert study.best_params["ema_fast"] >= 15
