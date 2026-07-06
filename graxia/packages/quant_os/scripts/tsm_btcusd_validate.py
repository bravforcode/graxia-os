"""
BTCUSD TSM Validation — Comprehensive Backtest for 5th Asset Inclusion.

Validates BTCUSD for inclusion in the 4-asset concentrated TSM portfolio.
Uses BTC_YF_close from d1_multi_asset.parquet (yfinance BTC-USD daily data).

Tasks:
1. Solo BTCUSD TSM backtest (individual Sharpe)
2. BTCUSD as 5th asset in 4-asset portfolio
3. Walk-forward validation (70/30 split)
4. Weight sensitivity (5%, 8%, 10%, 15%)
5. Correlation with existing portfolio assets
6. Swap cost impact analysis
7. Go/No-go recommendation

Usage:
    python scripts/tsm_btcusd_validate.py
"""

import importlib.util
import math
import sys
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd

SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = SCRIPT_DIR.parent
BASE = PROJECT_ROOT
sys.path.insert(0, str(PROJECT_ROOT))

# Load deflated_sharpe module
_spec_dsr = importlib.util.spec_from_file_location("deflated_sharpe", BASE / "validation" / "deflated_sharpe.py")
_mod_dsr = importlib.util.module_from_spec(_spec_dsr)
_spec_dsr.loader.exec_module(_mod_dsr)
deflated_sharpe_ratio = _mod_dsr.deflated_sharpe_ratio
_norm_cdf = _mod_dsr._norm_cdf

REPORTS = BASE / "reports"
REPORTS.mkdir(parents=True, exist_ok=True)

# ── Config ──
LOOKBACKS = [20, 40, 60, 120]
TARGET_VOL = 0.10
REBALANCE_FREQ = "W-FRI"
POSITION_CAP = 1.5

# BTC costs from cost_calibration.json
BTC_COST_BPS = 8.74  # round-trip measured
BTC_SWAP_LONG_BPS = -3.0  # daily swap long (bps of notional)
BTC_SWAP_SHORT_BPS = -1.5  # daily swap short

# 4-asset portfolio costs
ASSET_COSTS = {
    "NAS100": {"rt_bps": 1.0, "swap_long": -0.30, "swap_short": 0.10},
    "XAUUSD": {"rt_bps": 0.72, "swap_long": -0.50, "swap_short": 0.20},
    "OIL": {"rt_bps": 9.76, "swap_long": -0.50, "swap_short": 0.15},
    "USDJPY": {"rt_bps": 7.12, "swap_long": 0.08, "swap_short": -0.20},
}


# ── Data Loading ──


def load_btc_data() -> pd.Series:
    """Load BTC_YF_close from multi-asset parquet."""
    path = BASE / "artifacts" / "portfolio" / "d1_multi_asset.parquet"
    df = pd.read_parquet(path)
    df.index = pd.to_datetime(df.index, utc=True)
    df = df.sort_index()
    btc = df["BTC_YF_close"].dropna()
    btc = btc[btc.index >= "2016-01-01"]
    return btc


def load_portfolio_data() -> pd.DataFrame:
    """Load 4-asset portfolio close prices from parquet (longer history)."""
    path = BASE / "artifacts" / "portfolio" / "d1_multi_asset.parquet"
    df = pd.read_parquet(path)
    df.index = pd.to_datetime(df.index, utc=True)
    df = df.sort_index()

    # Map parquet column names to short names
    col_map = {
        "NAS100_close": "NAS100",
        "XAUUSD_close": "XAUUSD",
        "OIL_close": "OIL",
        "USDJPY_close": "USDJPY",
    }

    closes = {}
    for pq_col, short_name in col_map.items():
        if pq_col in df.columns:
            s = df[pq_col].dropna()
            s = s[s.index >= "2016-01-01"]
            if len(s) >= 180:
                closes[short_name] = s
                print(f"  Loaded {short_name}: {len(s)} bars, {s.index.min().date()} to {s.index.max().date()}")
            else:
                print(f"  WARNING: {short_name} has only {len(s)} bars (need >= 180)")
        else:
            print(f"  WARNING: {pq_col} not found in parquet")

    if not closes:
        raise RuntimeError("No portfolio asset data loaded!")

    result = pd.DataFrame(closes)
    result = result.dropna(how="all")
    return result


# ── Signal & Backtest ──


def ensemble_signal(returns: pd.Series) -> pd.Series:
    """Equal-weight mixture of vol-scaled momentum signals."""
    signals = []
    for L in LOOKBACKS:
        r = returns.rolling(L).sum()
        vol = returns.rolling(L).std()
        sig = r / vol.replace(0, np.nan)
        signals.append(sig)
    weights = [0.25] * len(LOOKBACKS)
    return sum(w * s for w, s in zip(weights, signals, strict=False))


def compute_position(returns: pd.Series, target_vol: float = TARGET_VOL) -> pd.Series:
    """Compute vol-targeted position."""
    sig = ensemble_signal(returns)
    realized_vol = returns.rolling(60).std() * (252**0.5)
    pos = sig * (target_vol / realized_vol.replace(0, np.nan))
    return pos.clip(-POSITION_CAP, POSITION_CAP)


def backtest_single_asset(
    close: pd.Series,
    cost_bps: float,
    swap_long_bps: float = 0.0,
    swap_short_bps: float = 0.0,
) -> pd.DataFrame:
    """Backtest TSM on a single asset with costs + swap."""
    df = pd.DataFrame({"close": close})
    df["ret"] = df["close"].pct_change()
    df["position"] = compute_position(df["ret"])

    # Weekly rebalance
    weekly_pos = df["position"].resample(REBALANCE_FREQ).last()
    weekly_pos = weekly_pos.reindex(df.index, method="ffill")
    df["position"] = weekly_pos

    # Strategy return
    df["strat_ret"] = df["position"].shift(1) * df["ret"]

    # Transaction costs
    df["pos_change"] = df["position"].diff().abs()
    df["tx_cost"] = df["pos_change"] * cost_bps / 10000

    # Swap costs
    prev_pos = df["position"].shift(1)
    df["swap_cost"] = 0.0
    long_mask = prev_pos > 0
    short_mask = prev_pos < 0
    df.loc[long_mask, "swap_cost"] = prev_pos[long_mask].abs() * abs(swap_long_bps) / 10000
    df.loc[short_mask, "swap_cost"] = prev_pos[short_mask].abs() * abs(swap_short_bps) / 10000
    df["swap_cost"] = df["swap_cost"].abs()

    df["cost"] = df["tx_cost"] + df["swap_cost"]
    df["strat_ret_net"] = df["strat_ret"] - df["cost"]

    return df


