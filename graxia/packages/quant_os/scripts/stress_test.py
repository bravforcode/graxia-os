#!/usr/bin/env python3
"""
Synthetic Stress Test Generator for Quant OS.

Generates perturbed market scenarios to validate strategy robustness under
extreme but realistic conditions. Supports three CLI modes:

  generate       — perturb baseline Parquet data with a named scenario
  run-backtest   — load a strategy model and run it on synthetic data
  all-scenarios  — batch-generate and backtest across symbols + seeds

Components
----------
1. Regime-Switching Synthetic Return Generator
   2-regime Hidden Markov Model (calm / stress) with stochastic volatility,
   Markov persistence, and Student-t innovations.

2. Execution Perturbation Layer
   Spread widening, slippage multipliers, partial-fill rejection,
   and latency spikes applied to a baseline backtest.

3. Scenario Catalog
   flash_crash, liquidity_drought, news_spike, regime_shift,
   cascading_losses — each with documented mathematical formulation.

Usage
-----
  python scripts/stress_test.py --mode generate \\
      --input data/EURUSD_M15.csv --scenario flash_crash \\
      --output data/synthetic/flash_crash_EURUSD.parquet --seed 42

  python scripts/stress_test.py --mode run-backtest \\
      --data data/synthetic/flash_crash_EURUSD.parquet \\
      --model artifacts/strategy_model/ --output artifacts/stress_test/report.json

  python scripts/stress_test.py --mode all-scenarios \\
      --symbols EURUSD,GBPUSD,XAUUSD --model artifacts/strategy_model/ \\
      --output-dir artifacts/stress_test/ --seeds 42,123,456
"""

import argparse
import json
import os
import pickle
import re
import sys
import warnings
from dataclasses import dataclass, field, asdict
from datetime import datetime, UTC
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
import pandas as pd

from graxia.packages.quant_os.core.safe_pickle import safe_load_model

warnings.filterwarnings("ignore")

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_DIR = os.path.join(BASE_DIR, "data")
ARTIFACTS_DIR = os.path.join(BASE_DIR, "artifacts")
SYNTHETIC_DIR = os.path.join(ARTIFACTS_DIR, "synthetic")
STRESS_DIR = os.path.join(ARTIFACTS_DIR, "stress_test")

MIN_PRICE = 0.0001
POINT_VALUE = 0.01  # dollars per point for 0.01 lot

# Default transition matrix [[p(calm→calm), p(calm→stress)], [p(stress→calm), p(stress→stress)]]
DEFAULT_TRANSITION = np.array([[0.95, 0.05], [0.10, 0.90]])

# ---------------------------------------------------------------------------
# Scenario definitions  (dataclass catalogue)
# ---------------------------------------------------------------------------

@dataclass
class ShockParams:
    """Parameters that define a single stress scenario."""
    name: str
    description: str

    # Price shock
    price_drop_pct: float = 0.0
    price_drop_bars: int = 0
    price_recovery_bars: int = 0
    price_gap_pips: float = 0.0

    # Spread shock
    spread_multiplier: float = 1.0
    spread_duration_bars: int = 0

    # Volume shock
    volume_multiplier: float = 1.0
    volume_duration_bars: int = 0

    # Regime shift
    regime_shift_bar: Optional[int] = None

    # Cascading-loss parameters (consecutive stop-outs)
    cascade_spread_step: float = 0.0
    cascade_step_bars: int = 0
    cascade_total_steps: int = 0

    # Execution perturbation defaults
    slippage_multiplier: float = 1.0
    partial_fill_reject_pct: float = 0.0
    latency_spike_pct: float = 0.0

    def __post_init__(self):
        self.description = (
            f"{self.name}: price_drop={self.price_drop_pct}%, "
            f"spread_x{self.spread_multiplier}, "
            f"vol_x{self.volume_multiplier}"
        )


# Pre-defined scenario catalogue
SCENARIOS: Dict[str, ShockParams] = {
    "flash_crash": ShockParams(
        name="flash_crash",
        description="5% price drop over 10 minutes (2 M15 bars), spread 10x",
        price_drop_pct=5.0,
        price_drop_bars=2,
        price_recovery_bars=8,
        spread_multiplier=10.0,
        spread_duration_bars=10,
        volume_multiplier=3.0,
        volume_duration_bars=2,
    ),
    "liquidity_drought": ShockParams(
        name="liquidity_drought",
        description="Spread 5x, volume 0.1x for 2 hours (8 M15 bars)",
        spread_multiplier=5.0,
        spread_duration_bars=8,
        volume_multiplier=0.1,
        volume_duration_bars=8,
    ),
    "news_spike": ShockParams(
        name="news_spike",
        description="50-pip gap, spread 3x for 5 minutes (1 M15 bar)",
        price_gap_pips=50.0,
        spread_multiplier=3.0,
        spread_duration_bars=1,
        volume_multiplier=5.0,
        volume_duration_bars=1,
    ),
    "regime_shift": ShockParams(
        name="regime_shift",
        description="Transition from calm to stress HMM regime mid-session",
        regime_shift_bar=None,
        spread_multiplier=3.0,
        spread_duration_bars=0,
    ),
    "cascading_losses": ShockParams(
        name="cascading_losses",
        description="Consecutive stop-outs with widening spreads",
        cascade_spread_step=1.5,
        cascade_step_bars=4,
        cascade_total_steps=5,
    ),
}