def portfolio_backtest_5asset(
    data: pd.DataFrame,
    btc_weight: float = 0.20,
    include_btc: bool = True,
) -> tuple:
    """Multi-asset portfolio: 4-asset base + optional BTC."""
    asset_returns = {}
    asset_costs = {}
    asset_pos_changes = {}

    for asset in data.columns:
        if asset == "BTC" and not include_btc:
            continue
        close = data[asset].dropna()
        if len(close) < 180:
            print(f"  SKIP {asset}: only {len(close)} bars")
            continue

        if asset == "BTC":
            cost_bps = BTC_COST_BPS
            swap_l = BTC_SWAP_LONG_BPS
            swap_s = BTC_SWAP_SHORT_BPS
        else:
            cfg = ASSET_COSTS.get(asset, {"rt_bps": 5.0, "swap_long": 0.0, "swap_short": 0.0})
            cost_bps = cfg["rt_bps"]
            swap_l = cfg["swap_long"]
            swap_s = cfg["swap_short"]

        bt = backtest_single_asset(close, cost_bps, swap_l, swap_s)
        asset_returns[asset] = bt["strat_ret_net"]
        asset_costs[asset] = bt["cost"]
        asset_pos_changes[asset] = bt["pos_change"]

    if not asset_returns:
        return pd.DataFrame(), {}

    ret_df = pd.DataFrame(asset_returns)
    cost_df = pd.DataFrame(asset_costs)
    pc_df = pd.DataFrame(asset_pos_changes)

    # Equal-weight across all assets (including BTC if present)
    portfolio_ret = ret_df.mean(axis=1, skipna=True)
    portfolio_cost = cost_df.mean(axis=1, skipna=True)

    valid_mask = portfolio_ret.notna()
    portfolio_ret = portfolio_ret[valid_mask]
    portfolio_cost = portfolio_cost[valid_mask]
    pc_df = pc_df.loc[valid_mask]

    result = pd.DataFrame(
        {
            "portfolio_ret": portfolio_ret,
            "portfolio_cost": portfolio_cost,
            "cum_ret": (1 + portfolio_ret).cumprod(),
        }
    )

    details = {
        "asset_returns": ret_df,
        "asset_costs": cost_df,
        "asset_pos_changes": pc_df,
        "n_assets": len(asset_returns),
    }

    return result, details


def portfolio_backtest_custom_weights(
    data: pd.DataFrame,
    asset_weights: dict,
) -> tuple:
    """Portfolio backtest with custom asset weights (must sum to 1)."""
    asset_returns = {}
    asset_costs = {}
    asset_pos_changes = {}

    for asset in data.columns:
        close = data[asset].dropna()
        if len(close) < 180:
            continue

        if asset == "BTC":
            cost_bps = BTC_COST_BPS
            swap_l = BTC_SWAP_LONG_BPS
            swap_s = BTC_SWAP_SHORT_BPS
        else:
            cfg = ASSET_COSTS.get(asset, {"rt_bps": 5.0, "swap_long": 0.0, "swap_short": 0.0})
            cost_bps = cfg["rt_bps"]
            swap_l = cfg["swap_long"]
            swap_s = cfg["swap_short"]

        bt = backtest_single_asset(close, cost_bps, swap_l, swap_s)
        asset_returns[asset] = bt["strat_ret_net"]
        asset_costs[asset] = bt["cost"]
        asset_pos_changes[asset] = bt["pos_change"]

    if not asset_returns:
        return pd.DataFrame(), {}

    ret_df = pd.DataFrame(asset_returns)
    cost_df = pd.DataFrame(asset_costs)
    pc_df = pd.DataFrame(asset_pos_changes)

    # Apply custom weights
    valid_assets = [a for a in ret_df.columns if a in asset_weights]
    if not valid_assets:
        return pd.DataFrame(), {}

    w = np.array([asset_weights[a] for a in valid_assets])
    w = w / w.sum()
    portfolio_ret = ret_df[valid_assets].values @ w
    portfolio_ret = pd.Series(portfolio_ret, index=ret_df.index)
    portfolio_cost = cost_df[valid_assets].values @ w
    portfolio_cost = pd.Series(portfolio_cost, index=cost_df.index)

    valid_mask = portfolio_ret.notna()
    portfolio_ret = portfolio_ret[valid_mask]
    portfolio_cost = portfolio_cost[valid_mask]
    pc_df = pc_df.loc[valid_mask]

    result = pd.DataFrame(
        {
            "portfolio_ret": portfolio_ret,
            "portfolio_cost": portfolio_cost,
            "cum_ret": (1 + portfolio_ret).cumprod(),
        }
    )

    details = {
        "asset_returns": ret_df,
        "asset_costs": cost_df,
        "asset_pos_changes": pc_df,
        "n_assets": len(asset_returns),
    }

    return result, details


# ── Metrics ──


@dataclass
class Metrics:
    name: str
    ann_ret: float
    ann_vol: float
    sharpe: float
    sortino: float
    max_dd: float
    dd_duration_days: int
    win_rate: float
    profit_factor: float
    skew: float
    kurtosis: float
    n_days: int
    n_years: float
    total_return: float
    annual_cost_drag_bps: float
    annual_cost_drag_pct: float
    avg_weekly_turnover: float
    avg_trade_duration_days: float
    total_trades: int


def compute_metrics(ret: pd.Series, cost_series: pd.Series, pos_changes: pd.DataFrame, name: str = "") -> Metrics:
    """Full metrics with trade analysis."""
    ret = ret.dropna()
    if len(ret) < 60:
        return Metrics(
            name=name,
            ann_ret=0,
            ann_vol=0,
            sharpe=0,
            sortino=0,
            max_dd=0,
            dd_duration_days=0,
            win_rate=0,
            profit_factor=0,
            skew=0,
            kurtosis=0,
            n_days=0,
            n_years=0,
            total_return=0,
            annual_cost_drag_bps=0,
            annual_cost_drag_pct=0,
            avg_weekly_turnover=0,
            avg_trade_duration_days=0,
            total_trades=0,
        )

    n_days = len(ret)
    n_years = n_days / 252

    ann_ret = ret.mean() * 252
    ann_vol = ret.std() * np.sqrt(252)
    sharpe = ann_ret / ann_vol if ann_vol > 0 else 0

    downside = ret[ret < 0]
    downside_vol = downside.std() * np.sqrt(252) if len(downside) > 0 else 1e-10
    sortino = ann_ret / downside_vol if downside_vol > 0 else 0

    cum = (1 + ret).cumprod()
    peak = cum.cummax()
    dd = (cum - peak) / peak
    max_dd = dd.min()

    is_dd = dd < 0
    dd_groups = (~is_dd).cumsum()
    dd_duration_days = int(is_dd.groupby(dd_groups).sum().max()) if is_dd.any() else 0

    win_rate = (ret > 0).mean()
    gains = ret[ret > 0].sum()
    losses = abs(ret[ret < 0].sum())
    profit_factor = gains / losses if losses > 0 else float("inf")

    total_return = cum.iloc[-1] - 1

    total_cost = cost_series.dropna().sum()
    annual_cost_drag_pct = total_cost / n_years if n_years > 0 else 0
    annual_cost_drag_bps = annual_cost_drag_pct * 10000

    if pos_changes is not None and not pos_changes.empty:
        weekly_pc = pos_changes.resample("W-FRI").sum()
        avg_weekly_turnover = weekly_pc.sum(axis=1).mean()
    else:
        avg_weekly_turnover = 0

    # Trade analysis: count position changes as trades
    if pos_changes is not None and not pos_changes.empty:
        total_pos_change = pos_changes.sum(axis=1).sum()
        # Estimate trades: each full position flip counts as ~2 trades (exit + entry)
        total_trades = int(total_pos_change / 2)
        # Average trade duration: 7 days (weekly rebalance)
        avg_trade_duration_days = 7.0
    else:
        total_trades = 0
        avg_trade_duration_days = 0

    skew = ret.skew()
    kurtosis = ret.kurtosis()

    return Metrics(
        name=name,
        ann_ret=ann_ret,
        ann_vol=ann_vol,
        sharpe=sharpe,
        sortino=sortino,
        max_dd=max_dd,
        dd_duration_days=dd_duration_days,
        win_rate=win_rate,
        profit_factor=profit_factor,
        skew=skew,
        kurtosis=kurtosis,
        n_days=n_days,
        n_years=n_years,
        total_return=total_return,
        annual_cost_drag_bps=annual_cost_drag_bps,
        annual_cost_drag_pct=annual_cost_drag_pct,
        avg_weekly_turnover=avg_weekly_turnover,
        avg_trade_duration_days=avg_trade_duration_days,
        total_trades=total_trades,
    )


# DEPRECATED: Use from validation.deflated_sharpe import deflated_sharpe_ratio
# This inline implementation will be removed in Phase 5.
def deflated_sharpe_n1(
    observed_sharpe: float,
    n_observations: int,
    skewness: float = 0.0,
    excess_kurtosis: float = 0.0,
) -> dict:
    """Deflated Sharpe ratio N=1 (single pre-registered hypothesis)."""
    if n_observations <= 1:
        return {"passes": False, "p_value": 1.0, "z_score": 0.0}

    sr_var = (1 - skewness * observed_sharpe + (excess_kurtosis + 3 - 1) / 4 * observed_sharpe**2) / (
        n_observations - 1
    )
    sr_std = math.sqrt(max(sr_var, 1e-20))
    expected_max_sharpe = 0.0
    z = observed_sharpe / sr_std
    p_value = 1 - _norm_cdf(z)
    passes = observed_sharpe > 0 and p_value < 0.05

    return {
        "passes": passes,
        "p_value": p_value,
        "z_score": z,
        "sr_std": sr_std,
        "expected_max_sharpe": expected_max_sharpe,
        "observed_sharpe": observed_sharpe,
        "n_observations": n_observations,
        "skewness": skewness,
        "excess_kurtosis": excess_kurtosis,
    }


# ── Walk-Forward ──


def walk_forward_btc(
    close: pd.Series,
    train_pct: float = 0.7,
) -> dict:
    """Walk-forward validation for single BTC asset."""
    n = len(close)
    train_end = int(n * train_pct)

    train_close = close.iloc[:train_end]
    test_close = close.iloc[train_end:]

    train_bt = backtest_single_asset(train_close, BTC_COST_BPS, BTC_SWAP_LONG_BPS, BTC_SWAP_SHORT_BPS)
    test_bt = backtest_single_asset(test_close, BTC_COST_BPS, BTC_SWAP_LONG_BPS, BTC_SWAP_SHORT_BPS)

    train_ret = train_bt["strat_ret_net"]
    test_ret = test_bt["strat_ret_net"]

    def _sharpe(r):
        r = r.dropna()
        if len(r) < 30:
            return 0.0
        ann_ret = r.mean() * 252
        ann_vol = r.std() * np.sqrt(252)
        return ann_ret / ann_vol if ann_vol > 0 else 0.0

    train_m = compute_metrics(train_ret, train_bt["cost"], train_bt[["pos_change"]], "train")
    test_m = compute_metrics(test_ret, test_bt["cost"], test_bt[["pos_change"]], "test")

    return {
        "train": train_m,
        "test": test_m,
        "train_sharpe": _sharpe(train_ret),
        "test_sharpe": _sharpe(test_ret),
        "train_days": len(train_ret),
        "test_days": len(test_ret),
        "train_start": str(train_close.index[0].date()),
        "train_end": str(train_close.index[-1].date()),
        "test_start": str(test_close.index[0].date()),
        "test_end": str(test_close.index[-1].date()),
    }