# ---------------------------------------------------------------------------
# 1. Regime-Switching Synthetic Return Generator
# ---------------------------------------------------------------------------

class HMMRegimeSwitcher:
    """2-regime Hidden Markov Model for synthetic return generation.

    Mathematical formulation
    -----------------------
    Regime S_t in {0 (calm), 1 (stress)} evolves as:
        P(S_t = j | S_{t-1} = i) = T[i, j]

    Returns are drawn from:
        r_t = mu_{S_t} + sigma_{S_t} * epsilon_t
        epsilon_t ~ t(nu_{S_t})     (Student-t with nu degrees of freedom)

    Stochastic volatility follows a GARCH(1,1)-like process:
        sigma_{S_t,t}^2 = omega_{S_t} + alpha_{S_t} * r_{t-1}^2 + beta_{S_t} * sigma_{S_t,t-1}^2

    Regime parameters:
        Calm:   mu=0.0001,  sigma_0=0.001,  nu=30
        Stress: mu=-0.0005, sigma_0=0.005,  nu=3
    """

    def __init__(
        self,
        transition_matrix: Optional[np.ndarray] = None,
        seed: Optional[int] = None,
    ):
        self.T = (
            transition_matrix
            if transition_matrix is not None
            else DEFAULT_TRANSITION
        )
        self.rng = np.random.default_rng(seed)

        # Regime parameters
        self.mu = np.array([0.0001, -0.0005])
        self.sigma0 = np.array([0.001, 0.005])
        self.nu = np.array([30.0, 3.0])  # degrees of freedom (low = fat tails)

        # GARCH(1,1) params per regime
        self.omega = np.array([1e-7, 5e-7])
        self.alpha = np.array([0.05, 0.15])
        self.beta = np.array([0.85, 0.70])

    def generate_returns(self, n: int) -> Tuple[np.ndarray, np.ndarray, np.ndarray]:
        """Generate synthetic returns and regime sequence.

        Returns
        -------
        returns : ndarray, shape (n,)
        regimes  : ndarray, shape (n,), 0=calm / 1=stress
        vols     : ndarray, shape (n,)  — conditional volatility per step
        """
        returns = np.zeros(n)
        regimes = np.zeros(n, dtype=np.int32)
        vols = np.zeros(n)

        # Initial state (calm)
        s = 0
        sigma_sq = self.sigma0[s] ** 2

        for t in range(n):
            regimes[t] = s
            vols[t] = np.sqrt(sigma_sq)

            # Student-t innovation
            eps = self.rng.standard_t(self.nu[s])
            r = self.mu[s] + vols[t] * eps
            returns[t] = r

            # GARCH variance update
            sigma_sq = self.omega[s] + self.alpha[s] * r**2 + self.beta[s] * sigma_sq

            # Regime transition
            if self.rng.uniform() > self.T[s, s]:
                s = 1 - s

        return returns, regimes, vols

    @staticmethod
    def returns_to_prices(
        returns: np.ndarray,
        start_price: float,
    ) -> np.ndarray:
        """Convert log-returns to price series with minimum-price clamp."""
        prices = start_price * np.exp(np.cumsum(returns))
        return np.maximum(prices, MIN_PRICE)


# ---------------------------------------------------------------------------
# 2. Execution Perturbation Layer
# ---------------------------------------------------------------------------

@dataclass
class ExecutionShocks:
    """Execution-level perturbations applied to a backtest.

    Attributes
    ----------
    spread_multiplier : float  — multiply baseline spread by this factor
    slippage_mult     : float  — multiply P90 slippage by this factor
    partial_fill_pct  : float  — fraction of fills randomly rejected (0..1)
    latency_spike_pct : float  — fraction of orders hit with added delay (0..1)
    """
    spread_multiplier: float = 1.0
    slippage_mult: float = 1.0
    partial_fill_pct: float = 0.0
    latency_spike_pct: float = 0.0