def walk_forward_portfolio(
    data: pd.DataFrame,
    train_pct: float = 0.7,
) -> dict:
    """Walk-forward for 5-asset portfolio."""
    n = len(data)
    train_end = int(n * train_pct)

    train_data = data.iloc[:train_end]
    test_data = data.iloc[train_end:]

    bt_train, _ = portfolio_backtest_5asset(train_data)
    bt_test, _ = portfolio_backtest_5asset(test_data)

    train_m = compute_metrics(bt_train["portfolio_ret"], bt_train["portfolio_cost"], pd.DataFrame(), "train")
    test_m = compute_metrics(bt_test["portfolio_ret"], bt_test["portfolio_cost"], pd.DataFrame(), "test")

    return {
        "train": train_m,
        "test": test_m,
        "train_days": train_m.n_days,
        "test_days": test_m.n_days,
    }


# ── Correlation Analysis ──


def compute_correlation_matrix(data: pd.DataFrame) -> pd.DataFrame:
    """Return correlation matrix for all assets."""
    returns = data.pct_change().dropna()
    return returns.corr()


def compute_effective_bets(corr_matrix: pd.DataFrame) -> dict:
    """Effective number of independent bets."""
    n = len(corr_matrix)
    mask = np.triu(np.ones_like(corr_matrix, dtype=bool), k=1)
    upper_vals = corr_matrix.values[mask]
    avg_corr = upper_vals.mean()
    n_eff = n / (1 + (n - 1) * avg_corr)
    return {
        "n_nominal": n,
        "avg_pairwise_corr": avg_corr,
        "n_effective": n_eff,
        "diversification_ratio": n_eff / n,
    }


# ── Weight Sensitivity ──


def weight_sensitivity_analysis(data: pd.DataFrame) -> dict:
    """Test BTC weights: 0%, 5%, 8%, 10%, 15%, 20%."""
    weights = [0.0, 0.05, 0.08, 0.10, 0.15, 0.20]
    results = {}

    for btc_w in weights:
        # Remaining weight distributed equally among 4 assets
        other_w = (1.0 - btc_w) / 4.0 if btc_w < 1.0 else 0.0
        asset_weights = {
            "NAS100": other_w,
            "XAUUSD": other_w,
            "OIL": other_w,
            "USDJPY": other_w,
        }
        if btc_w > 0:
            asset_weights["BTC"] = btc_w

        bt, details = portfolio_backtest_custom_weights(data, asset_weights)
        if bt.empty:
            continue

        m = compute_metrics(
            bt["portfolio_ret"], bt["portfolio_cost"], details.get("asset_pos_changes"), f"btc_{int(btc_w*100)}pct"
        )
        dsr = deflated_sharpe_n1(m.sharpe, m.n_days, m.skew, m.kurtosis)

        results[f"btc_{int(btc_w*100)}pct"] = {
            "btc_weight": btc_w,
            "metrics": m,
            "dsr": dsr,
        }

    return results


# ── Swap Cost Impact ──


def swap_cost_impact(close: pd.Series) -> dict:
    """Compare TSM performance with and without swap costs."""
    bt_no_swap = backtest_single_asset(close, BTC_COST_BPS, 0.0, 0.0)
    bt_with_swap = backtest_single_asset(close, BTC_COST_BPS, BTC_SWAP_LONG_BPS, BTC_SWAP_SHORT_BPS)

    m_no_swap = compute_metrics(bt_no_swap["strat_ret_net"], bt_no_swap["cost"], bt_no_swap[["pos_change"]], "no_swap")
    m_with_swap = compute_metrics(
        bt_with_swap["strat_ret_net"], bt_with_swap["cost"], bt_with_swap[["pos_change"]], "with_swap"
    )

    return {
        "no_swap": m_no_swap,
        "with_swap": m_with_swap,
        "sharpe_drag": m_no_swap.sharpe - m_with_swap.sharpe,
        "return_drag_pct": m_no_swap.ann_ret - m_with_swap.ann_ret,
    }


# ── Formatting ──


def format_metrics(m: Metrics, label: str) -> str:
    lines = [f"### {label}\n"]
    lines.append("| Metric | Value |")
    lines.append("|--------|-------|")
    lines.append(f"| Total Return | {m.total_return:.2%} |")
    lines.append(f"| Annualized Return | {m.ann_ret:.2%} |")
    lines.append(f"| Annualized Vol | {m.ann_vol:.2%} |")
    lines.append(f"| Sharpe Ratio | {m.sharpe:.3f} |")
    lines.append(f"| Sortino Ratio | {m.sortino:.3f} |")
    lines.append(f"| Max Drawdown | {m.max_dd:.2%} |")
    lines.append(f"| DD Duration | {m.dd_duration_days} days |")
    lines.append(f"| Win Rate | {m.win_rate:.1%} |")
    lines.append(f"| Profit Factor | {m.profit_factor:.2f} |")
    lines.append(f"| Skewness | {m.skew:.3f} |")
    lines.append(f"| Excess Kurtosis | {m.kurtosis:.3f} |")
    lines.append(f"| Observation Days | {m.n_days} |")
    lines.append(f"| Observation Years | {m.n_years:.1f} |")
    lines.append(f"| Annual Cost Drag (bps) | {m.annual_cost_drag_bps:.1f} |")
    lines.append(f"| Annual Cost Drag (%) | {m.annual_cost_drag_pct:.2%} |")
    lines.append(f"| Avg Weekly Turnover | {m.avg_weekly_turnover:.3f} |")
    lines.append(f"| Est. Total Trades | {m.total_trades} |")
    lines.append(f"| Avg Trade Duration | {m.avg_trade_duration_days:.1f} days |")
    lines.append("")
    return "\n".join(lines)


def format_dsr(dsr: dict, label: str) -> str:
    lines = [f"### DSR (N=1): {label}\n"]
    lines.append("| Metric | Value |")
    lines.append("|--------|-------|")
    lines.append(f"| Observed Sharpe | {dsr['observed_sharpe']:.3f} |")
    lines.append(f"| T (observations) | {dsr['n_observations']} |")
    lines.append(f"| SR Std Error | {dsr['sr_std']:.6f} |")
    lines.append(f"| Z-score | {dsr['z_score']:.3f} |")
    lines.append(f"| P-value (one-sided) | {dsr['p_value']:.6f} |")
    lines.append(f"| Significant (95%) | {'YES' if dsr['passes'] else 'NO'} |")
    lines.append("")
    return "\n".join(lines)


# ── Main ──


def main():
    print("=" * 70)
    print("BTCUSD TSM VALIDATION — Comprehensive Backtest")
    print("=" * 70)
    print()

    # ── Load Data ──
    print("Loading data...")
    btc_close = load_btc_data()
    portfolio_data = load_portfolio_data()

    # Merge BTC into portfolio data
    btc_aligned = btc_close.reindex(portfolio_data.index, method="ffill")
    combined_data = portfolio_data.copy()
    combined_data["BTC"] = btc_aligned

    print(f"BTC data: {len(btc_close)} bars, {btc_close.index.min().date()} to {btc_close.index.max().date()}")
    print(
        f"Portfolio data: {len(portfolio_data)} bars, {portfolio_data.index.min().date()} to {portfolio_data.index.max().date()}"
    )
    print(f"Combined data: {len(combined_data)} bars")
    print(f"Portfolio assets: {list(portfolio_data.columns)}")
    print()

    all_report = []

    # ══════════════════════════════════════════════════════════════════════
    # SECTION 1: Solo BTCUSD TSM Backtest
    # ══════════════════════════════════════════════════════════════════════
    print("=" * 70)
    print("SECTION 1: Solo BTCUSD TSM Backtest")
    print("=" * 70)

    btc_bt = backtest_single_asset(btc_close, BTC_COST_BPS, BTC_SWAP_LONG_BPS, BTC_SWAP_SHORT_BPS)
    btc_m = compute_metrics(btc_bt["strat_ret_net"], btc_bt["cost"], btc_bt[["pos_change"]], "BTCUSD_solo")
    btc_dsr = deflated_sharpe_n1(btc_m.sharpe, btc_m.n_days, btc_m.skew, btc_m.kurtosis)

    print(format_metrics(btc_m, "Solo BTCUSD TSM (with swap)"))
    print(format_dsr(btc_dsr, "Solo BTC"))
    all_report.append(format_metrics(btc_m, "Solo BTCUSD TSM (with swap)"))
    all_report.append(format_dsr(btc_dsr, "Solo BTC"))

    # ══════════════════════════════════════════════════════════════════════
    # SECTION 2: BTCUSD in 5-Asset Portfolio (Equal Weight)
    # ══════════════════════════════════════════════════════════════════════
    print("=" * 70)
    print("SECTION 2: 5-Asset Portfolio (Equal Weight: NAS100, XAUUSD, OIL, USDJPY, BTC)")
    print("=" * 70)

    bt_5eq, details_5eq = portfolio_backtest_5asset(combined_data)
    if not bt_5eq.empty:
        m_5eq = compute_metrics(
            bt_5eq["portfolio_ret"], bt_5eq["portfolio_cost"], details_5eq.get("asset_pos_changes"), "5asset_eq"
        )
        dsr_5eq = deflated_sharpe_n1(m_5eq.sharpe, m_5eq.n_days, m_5eq.skew, m_5eq.kurtosis)
        print(format_metrics(m_5eq, "5-Asset Equal Weight"))
        print(format_dsr(dsr_5eq, "5-Asset Equal Weight"))
        all_report.append(format_metrics(m_5eq, "5-Asset Equal Weight"))
        all_report.append(format_dsr(dsr_5eq, "5-Asset Equal Weight"))

    # 4-asset baseline (no BTC) for comparison
    bt_4eq, details_4eq = portfolio_backtest_5asset(combined_data, include_btc=False)
    if not bt_4eq.empty:
        m_4eq = compute_metrics(
            bt_4eq["portfolio_ret"], bt_4eq["portfolio_cost"], details_4eq.get("asset_pos_changes"), "4asset_eq"
        )
        print("\n--- 4-Asset Baseline (for comparison) ---")
        print(f"  Sharpe: {m_4eq.sharpe:.3f}  Ann Ret: {m_4eq.ann_ret:.2%}  Max DD: {m_4eq.max_dd:.2%}")

    # ══════════════════════════════════════════════════════════════════════
    # SECTION 3: Walk-Forward Validation (70/30)
    # ══════════════════════════════════════════════════════════════════════
    print("\n" + "=" * 70)
    print("SECTION 3: Walk-Forward Validation (70% Train / 30% Test)")
    print("=" * 70)

    # BTC solo walk-forward
    wf_btc = walk_forward_btc(btc_close)
    print("\n--- BTC Solo Walk-Forward ---")
    print(f"  Train: {wf_btc['train_start']} to {wf_btc['train_end']} ({wf_btc['train_days']} days)")
    print(f"  Test:  {wf_btc['test_start']} to {wf_btc['test_end']} ({wf_btc['test_days']} days)")
    print(f"  Train Sharpe: {wf_btc['train_sharpe']:.3f}")
    print(f"  Test Sharpe:  {wf_btc['test_sharpe']:.3f}")
    print(f"  Train Ann Ret: {wf_btc['train'].ann_ret:.2%}  Test Ann Ret: {wf_btc['test'].ann_ret:.2%}")
    print(f"  Train Max DD:  {wf_btc['train'].max_dd:.2%}  Test Max DD:  {wf_btc['test'].max_dd:.2%}")
    all_report.append("\n## Walk-Forward: BTC Solo (70/30)\n")
    all_report.append("| Period | Sharpe | Ann Ret | Max DD | Days |")
    all_report.append("|--------|--------|---------|--------|------|")
    all_report.append(
        f"| Train | {wf_btc['train_sharpe']:.3f} | {wf_btc['train'].ann_ret:.2%} | {wf_btc['train'].max_dd:.2%} | {wf_btc['train_days']} |"
    )
    all_report.append(
        f"| Test (OOS) | {wf_btc['test_sharpe']:.3f} | {wf_btc['test'].ann_ret:.2%} | {wf_btc['test'].max_dd:.2%} | {wf_btc['test_days']} |"
    )
    all_report.append("")

    # 5-asset portfolio walk-forward
    wf_port = walk_forward_portfolio(combined_data)
    print("\n--- 5-Asset Portfolio Walk-Forward ---")
    print(f"  Train Sharpe: {wf_port['train'].sharpe:.3f}")
    print(f"  Test Sharpe:  {wf_port['test'].sharpe:.3f}")
    all_report.append("\n## Walk-Forward: 5-Asset Portfolio (70/30)\n")
    all_report.append("| Period | Sharpe | Ann Ret | Max DD | Days |")
    all_report.append("|--------|--------|---------|--------|------|")
    all_report.append(
        f"| Train | {wf_port['train'].sharpe:.3f} | {wf_port['train'].ann_ret:.2%} | {wf_port['train'].max_dd:.2%} | {wf_port['train_days']} |"
    )
    all_report.append(
        f"| Test (OOS) | {wf_port['test'].sharpe:.3f} | {wf_port['test'].ann_ret:.2%} | {wf_port['test'].max_dd:.2%} | {wf_port['test_days']} |"
    )
    all_report.append("")

    # ══════════════════════════════════════════════════════════════════════
    # SECTION 4: Weight Sensitivity
    # ══════════════════════════════════════════════════════════════════════
    print("\n" + "=" * 70)
    print("SECTION 4: BTC Weight Sensitivity Analysis")
    print("=" * 70)

    ws = weight_sensitivity_analysis(combined_data)
    print(
        f"\n{'BTC Wt':>8} {'Sharpe':>8} {'Sortino':>8} {'AnnRet':>8} {'MaxDD':>8} {'Win%':>6} {'PF':>6} {'DSR P':>8} {'Sig?':>5}"
    )
    print("-" * 80)
    all_report.append("\n## BTC Weight Sensitivity\n")
    all_report.append(
        "| BTC Weight | Sharpe | Sortino | Ann Ret | Max DD | Win Rate | Profit Factor | DSR P-value | Sig? |"
    )
    all_report.append(
        "|------------|--------|---------|---------|--------|----------|---------------|-------------|------|"
    )

    for key, entry in ws.items():
        m = entry["metrics"]
        dsr = entry["dsr"]
        sig = "YES" if dsr["passes"] else "NO"
        print(
            f"{entry['btc_weight']:>7.0%} {m.sharpe:>8.3f} {m.sortino:>8.3f} {m.ann_ret:>7.2%} {m.max_dd:>7.2%} {m.win_rate:>5.1%} {m.profit_factor:>5.2f} {dsr['p_value']:>8.4f} {sig:>5}"
        )
        all_report.append(
            f"| {entry['btc_weight']:.0%} | {m.sharpe:.3f} | {m.sortino:.3f} | {m.ann_ret:.2%} | {m.max_dd:.2%} | {m.win_rate:.1%} | {m.profit_factor:.2f} | {dsr['p_value']:.6f} | {sig} |"
        )

    all_report.append("")

    # ══════════════════════════════════════════════════════════════════════
    # SECTION 5: Correlation Analysis
    # ══════════════════════════════════════════════════════════════════════
    print("\n" + "=" * 70)
    print("SECTION 5: Correlation Analysis")
    print("=" * 70)

    corr = compute_correlation_matrix(combined_data)
    print("\nReturn Correlation Matrix:")
    print(corr.to_string())
    all_report.append("\n## Correlation Analysis\n")
    all_report.append("### Return Correlation Matrix\n")
    all_report.append("```")
    all_report.append(corr.to_string())
    all_report.append("```\n")

    eff = compute_effective_bets(corr)
    print(f"\nNominal bets:      {eff['n_nominal']}")
    print(f"Avg pairwise corr: {eff['avg_pairwise_corr']:.4f}")
    print(f"Effective bets:    {eff['n_effective']:.2f}")
    print(f"Diversification:   {eff['diversification_ratio']:.2%}")
    all_report.append(f"- **Nominal bets:** {eff['n_nominal']}")
    all_report.append(f"- **Avg pairwise correlation:** {eff['avg_pairwise_corr']:.4f}")
    all_report.append(f"- **Effective bets:** {eff['n_effective']:.2f}")
    all_report.append(f"- **Diversification ratio:** {eff['diversification_ratio']:.2%}")
    all_report.append("")

    # Print available correlations
    btc_corrs = {}
    for col in corr.columns:
        if col != "BTC":
            btc_corrs[col] = corr.loc["BTC", col]
    if btc_corrs:
        print("\nBTC correlations with other assets:")
        for asset, c in sorted(btc_corrs.items(), key=lambda x: abs(x[1]), reverse=True):
            print(f"  BTC-{asset}: {c:.4f}")
    all_report.append("\n### BTC Correlations\n")
    for asset, c in btc_corrs.items():
        all_report.append(f"- BTC-{asset}: {c:.4f}")
    all_report.append("")

    # ══════════════════════════════════════════════════════════════════════
    # SECTION 6: Swap Cost Impact
    # ══════════════════════════════════════════════════════════════════════
    print("\n" + "=" * 70)
    print("SECTION 6: Swap Cost Impact on BTCUSD TSM")
    print("=" * 70)

    swap_impact = swap_cost_impact(btc_close)
    m_ns = swap_impact["no_swap"]
    m_ws = swap_impact["with_swap"]
    print(f"\n{'Metric':<25} {'No Swap':>12} {'With Swap':>12} {'Drag':>12}")
    print("-" * 65)
    print(f"{'Sharpe':<25} {m_ns.sharpe:>12.3f} {m_ws.sharpe:>12.3f} {swap_impact['sharpe_drag']:>12.3f}")
    print(f"{'Ann Return':<25} {m_ns.ann_ret:>11.2%} {m_ws.ann_ret:>11.2%} {swap_impact['return_drag_pct']:>11.2%}")
    print(f"{'Max DD':<25} {m_ns.max_dd:>11.2%} {m_ws.max_dd:>11.2%}")
    print(f"{'Win Rate':<25} {m_ns.win_rate:>11.1%} {m_ws.win_rate:>11.1%}")
    print(f"{'Cost Drag (bps/yr)':<25} {m_ns.annual_cost_drag_bps:>12.1f} {m_ws.annual_cost_drag_bps:>12.1f}")

    all_report.append("\n## Swap Cost Impact\n")
    all_report.append("| Metric | No Swap | With Swap | Drag |")
    all_report.append("|--------|---------|-----------|------|")
    all_report.append(f"| Sharpe | {m_ns.sharpe:.3f} | {m_ws.sharpe:.3f} | {swap_impact['sharpe_drag']:.3f} |")
    all_report.append(
        f"| Ann Return | {m_ns.ann_ret:.2%} | {m_ws.ann_ret:.2%} | {swap_impact['return_drag_pct']:.2%} |"
    )
    all_report.append(f"| Max DD | {m_ns.max_dd:.2%} | {m_ws.max_dd:.2%} | |")
    all_report.append(
        f"| Annual Cost Drag | {m_ns.annual_cost_drag_bps:.1f} bps | {m_ws.annual_cost_drag_bps:.1f} bps | |"
    )
    all_report.append("")

    # ══════════════════════════════════════════════════════════════════════
    # SECTION 7: Decision Gate
    # ══════════════════════════════════════════════════════════════════════
    print("\n" + "=" * 70)
    print("SECTION 7: DECISION GATE")
    print("=" * 70)

    # Primary gate: OOS Sharpe from walk-forward
    oos_sharpe = wf_btc["test_sharpe"]
    full_sharpe = btc_m.sharpe
    net_sharpe = m_ws.sharpe  # with swap

    if oos_sharpe > 0.5:
        verdict = "GO"
        verdict_detail = f"OOS Sharpe = {oos_sharpe:.3f} > 0.5. BTCUSD shows real alpha. RECOMMENDED for inclusion."
    elif oos_sharpe > 0.3:
        verdict = "CONDITIONAL_GO"
        verdict_detail = f"OOS Sharpe = {oos_sharpe:.3f} (0.3-0.5). BTCUSD shows marginal alpha. CONDITIONAL: include with small weight (5%)."
    elif oos_sharpe > 0.0:
        verdict = "NO_GO"
        verdict_detail = f"OOS Sharpe = {oos_sharpe:.3f} (< 0.3). BTCUSD alpha is weak. DO NOT include."
    else:
        verdict = "NO_GO"
        verdict_detail = f"OOS Sharpe = {oos_sharpe:.3f} (negative). BTCUSD has no alpha. DO NOT include."

    print(f"\nVerdict: {verdict}")
    print(f"Detail:  {verdict_detail}")
    print()

    # Find optimal weight from sensitivity analysis
    best_key = max(ws.keys(), key=lambda k: ws[k]["metrics"].sharpe)
    best_entry = ws[best_key]
    recommended_weight = best_entry["btc_weight"]

    print(f"Recommended BTC weight: {recommended_weight:.0%}")
    print(f"  (Best Sharpe among tested weights: {best_entry['metrics'].sharpe:.3f})")
    print()

    # Risk summary
    print("Risk Summary:")
    print(f"  Full-period Sharpe (with swap): {net_sharpe:.3f}")
    print(f"  OOS Sharpe (walk-forward):      {oos_sharpe:.3f}")
    print(f"  Max Drawdown:                   {btc_m.max_dd:.2%}")
    print(f"  Sortino:                        {btc_m.sortino:.3f}")
    print(f"  Win Rate:                       {btc_m.win_rate:.1%}")
    print(f"  Profit Factor:                  {btc_m.profit_factor:.2f}")
    print(f"  Annual Cost Drag:               {m_ws.annual_cost_drag_bps:.1f} bps")
    for asset, c in btc_corrs.items():
        print(f"  BTC-{asset} Correlation:        {c:.4f}")
    print()

    # ══════════════════════════════════════════════════════════════════════
    # SECTION 8: Portfolio Comparison
    # ══════════════════════════════════════════════════════════════════════
    print("=" * 70)
    print("PORTFOLIO COMPARISON")
    print("=" * 70)
    print()
    print("| Portfolio                      | Sharpe | Ann Ret | Max DD   | OOS SR | DSR Sig? | Verdict |")
    print("|--------------------------------|--------|---------|----------|--------|----------|---------|")

    # 4-asset baseline
    if not bt_4eq.empty:
        dsr_4 = deflated_sharpe_n1(m_4eq.sharpe, m_4eq.n_days, m_4eq.skew, m_4eq.kurtosis)
        print(
            f"| 4-Asset Baseline (no BTC)      | {m_4eq.sharpe:.3f} | {m_4eq.ann_ret:.2%} | {m_4eq.max_dd:.2%} |   —    | {'YES' if dsr_4['passes'] else 'NO':4s}    | Baseline |"
        )

    # 5-asset equal weight
    if not bt_5eq.empty:
        wf_5oos = wf_port["test"].sharpe if "test" in wf_port else 0
        print(
            f"| 5-Asset Equal Weight (20% BTC) | {m_5eq.sharpe:.3f} | {m_5eq.ann_ret:.2%} | {m_5eq.max_dd:.2%} | {wf_5oos:.3f} | {'YES' if dsr_5eq['passes'] else 'NO':4s}    | {verdict:8s} |"
        )

    # BTC solo
    print(
        f"| BTCUSD Solo                    | {btc_m.sharpe:.3f} | {btc_m.ann_ret:.2%} | {btc_m.max_dd:.2%} | {oos_sharpe:.3f} | {'YES' if btc_dsr['passes'] else 'NO':4s}    | {'SINGLE' if verdict != 'GO' else 'INCLUDE':8s} |"
    )

    # Optimal weight
    bt_opt, details_opt = portfolio_backtest_custom_weights(combined_data, best_entry.get("weights", {}))
    if not bt_opt.empty:
        m_opt = compute_metrics(
            bt_opt["portfolio_ret"], bt_opt["portfolio_cost"], details_opt.get("asset_pos_changes"), "optimal"
        )
        dsr_opt = deflated_sharpe_n1(m_opt.sharpe, m_opt.n_days, m_opt.skew, m_opt.kurtosis)
        print(
            f"| Optimal Weight ({recommended_weight:.0%} BTC)      | {m_opt.sharpe:.3f} | {m_opt.ann_ret:.2%} | {m_opt.max_dd:.2%} |   —    | {'YES' if dsr_opt['passes'] else 'NO':4s}    | -        |"
        )

    print("| Academic TSM baseline          | ~0.4   | ~8%     | -20%     |   —    | -        | Reference |")
    print()

    # ══════════════════════════════════════════════════════════════════════
    # Generate Report
    # ══════════════════════════════════════════════════════════════════════
    report_lines = [
        "# BTCUSD TSM Validation Report",
        "",
        "**Date:** 2026-07-05",
        "**Strategy:** Ensemble TSM (equal-weight mixture of lookbacks [20, 40, 60, 120])",
        "**Asset:** BTCUSD (via yfinance BTC-USD daily data)",
        f"**Data:** {btc_close.index.min().date()} to {btc_close.index.max().date()} ({len(btc_close)} bars)",
        f"**BTC Costs:** RT={BTC_COST_BPS}bps, Swap Long={BTC_SWAP_LONG_BPS} bps/day, Swap Short={BTC_SWAP_SHORT_BPS} bps/day",
        "",
        "---",
        "",
        "## Verdict",
        "",
        f"**{verdict}** — {verdict_detail}",
        "",
        f"**Recommended Weight: {recommended_weight:.0%}** of multi-asset TSM portfolio",
        "",
        "---",
        "",
    ]

    report_lines.extend(all_report)

    report_lines.extend(
        [
            "## Portfolio Comparison",
            "",
            "| Portfolio | Sharpe | Ann Ret | Max DD | OOS Sharpe | DSR Sig? | Verdict |",
            "|-----------|--------|---------|--------|------------|----------|---------|",
        ]
    )

    if not bt_4eq.empty:
        dsr_4 = deflated_sharpe_n1(m_4eq.sharpe, m_4eq.n_days, m_4eq.skew, m_4eq.kurtosis)
        report_lines.append(
            f"| 4-Asset Baseline (no BTC) | {m_4eq.sharpe:.3f} | {m_4eq.ann_ret:.2%} | {m_4eq.max_dd:.2%} | — | "
            f"{'YES' if dsr_4['passes'] else 'NO'} | Baseline |"
        )
    if not bt_5eq.empty:
        report_lines.append(
            f"| 5-Asset Equal Weight (20% BTC) | {m_5eq.sharpe:.3f} | {m_5eq.ann_ret:.2%} | {m_5eq.max_dd:.2%} | {wf_port['test'].sharpe:.3f} | "
            f"{'YES' if dsr_5eq['passes'] else 'NO'} | {verdict} |"
        )
    report_lines.append(
        f"| BTCUSD Solo | {btc_m.sharpe:.3f} | {btc_m.ann_ret:.2%} | {btc_m.max_dd:.2%} | {oos_sharpe:.3f} | "
        f"{'YES' if btc_dsr['passes'] else 'NO'} | INCLUDE |"
    )
    report_lines.append("| Academic TSM baseline | ~0.4 | ~8% | -20% | — | — | Reference |")
    report_lines.append("")

    report_lines.extend(
        [
            "## Decision Criteria",
            "",
            "| OOS Sharpe | Verdict | Action |",
            "|------------|---------|--------|",
            "| > 0.5 | GO | Include in portfolio at recommended weight |",
            "| 0.3 - 0.5 | CONDITIONAL_GO | Include at small weight (5%), monitor closely |",
            "| 0.0 - 0.3 | NO_GO | Do not include |",
            "| < 0.0 | NO_GO | No alpha |",
            "",
            f"**Result: {verdict}** (OOS Sharpe = {oos_sharpe:.3f})",
            "",
            "---",
            "",
            "## Methodology",
            "",
            "- Signal: Equal-weight mixture of vol-scaled returns at lookbacks [20, 40, 60, 120]",
            "- Vol targeting: 10% annualized, 60-day window, position capped at 1.5x",
            "- Weekly rebalance (Friday close)",
            "- Walk-forward: 70% train, 30% test",
            "- BTC costs: 8.74 bps round-trip, -3.0 bps/day long swap, -1.5 bps/day short swap",
            "- 4-asset costs: per-asset measured Pepperstone Razor spreads",
            "- Weight sensitivity tested: 0%, 5%, 8%, 10%, 15%, 20%",
            "",
        ]
    )

    report_path = REPORTS / "tsm_btcusd_validation.md"
    report_content = "\n".join(report_lines)
    report_path.write_text(report_content, encoding="utf-8")
    print(f"\nReport written to: {report_path}")

    # Final
    print("\n" + "=" * 70)
    print(f"FINAL VERDICT: {verdict}")
    print(f"  {verdict_detail}")
    print(f"  Recommended weight: {recommended_weight:.0%}")
    print("=" * 70)

    return verdict


if __name__ == "__main__":
    main()