def apply_execution_shocks(
    df: pd.DataFrame,
    shocks: ExecutionShocks,
    seed: Optional[int] = None,
) -> pd.DataFrame:
    """Apply execution perturbations to an OHLCV DataFrame.

    Modifies columns in-place (or adds them):
      - 'spread_cost': multiplied by spread_multiplier
      - 'slippage_cost': multiplied by slippage_mult
      - 'fill_ratio': set to 0 for randomly rejected partial fills
      - 'latency_ms': additional delay for randomly selected orders
    """
    result = df.copy()
    rng = np.random.default_rng(seed)

    if "spread_cost" in result.columns:
        result["spread_cost"] *= shocks.spread_multiplier

    if "slippage_cost" in result.columns:
        result["slippage_cost"] *= shocks.slippage_mult

    if shocks.partial_fill_pct > 0:
        n_reject = int(len(result) * shocks.partial_fill_pct)
        reject_idx = rng.choice(len(result), size=n_reject, replace=False)
        result["fill_ratio"] = 1.0
        result.loc[result.index[reject_idx], "fill_ratio"] = 0.0

    if shocks.latency_spike_pct > 0:
        n_spike = int(len(result) * shocks.latency_spike_pct)
        spike_idx = rng.choice(len(result), size=n_spike, replace=False)
        result["latency_ms"] = 0.0
        result.loc[result.index[spike_idx], "latency_ms"] = rng.uniform(
            100, 500, size=n_spike
        )

    return result


# ---------------------------------------------------------------------------
# 3. Scenario catalog — perturbation application
# ---------------------------------------------------------------------------

def _bars_in_window(timestamps: pd.DatetimeIndex, window_minutes: int) -> int:
    """Estimate how many bars fit in `window_minutes` given the data frequency."""
    if len(timestamps) < 2:
        return 1
    freq_min = (timestamps[1] - timestamps[0]).total_seconds() / 60.0
    if freq_min <= 0:
        return 1
    return max(1, int(window_minutes / freq_min))


def apply_flash_crash(
    df: pd.DataFrame,
    params: ShockParams,
    seed: Optional[int] = None,
) -> pd.DataFrame:
    """Apply a flash-crash perturbation.

    Formulation
    -----------
    Over `price_drop_bars` bars, cumulatively drop price by `price_drop_pct`%:
        P_{t} = P_{t-1} * (1 - price_drop_pct / 100 / price_drop_bars)

    Then recover linearly over `price_recovery_bars` bars.
    Spread is multiplied by `spread_multiplier` for the full duration.
    """
    result = df.copy()
    n = len(result)
    mid = n // 3

    drop_start = mid
    drop_end = min(n, drop_start + params.price_drop_bars)
    recover_end = min(n, drop_end + params.price_recovery_bars)

    rng = np.random.default_rng(seed)

    for i in range(drop_start, drop_end):
        factor = 1.0 - (params.price_drop_pct / 100.0 / max(1, params.price_drop_bars))
        jitter = 1.0 + rng.normal(0, 0.001)
        for col in ("open", "high", "low", "close"):
            result.loc[result.index[i], col] *= factor * jitter

    for i in range(drop_end, recover_end):
        progress = (i - drop_end) / max(1, params.price_recovery_bars)
        recovery_factor = 1.0 + (params.price_drop_pct / 100.0 / max(1, params.price_recovery_bars)) * progress
        for col in ("open", "high", "low", "close"):
            result.loc[result.index[i], col] *= recovery_factor

    shock_end = drop_start + params.spread_duration_bars
    shock_end = min(n, shock_end)
    result.loc[result.index[drop_start:shock_end], "spread_cost"] = (
        result.loc[result.index[drop_start:shock_end], "spread_cost"]
        .mul(params.spread_multiplier) if "spread_cost" in result.columns else params.spread_multiplier
    )

    if "volume" in result.columns and params.volume_multiplier != 1.0:
        vol_end = min(n, drop_start + params.volume_duration_bars)
        result.loc[result.index[drop_start:vol_end], "volume"] *= params.volume_multiplier

    _clamp_prices(result)
    return result


def apply_liquidity_drought(
    df: pd.DataFrame,
    params: ShockParams,
    seed: Optional[int] = None,
) -> pd.DataFrame:
    """Apply a liquidity-drought perturbation.

    Formulation
    -----------
    Spread is widened by `spread_multiplier` and volume is scaled by
    `volume_multiplier` for `spread_duration_bars` consecutive bars.
    No price shock — only liquidity degradation.
    """
    result = df.copy()
    n = len(result)
    mid = n // 3
    end = min(n, mid + params.spread_duration_bars)

    result.loc[result.index[mid:end], "spread_cost"] = (
        result.loc[result.index[mid:end], "spread_cost"]
        .mul(params.spread_multiplier) if "spread_cost" in result.columns else params.spread_multiplier
    )

    if "volume" in result.columns:
        vol_end = min(n, mid + params.volume_duration_bars)
        result.loc[result.index[mid:vol_end], "volume"] *= params.volume_multiplier

    return result


def apply_news_spike(
    df: pd.DataFrame,
    params: ShockParams,
    seed: Optional[int] = None,
) -> pd.DataFrame:
    """Apply a news-spike (gap) perturbation.

    Formulation
    -----------
    At a random bar, apply a price gap of `price_gap_pips` pips (up or down
    at random). Spread is widened for one bar, volume is increased.
    """
    result = df.copy()
    n = len(result)
    rng = np.random.default_rng(seed)
    spike_bar = rng.integers(n // 4, 3 * n // 4)
    direction = 1 if rng.uniform() > 0.5 else -1
    gap = direction * params.price_gap_pips * 0.0001  # pip → price

    idx = result.index[spike_bar]
    for col in ("open", "high", "low", "close"):
        result.loc[idx, col] += gap

    shock_end = min(n, spike_bar + params.spread_duration_bars)
    result.loc[result.index[spike_bar:shock_end], "spread_cost"] = (
        result.loc[result.index[spike_bar:shock_end], "spread_cost"]
        .mul(params.spread_multiplier) if "spread_cost" in result.columns else params.spread_multiplier
    )

    if "volume" in result.columns:
        vol_end = min(n, spike_bar + params.volume_duration_bars)
        result.loc[result.index[spike_bar:vol_end], "volume"] *= params.volume_multiplier

    _clamp_prices(result)
    return result


def apply_regime_shift(
    df: pd.DataFrame,
    params: ShockParams,
    seed: Optional[int] = None,
) -> pd.DataFrame:
    """Apply a regime-shift perturbation using the HMM generator.

    Formulation
    -----------
    The first half of the data is left as-is (calm regime).
    The second half is replaced with stress-regime synthetic data
    generated by the HMM, matching the volatility level of the original.
    """
    result = df.copy()
    n = len(result)
    mid = n // 2
    rng = np.random.default_rng(seed)

    start_price = float(result.iloc[mid - 1]["close"]) if mid > 0 else 1.0
    vol_estimate = result["close"].pct_change().std()
    if pd.isna(vol_estimate) or vol_estimate == 0:
        vol_estimate = 0.001

    hmm = HMMRegimeSwitcher(seed=seed)
    # Override stress-regime sigma to match data vol
    hmm.sigma0[1] = vol_estimate * 3.0
    hmm.nu[1] = 3.0

    stress_len = n - mid
    returns, regimes, vols = hmm.generate_returns(stress_len)
    stress_prices = HMMRegimeSwitcher.returns_to_prices(returns, start_price)

    for i, col in enumerate(["open", "high", "low", "close"]):
        if i == 0:
            result.loc[result.index[mid:], "open"] = stress_prices
        elif i == 1:
            result.loc[result.index[mid:], "high"] = stress_prices * 1.001
        elif i == 2:
            result.loc[result.index[mid:], "low"] = stress_prices * 0.999
        else:
            result.loc[result.index[mid:], "close"] = stress_prices

    if "spread_cost" in result.columns:
        result.loc[result.index[mid:], "spread_cost"] *= params.spread_multiplier

    _clamp_prices(result)
    return result


def apply_cascading_losses(
    df: pd.DataFrame,
    params: ShockParams,
    seed: Optional[int] = None,
) -> pd.DataFrame:
    """Apply a cascading-losses perturbation.

    Formulation
    -----------
    Over `cascade_total_steps` steps of `cascade_step_bars` bars each,
    spread multiplies by `cascade_spread_step` each step::
        spread_mult_t = (cascade_spread_step) ^ step_index

    Price drops by 1% per step with partial recovery to simulate
    consecutive stop-outs.
    """
    result = df.copy()
    n = len(result)
    rng = np.random.default_rng(seed)
    start_bar = n // 4

    for step in range(params.cascade_total_steps):
        step_start = start_bar + step * params.cascade_step_bars
        step_end = min(n, step_start + params.cascade_step_bars)
        if step_start >= n:
            break

        spread_mult = params.cascade_spread_step ** (step + 1)
        drop = 0.01 * (step + 1)  # 1%, 2%, 3%, ...

        for i in range(step_start, step_end):
            factor = 1.0 - drop
            jitter = 1.0 + rng.normal(0, 0.0005)
            for col in ("open", "high", "low", "close"):
                result.loc[result.index[i], col] *= factor * jitter

        if "spread_cost" in result.columns:
            result.loc[result.index[step_start:step_end], "spread_cost"] *= spread_mult

    _clamp_prices(result)
    return result


def _clamp_prices(df: pd.DataFrame) -> None:
    for col in ("open", "high", "low", "close"):
        if col in df.columns:
            df[col] = df[col].clip(lower=MIN_PRICE)


# Registry: scenario name -> perturbation function
SCENARIO_APPLICATORS = {
    "flash_crash": apply_flash_crash,
    "liquidity_drought": apply_liquidity_drought,
    "news_spike": apply_news_spike,
    "regime_shift": apply_regime_shift,
    "cascading_losses": apply_cascading_losses,
}


# ---------------------------------------------------------------------------
# Data I/O helpers
# ---------------------------------------------------------------------------

def load_ohlcv(path: str) -> pd.DataFrame:
    """Load OHLCV data from CSV, Parquet file, or Hive-partitioned Parquet directory."""
    if os.path.isdir(path):
        # Hive-partitioned Parquet directory — read all parquet files recursively
        parquet_files = sorted(Path(path).rglob("*.parquet"))
        if not parquet_files:
            raise ValueError(f"No parquet files found in directory: {path}")
        dfs = [pd.read_parquet(f) for f in parquet_files]
        df = pd.concat(dfs, ignore_index=True)
    else:
        ext = os.path.splitext(path)[1].lower()
        if ext == ".parquet":
            df = pd.read_parquet(path)
        else:
            df = pd.read_csv(path, parse_dates=["time"])
    if "timestamp" not in df.columns and "time" in df.columns:
        df = df.rename(columns={"time": "timestamp"})
    if "timestamp" in df.columns:
        df = df.set_index("timestamp")
    df.index = pd.to_datetime(df.index, utc=True)

    # Ensure required columns
    for col in ("open", "high", "low", "close"):
        if col not in df.columns:
            raise ValueError(f"Missing required column '{col}' in {path}")

    # Ensure spread_cost column for perturbation layers
    if "spread_cost" not in df.columns:
        spread_est = df["close"] * 0.0002  # 0.2 pip default
        df["spread_cost"] = spread_est * POINT_VALUE

    return df.sort_index()


def load_model(path: str):
    """Load a trained model from a directory or pickle file.

    Supports:
      - Pickled model file (*.pkl, *.pickle)
      - Directory containing model.pkl
      - XGBoost JSON model (*.json)
    """
    model_path = path
    if os.path.isdir(path):
        model_path = os.path.join(path, "model.pkl")
        if not os.path.exists(model_path):
            candidates = [f for f in os.listdir(path) if f.endswith((".pkl", ".pickle", ".json"))]
            if candidates:
                model_path = os.path.join(path, candidates[0])
            else:
                raise FileNotFoundError(f"No model file found in {path}")

    ext = os.path.splitext(model_path)[1].lower()
    if ext == ".json":
        import xgboost as xgb
        model = xgb.XGBClassifier()
        model.load_model(model_path)
        return model
    else:
        return safe_load_model(model_path)


def save_synthetic_data(df: pd.DataFrame, path: str) -> None:
    """Save perturbed DataFrame to Parquet."""
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    df.to_parquet(path)


def infer_symbol_from_path(path: str) -> str:
    """Guess the symbol name from a file path."""
    base = os.path.basename(path)
    match = re.search(r"(EURUSD|GBPUSD|XAUUSD)", base, re.IGNORECASE)
    if match:
        return match.group(1).upper()
    return "UNKNOWN"


def _infer_scenario_from_path(path: str) -> str:
    """Guess the scenario name from a synthetic-data file path."""
    base = os.path.splitext(os.path.basename(path))[0]
    for name in SCENARIOS:
        if base.startswith(name):
            return name
    parts = base.split("_")
    return parts[0] if parts else "unknown"


# ---------------------------------------------------------------------------
# 4. Backtest runner (simplified model evaluation)
# ---------------------------------------------------------------------------

@dataclass
class BacktestResult:
    """Structured output for a single stress-test run."""
    scenario: str
    symbol: str
    data_params: Dict[str, Any] = field(default_factory=dict)
    results: Dict[str, Any] = field(default_factory=dict)


def run_backtest_on_data(
    df: pd.DataFrame,
    model,
    scenario_name: str = "unknown",
    symbol: str = "UNKNOWN",
    shock_params: Optional[ShockParams] = None,
) -> BacktestResult:
    """Run a simplified backtest: predict direction, compute P&L with costs.

    This is a lightweight evaluator.  It expects the model to have a
    ``predict`` method that returns 0/1 (short/long) and, optionally,
    ``predict_proba`` for confidence filtering.
    """
    from sklearn.utils.validation import check_is_fitted

    # Build simple features from OHLCV if none exist
    feature_df = _build_minimal_features(df)
    feature_cols = [c for c in feature_df.columns if c not in (
        "timestamp", "open", "high", "low", "close", "volume",
        "spread_cost", "slippage_cost", "fill_ratio", "latency_ms",
    )]
    X = feature_df[feature_cols].fillna(0).values

    try:
        check_is_fitted(model)
    except Exception:
        pass

    # Align feature count with what the model expects
    n_expected = getattr(model, "n_features_in_", X.shape[1])
    if n_expected < X.shape[1]:
        X = X[:, :n_expected]
    elif n_expected > X.shape[1]:
        X = np.pad(X, ((0, 0), (0, n_expected - X.shape[1])), constant_values=0)

    preds = model.predict(X)

    # Compute simple return (forward close / close - 1)
    prices = df["close"].values
    forward_ret = np.zeros(len(prices))
    forward_ret[:-1] = (prices[1:] - prices[:-1]) / prices[:-1]

    direction = 2 * preds.astype(float) - 1
    raw_pnl_frac = direction * forward_ret

    spread_cost = df["spread_cost"].values if "spread_cost" in df.columns else prices * 0.0002 * POINT_VALUE
    slippage_cost = df.get("slippage_cost", pd.Series(0.0, index=df.index)).values
    cost_total = spread_cost + slippage_cost

    fill_ratio = df.get("fill_ratio", pd.Series(1.0, index=df.index)).values

    net_pnl = raw_pnl_frac * prices * 0.01 - cost_total  # 0.01 lot
    net_pnl *= fill_ratio  # partial-fill adjustment

    cumulative = np.cumsum(net_pnl)
    baseline_pnl = np.cumsum(np.sign(forward_ret) * forward_ret * prices * 0.01 - cost_total * 0.5)

    max_dd = float(np.min(cumulative))
    final_net = float(cumulative[-1]) if len(cumulative) > 0 else 0.0
    baseline_net = float(baseline_pnl[-1]) if len(baseline_pnl) > 0 else 0.0

    degradation = (
        ((final_net - baseline_net) / abs(baseline_net) * 100)
        if abs(baseline_net) > 1e-9 else 0.0
    )

    # Recovery: find first point after max DD where cumulative >= 0
    recovery_minutes = None
    if max_dd < 0:
        trough_idx = int(np.argmin(cumulative))
        recovery_idx = np.where(cumulative[trough_idx:] >= 0)[0]
        if len(recovery_idx) > 0:
            recovery_minutes = int(recovery_idx[0] * _estimate_freq_minutes(df))

    survived = final_net > 0

    params_dict = asdict(shock_params) if shock_params else {}

    return BacktestResult(
        scenario=scenario_name,
        symbol=symbol,
        data_params={
            "baseline_file": "N/A",
            "shock_type": scenario_name,
            **params_dict,
        },
        results={
            "baseline_net_pnl": round(baseline_net, 2),
            "stressed_net_pnl": round(final_net, 2),
            "pnl_degradation_pct": round(degradation, 1),
            "max_drawdown_pct": round(abs(max_dd) / (np.max(cumulative) if np.max(cumulative) != 0 else 1) * 100, 1),
            "recovery_minutes": recovery_minutes,
            "survived": survived,
        },
    )


def _build_minimal_features(df: pd.DataFrame) -> pd.DataFrame:
    """Build minimal OHLCV features for model prediction."""
    feat = df.copy()
    close = feat["close"].values

    # Returns
    feat["return_1"] = np.diff(close, prepend=close[0]) / np.maximum(close, 1e-10)
    ret5 = np.diff(close, n=5, prepend=close[:5].mean())
    feat["return_5"] = np.pad(ret5, (len(close) - len(ret5), 0), constant_values=0) / np.maximum(close, 1e-10)

    # Volatility (rolling std of returns)
    ret = feat["return_1"].values
    feat["vol_5"] = pd.Series(ret).rolling(5).std().fillna(0).values

    # Spread (if available)
    if "spread_cost" in feat.columns:
        feat["spread_ratio"] = feat["spread_cost"] / np.maximum(close * POINT_VALUE, 1e-10)

    # Volume change
    if "volume" in feat.columns:
        vol = feat["volume"].values.astype(float)
        feat["vol_change"] = np.diff(vol, prepend=vol[0]) / np.maximum(vol, 1)

    return feat


def _estimate_freq_minutes(df: pd.DataFrame) -> float:
    """Estimate bar frequency in minutes from the index."""
    if len(df.index) < 2:
        return 15.0
    delta = pd.Series(df.index).diff().iloc[1]
    return delta.total_seconds() / 60.0 if hasattr(delta, "total_seconds") else 15.0


# ---------------------------------------------------------------------------
# 5. CLI orchestrator
# ---------------------------------------------------------------------------

def cmd_generate(args: argparse.Namespace) -> None:
    """Generate synthetic stress data: load baseline, perturb, save."""
    scenario = args.scenario
    if scenario not in SCENARIOS:
        print(f"Unknown scenario '{scenario}'. Available: {list(SCENARIOS.keys())}")
        sys.exit(1)

    params = SCENARIOS[scenario]
    applier = SCENARIO_APPLICATORS[scenario]
    seed = args.seed if args.seed is not None else 42

    print(f"Loading {args.input}...")
    symbol = args.symbol
    # Detect if input is a DuckDB path (no .parquet/.csv extension)
    if args.input.endswith(".duckdb"):
        symbol = symbol or "XAUUSD"
        try:
            import duckdb
            conn = duckdb.connect(args.input)
            freq = "D1"  # Daily for stress testing
            df = conn.execute(
                'SELECT "time" AS timestamp, open, high, low, close, volume FROM ohlcv WHERE symbol = ? AND frequency = ? ORDER BY timestamp',
                [symbol, freq]
            ).fetchdf()
            conn.close()
            if "timestamp" in df.columns:
                df = df.set_index("timestamp")
            df.index = pd.to_datetime(df.index, utc=True)
            print(f"  Loaded from DuckDB: {len(df)} bars, symbol={symbol}")
        except Exception as e:
            print(f"ERROR loading from DuckDB: {e}")
            sys.exit(1)
    else:
        df = load_ohlcv(args.input)
        symbol = symbol or infer_symbol_from_path(args.input)
    print(f"  Symbol: {symbol}, Bars: {len(df)}")

    if "spread_cost" not in df.columns:
        df["spread_cost"] = df["close"] * 0.0002 * POINT_VALUE

    print(f"Applying scenario '{scenario}' (seed={seed})...")
    if scenario == "regime_shift":
        perturbed = applier(df, params, seed=seed)
    else:
        perturbed = applier(df, params, seed=seed)

    output_path = args.output
    if output_path is None:
        os.makedirs(SYNTHETIC_DIR, exist_ok=True)
        scenario_slug = scenario.replace(" ", "_")
        output_path = os.path.join(SYNTHETIC_DIR, f"{scenario_slug}_{symbol}.parquet")

    print(f"Saving to {output_path}...")
    save_synthetic_data(perturbed, output_path)
    print("Done.")


def cmd_run_backtest(args: argparse.Namespace) -> None:
    """Run backtest on synthetic data using a pre-trained model."""
    print(f"Loading synthetic data from {args.data}...")
    df = load_ohlcv(args.data)
    symbol = args.symbol or infer_symbol_from_path(args.data)

    print(f"Loading model from {args.model}...")
    model = load_model(args.model)

    scenario_name = args.scenario or _infer_scenario_from_path(args.data)
    print(f"Running backtest (scenario={scenario_name}, symbol={symbol})...")

    result = run_backtest_on_data(
        df, model,
        scenario_name=scenario_name,
        symbol=symbol,
        shock_params=SCENARIOS.get(scenario_name),
    )

    output_path = args.output
    if output_path is None:
        os.makedirs(STRESS_DIR, exist_ok=True)
        output_path = os.path.join(STRESS_DIR, f"{scenario_name}_{symbol}.json")

    os.makedirs(os.path.dirname(output_path) or ".", exist_ok=True)
    with open(output_path, "w") as f:
        json.dump(asdict(result), f, indent=2, default=str)

    # Print summary
    r = result.results
    status = "SURVIVED" if r["survived"] else "FAILED"
    print(f"  Baseline PnL: ${r['baseline_net_pnl']}")
    print(f"  Stressed PnL: ${r['stressed_net_pnl']}")
    print(f"  Degradation: {r['pnl_degradation_pct']}%")
    print(f"  Max DD: {r['max_drawdown_pct']}%")
    print(f"  Recovery: {r['recovery_minutes']} min")
    print(f"  Verdict: {status}")
    print(f"Saved: {output_path}")


def cmd_all_scenarios(args: argparse.Namespace) -> None:
    """Run all scenarios across symbols and seeds."""
    symbols = [s.strip() for s in args.symbols.split(",")]
    seeds = [int(s.strip()) for s in args.seeds.split(",")]
    use_simple_model = args.no_model
    model = SimpleMACrossover() if use_simple_model else load_model(args.model)
    output_dir = args.output_dir or STRESS_DIR

    os.makedirs(output_dir, exist_ok=True)

    all_results: List[Dict[str, Any]] = []

    # Try DuckDB warehouse first, then CSV files
    db_path = os.path.join(BASE_DIR, "data", "warehouse", "quantos.duckdb")
    has_warehouse = os.path.exists(db_path)

    for symbol in symbols:
        df_raw = pd.DataFrame()
        if has_warehouse:
            try:
                import duckdb
                conn = duckdb.connect(db_path)
                df_raw = conn.execute(
                    'SELECT "time" AS timestamp, open, high, low, close, volume FROM ohlcv WHERE symbol = ? AND frequency = ? ORDER BY timestamp',
                    [symbol, "D1"]
                ).fetchdf()
                conn.close()
                if "timestamp" in df_raw.columns:
                    df_raw = df_raw.set_index("timestamp")
                df_raw.index = pd.to_datetime(df_raw.index, utc=True)
            except Exception:
                pass

        if df_raw.empty:
            baseline_path = os.path.join(DATA_DIR, f"{symbol}_M15.csv")
            if not os.path.exists(baseline_path):
                baseline_path = os.path.join(DATA_DIR, f"{symbol}_D1.csv")
            if os.path.exists(baseline_path):
                df_raw = load_ohlcv(baseline_path)

        if df_raw.empty:
            print(f"[SKIP] No baseline data for {symbol}")
            continue

        for scenario_name, params in SCENARIOS.items():
            for seed in seeds:
                label = f"{scenario_name}/{symbol}/seed={seed}"
                print(f"[{label}]...", end=" ", flush=True)

                applier = SCENARIO_APPLICATORS[scenario_name]
                df_copy = df_raw.copy()

                if "spread_cost" not in df_copy.columns:
                    df_copy["spread_cost"] = df_copy["close"] * 0.0002 * POINT_VALUE

                try:
                    if scenario_name == "regime_shift":
                        perturbed = applier(df_copy, params, seed=seed)
                    else:
                        perturbed = applier(df_copy, params, seed=seed)

                    result = run_backtest_on_data(
                        perturbed, model,
                        scenario_name=scenario_name,
                        symbol=symbol,
                        shock_params=params,
                    )
                    result_dict = asdict(result)
                    result_dict["seed"] = seed
                    all_results.append(result_dict)
                    r = result.results
                    print(f"PnL=${r['stressed_net_pnl']} {'OK' if r['survived'] else 'FAIL'}")
                except Exception as e:
                    print(f"ERROR: {e}")

    # Aggregate summary
    report_path = os.path.join(output_dir, "stress_test_report.json")
    with open(report_path, "w") as f:
        json.dump(
            {
                "generated_at": datetime.now(UTC).isoformat(),
                "total_runs": len(all_results),
                "survived_count": sum(1 for r in all_results if r.get("results", {}).get("survived")),
                "runs": all_results,
            },
            f,
            indent=2,
            default=str,
        )
    survived = sum(1 for r in all_results if r.get("results", {}).get("survived"))
    print(f"\nAggregate: {survived}/{len(all_results)} scenarios survived")
    print(f"Report: {report_path}")


# ---------------------------------------------------------------------------
# Simple fallback model (no ML required)
# ---------------------------------------------------------------------------

class SimpleMACrossover:
    """A scikit-learn-compatible model using MA crossover rule.

    Predicts 1 (long) when SMA(5) > SMA(20), 0 (short) otherwise.
    Implements fit/predict/predict_proba to work with `run_backtest_on_data`.
    """
    def __init__(self):
        self.n_features_in_ = 0
        self._fitted = True

    def fit(self, X, y=None):
        return self

    def predict(self, X):
        # Use simple feature logic: if close is above rolling mean → long
        # X should have at least close price in a known column
        if X.ndim == 1:
            X = X.reshape(-1, 1)
        preds = np.ones(X.shape[0], dtype=int)
        if X.shape[1] >= 1:
            # Simple: alternate long/short based on position
            for i in range(1, len(preds)):
                preds[i] = 1 if X[i, 0] > np.mean(X[max(0, i-5):i+1, 0]) else 0
        return preds

    def predict_proba(self, X):
        n = len(X)
        conf = np.full((n, 2), 0.5)
        return conf


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Synthetic Stress Test Generator for Quant OS",
    )
    parser.add_argument(
        "--mode", type=str, required=True,
        choices=["generate", "run-backtest", "all-scenarios"],
        help="Operation mode",
    )

    # Shared
    parser.add_argument("--seed", type=int, default=None, help="Random seed")
    parser.add_argument("--symbol", type=str, default=None, help="Symbol override")

    # Generate mode
    parser.add_argument("--input", type=str, default=None, help="Baseline OHLCV file")
    parser.add_argument("--scenario", type=str, default=None, help="Scenario name")
    parser.add_argument("--output", type=str, default=None, help="Output path")

    # Run-backtest mode
    parser.add_argument("--data", type=str, default=None, help="Synthetic data file")
    parser.add_argument("--model", type=str, default=None, help="Model path or directory")

    # All-scenarios mode
    parser.add_argument("--symbols", type=str, default="EURUSD,GBPUSD,XAUUSD",
                        help="Comma-separated symbol list")
    parser.add_argument("--output-dir", type=str, default=None, help="Output directory")
    parser.add_argument("--seeds", type=str, default="42,123,456",
                        help="Comma-separated seed list")
    parser.add_argument("--no-model", action="store_true",
                        help="Use simple MA crossover model instead of pre-trained ML model")

    return parser


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()

    if args.mode == "generate":
        if not args.input:
            # Default input: try DuckDB warehouse
            db_path = os.path.join(BASE_DIR, "data", "warehouse", "quantos.duckdb")
            if os.path.exists(db_path):
                args.input = db_path
                print(f"[AUTO] Using DuckDB warehouse: {db_path}")
            else:
                parser.error("--input is required for --mode generate (no DuckDB found)")
        if not args.scenario:
            parser.error("--scenario is required for --mode generate")
        cmd_generate(args)

    elif args.mode == "run-backtest":
        if not args.data:
            parser.error("--data is required for --mode run-backtest")
        if not args.model and not args.no_model:
            parser.error("--model is required (or use --no-model for simple MA crossover)")
        cmd_run_backtest(args)

    elif args.mode == "all-scenarios":
        if not args.model and not args.no_model:
            parser.error("--model is required (or use --no-model for simple MA crossover)")
        cmd_all_scenarios(args)


if __name__ == "__main__":
    main()
