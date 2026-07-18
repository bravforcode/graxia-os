"""
Core paper execution engine — runs one campaign, simulates trades, computes P&L.
"""

from __future__ import annotations

import importlib.util
import math
from datetime import UTC, datetime

import numpy as np
import pandas as pd

# Lazy import: validation.walk_forward has broken __init__.py chain
_wfa_split = None

def _get_wfa_split():
    global _wfa_split
    if _wfa_split is None:
        # Bypass broken validation/__init__.py by loading module directly from file
        import importlib.util as _iu
        import os as _os
        import sys as _sys
        _wf_path = _os.path.join(_os.path.dirname(_os.path.dirname(__file__)), "validation", "walk_forward.py")
        _spec = _iu.spec_from_file_location("validation.walk_forward", _wf_path)
        if _spec and _spec.origin:
            _mod = _iu.module_from_spec(_spec)
            # Register in sys.modules so dataclass decorators work
            _sys.modules["validation.walk_forward"] = _mod
            _spec.loader.exec_module(_mod)
            _wfa_split = _mod.walk_forward_split
        else:
            raise ImportError("Cannot load validation.walk_forward")
    return _wfa_split

from .campaign import CampaignConfig, get_param_grid
from .price_feed import load_ohlcv
from .strategies.base import BaseStrategy, Signal, StrategyResult
from .strategies.donchian import DonchianStrategy
from .strategies.mrb import MRBStrategy
from .strategies.rsi_bb import RSIBBStrategy
from .strategies.tsm import TSMStrategy
from .strategies.volume_breakout import VolumeBreakoutStrategy

# Gold ICT strategies (lazy — may not be available)
_gold_ict_registry = {}
try:
    from .strategies.gold_ict import GOLD_ICT_REGISTRY
    _gold_ict_registry = GOLD_ICT_REGISTRY
except ImportError:
    pass


def _get_strategy(strategy_id: str) -> BaseStrategy:
    """Factory: get strategy instance by id."""
    registry = {
        "tsm": TSMStrategy,
        "rsi_bb": RSIBBStrategy,
        "donchian": DonchianStrategy,
        "volume_breakout": VolumeBreakoutStrategy,
        "mrb": MRBStrategy,
    }
    # Merge gold_bot strategies
    registry.update(_gold_ict_registry)
    cls = registry.get(strategy_id)
    if cls is None:
        raise ValueError(f"Unknown strategy: {strategy_id}. Available: {list(registry.keys())}")
    return cls()


def _trades_per_year(trades: list) -> float:
    """Compute average trades per year from trade timestamps.

    Works with both Trade objects (entry_time/exit_time strings) and
    dicts from trades_json (entry_time/exit_time strings).

    Returns 252 as fallback if timestamps are missing or invalid.
    """
    if len(trades) < 2:
        return 252.0

    # Get first entry_time and last exit_time
    def _get_time(trade, field: str) -> str | None:
        if isinstance(trade, dict):
            return trade.get(field)
        return getattr(trade, field, None)

    first_entry = _get_time(trades[0], "entry_time")
    last = trades[-1]
    last_exit = _get_time(last, "exit_time") or _get_time(last, "entry_time")

    if not first_entry or not last_exit:
        return 252.0

    try:
        t_start = pd.Timestamp(first_entry)
        t_end = pd.Timestamp(last_exit)
        time_span_years = (t_end - t_start).total_seconds() / (365.25 * 86400)
        if time_span_years < 1 / 365.25:
            return 252.0
        return len(trades) / time_span_years
    except Exception:
        return 252.0


def _point_value(symbol: str, lot_size: float) -> float:
    """Dollar P&L per 1-point price move for given lot size.

    Standard contract sizes (MT5):
      forex:  1 lot = 100,000 units → $1/pip per 0.01 lot
      XAUUSD: 1 lot = 100 oz       → $1/point per 0.01 lot
      XAGUSD: 1 lot = 5000 oz      → $50/point per 0.01 lot
      OIL:    1 lot = 1000 barrels → $10/point per 0.01 lot
      indices: 1 lot = $1/point    → $0.01/point per 0.01 lot
    """
    sym = symbol.upper()
    lots = lot_size

    if "XAU" in sym or "GOLD" in sym:
        return lots * 100  # 1 lot = 100 oz
    elif "XAG" in sym or "SILVER" in sym:
        return lots * 5000  # 1 lot = 5000 oz
    elif "OIL" in sym or "CL=F" in sym or "BRENT" in sym or "BZ=F" in sym:
        return lots * 1000  # 1 lot = 1000 barrels
    elif "NAS" in sym or "NDX" in sym or "IXIC" in sym:
        return lots * 1  # index: $1/point per lot
    elif "US30" in sym or "DJI" in sym or "SPX" in sym or "GSPC" in sym:
        return lots * 1
    elif "BTC" in sym:
        return lots * 1  # 1 lot = 1 BTC (varies by broker)
    elif "ETH" in sym:
        return lots * 1
    else:
        # forex: 1 lot = 100,000 → $10/pip per lot = $0.10 per 0.01 lot
        return lots * 100000


class Trade:
    """Simulated trade with full P&L."""

    def __init__(
        self,
        signal: Signal,
        capital: float,
        risk_pct: float,
        commission_bps: float,
        slippage_bps: float,
        symbol: str = "",
        spread_bps: float = 0.0,
    ):
        self.signal = signal
        self.entry_time = signal.timestamp
        self.direction = signal.direction
        self.entry_price = signal.entry_price
        self.stop_loss = signal.stop_loss
        self.take_profit = signal.take_profit
        self.confidence = signal.confidence
        self.symbol = symbol
        self.entry_bar_idx: int | None = signal.bar_index + 1 if signal.bar_index is not None else None

        # Position sizing based on risk + stop distance
        self.risk_amount = capital * risk_pct / 100.0
        self.position_size = self._calc_position_size()
        self.point_value = _point_value(symbol, self.position_size)
        self.commission_bps = commission_bps
        self.slippage_bps = slippage_bps
        self.spread_bps = spread_bps

        # Exit info (filled after simulation)
        self.exit_time: str | None = None
        self.exit_price: float | None = None
        self.exit_reason: str = ""
        self.gross_pnl: float = 0.0
        self.net_pnl: float = 0.0
        self.commission_paid: float = 0.0
        self.holding_bars: int = 0

    def _calc_position_size(self) -> float:
        """Position sizing: risk_amount / (stop_distance * point_value_per_lot).

        For XAUUSD with $1000 risk, $100 stop:
          lots = 1000 / (100 * 100) = 0.10 lot
          P&L for $50 move = 50 * 0.10 * 100 = $500 ✓
        """
        stop_dist = 0.0
        if self.stop_loss and self.entry_price:
            stop_dist = abs(self.entry_price - self.stop_loss)
        if stop_dist < 1e-10:
            return 0.01

        pv_per_lot = _point_value(self.symbol, 1.0)
        if pv_per_lot < 1e-10:
            return 0.01

        lots = self.risk_amount / (stop_dist * pv_per_lot)
        return max(0.01, round(lots, 2))

    def close(self, exit_price: float, exit_time: str, reason: str = "signal") -> float:
        """Close trade, return net P&L.

        P&L = price_diff × lot_size × point_value_per_lot
        Cost = per-lot RT commission + slippage (bps on price movement)
        """
        self.exit_price = exit_price
        self.exit_time = exit_time
        self.exit_reason = reason

        price_diff = exit_price - self.entry_price if self.direction == 1 else self.entry_price - exit_price
        self.gross_pnl = price_diff * self.point_value

        # Commission: per-lot flat rate (broker model)
        # Pepperstone Razor: ~$3.50/lot RT for forex, ~$7/lot RT for metals
        lots = self.point_value / _point_value(self.symbol, 1.0) if _point_value(self.symbol, 1.0) > 0 else 0.01
        is_metal = "XAU" in self.symbol.upper() or "XAG" in self.symbol.upper()
        commission_per_lot = 7.0 if is_metal else 3.5
        flat_commission = lots * commission_per_lot

        # Slippage: bps on trade value (half on entry, half on exit)
        price_slippage = abs(self.entry_price * self.slippage_bps / 10000) + abs(exit_price * self.slippage_bps / 10000)
        slippage_cost = price_slippage * self.point_value
        self.commission_paid = flat_commission + slippage_cost

        # Spread cost: bid-ask spread on both entry and exit (yfinance uses mid-price)
        spread_cost = 0.0
        if self.spread_bps > 0:
            spread_entry = abs(self.entry_price * self.spread_bps / 20000)  # half-spread
            spread_exit = abs(exit_price * self.spread_bps / 20000)  # half-spread
            spread_cost = (spread_entry + spread_exit) * self.point_value
            self.commission_paid += spread_cost

        self.net_pnl = self.gross_pnl - self.commission_paid

        return self.net_pnl

    def to_dict(self) -> dict:
        return {
            "entry_time": self.entry_time,
            "exit_time": self.exit_time,
            "direction": "LONG" if self.direction == 1 else "SHORT",
            "entry_price": self.entry_price,
            "exit_price": self.exit_price,
            "stop_loss": self.stop_loss,
            "take_profit": self.take_profit,
            "position_size": round(self.position_size, 2),
            "confidence": self.confidence,
            "gross_pnl": round(self.gross_pnl, 2),
            "commission": round(self.commission_paid, 2),
            "net_pnl": round(self.net_pnl, 2),
            "exit_reason": self.exit_reason,
            "holding_bars": self.holding_bars,
            "spread_bps": self.spread_bps,
        }


class CampaignResult:
    """Complete results from running one campaign."""

    def __init__(self, config: CampaignConfig):
        self.config = config
        self.trades: list[Trade] = []
        self.equity_curve: list[dict] = []
        self.start_time: str = ""
        self.end_time: str = ""
        self.data_bars: int = 0
        self.error: str | None = None
        self.metrics: dict = {}

    def compute_metrics(self) -> dict:
        """Calculate performance metrics."""
        if not self.trades:
            self.metrics = {
                "strategy": self.config.strategy_id,
                "symbol": self.config.symbol,
                "timeframe": self.config.timeframe,
                "total_trades": 0,
                "error": "No trades generated",
            }
            return self.metrics

        pnls = np.array([t.net_pnl for t in self.trades])
        gross_pnls = np.array([t.gross_pnl for t in self.trades])
        wins = pnls > 0
        losses = pnls < 0
        total_pnl = float(np.sum(pnls))
        total_gross = float(np.sum(gross_pnls))
        total_commission = float(np.sum([t.commission_paid for t in self.trades]))
        n = len(pnls)

        win_rate = float(np.mean(wins)) * 100 if n > 0 else 0.0
        avg_win = float(np.mean(pnls[wins])) if np.any(wins) else 0.0
        avg_loss = float(np.mean(pnls[losses])) if np.any(losses) else 0.0
        profit_factor = abs(float(np.sum(pnls[wins]) / np.sum(pnls[losses]))) if np.any(losses) and np.sum(pnls[losses]) != 0 else float("inf")

        # Sharpe — frequency-corrected annualization
        returns = pnls / 100000  # per-trade return as fraction of capital
        tpy = _trades_per_year(self.trades)
        sharpe = float(np.mean(returns) / np.std(returns) * np.sqrt(tpy)) if np.std(returns) > 1e-10 else 0.0

        # Max drawdown
        cumulative = np.cumsum(pnls)
        running_max = np.maximum.accumulate(cumulative)
        drawdowns = running_max - cumulative
        max_dd = float(np.max(drawdowns)) if len(drawdowns) > 0 else 0.0
        max_dd_pct = float(max_dd / (100000 + cumulative[0]) * 100) if len(cumulative) > 0 else 0.0

        self.metrics = {
            "strategy": self.config.strategy_id,
            "symbol": self.config.symbol,
            "timeframe": self.config.timeframe,
            "total_trades": n,
            "total_pnl": round(total_pnl, 2),
            "total_gross_pnl": round(total_gross, 2),
            "total_commission": round(total_commission, 2),
            "win_rate_pct": round(win_rate, 1),
            "avg_win": round(avg_win, 2),
            "avg_loss": round(avg_loss, 2),
            "profit_factor": round(profit_factor, 2),
            "sharpe": round(sharpe, 3),
            "max_drawdown": round(max_dd, 2),
            "max_drawdown_pct": round(max_dd_pct, 2),
            "avg_confidence": round(float(np.mean([t.confidence for t in self.trades])), 3),
            "data_bars": self.data_bars,
        }
        return self.metrics

    def to_dict(self) -> dict:
        return {
            "campaign_id": self.config.campaign_id,
            "config": self.config.to_dict(),
            "trades": [t.to_dict() for t in self.trades],
            "metrics": self.metrics,
            "start_time": self.start_time,
            "end_time": self.end_time,
            "data_bars": self.data_bars,
            "error": self.error,
        }


def _simulate_trades(
    strategy_result: StrategyResult,
    df: pd.DataFrame,
    config: CampaignConfig,
) -> tuple[list[Trade], list[dict]]:
    """Simulate trades from a strategy's signals — next-bar execution.

    Signal at bar[i] executes at close[i+1]. SL/TP checked against high[i+1]/low[i+1].
    Extracted from run_campaign() so walk-forward validation can reuse the identical
    simulation logic (no drift between in-sample and OOS execution).
    """
    closes = df["close"].values.astype(float)
    highs = df["high"].values.astype(float)
    lows = df["low"].values.astype(float)
    n = len(closes)

    trades: list[Trade] = []
    equity_curve: list[dict] = []
    capital = config.capital
    open_trade: Trade | None = None
    sym = config.symbol

    for signal in strategy_result.signals:
        idx = signal.bar_index
        if idx is None or idx + 1 >= n:
            continue  # no next bar available — skip signal

        if open_trade is None:
            # OPEN: execute at NEXT bar's close
            if signal.direction == 0:
                continue
            entry_price = closes[idx + 1]
            open_trade = Trade(
                signal=signal,
                capital=capital,
                risk_pct=config.risk_per_trade_pct,
                commission_bps=config.commission_bps,
                slippage_bps=config.slippage_bps,
                symbol=sym,
                spread_bps=config.spread_bps,
            )
            open_trade.entry_price = entry_price  # override with next-bar price
            open_trade.entry_time = str(df.index[idx + 1])
        else:
            # Check SL/TP on next bar before checking signal
            sl_tp_hit = False
            if open_trade.direction == 1:
                if open_trade.stop_loss and lows[idx + 1] <= open_trade.stop_loss:
                    pnl = open_trade.close(open_trade.stop_loss, str(df.index[idx + 1]), "stop_loss")
                    capital += pnl
                    trades.append(open_trade)
                    equity_curve.append({"time": str(df.index[idx + 1]), "equity": capital, "pnl": pnl})
                    sl_tp_hit = True
                elif open_trade.take_profit and highs[idx + 1] >= open_trade.take_profit:
                    pnl = open_trade.close(open_trade.take_profit, str(df.index[idx + 1]), "take_profit")
                    capital += pnl
                    trades.append(open_trade)
                    equity_curve.append({"time": str(df.index[idx + 1]), "equity": capital, "pnl": pnl})
                    sl_tp_hit = True
            elif open_trade.direction == -1:
                if open_trade.stop_loss and highs[idx + 1] >= open_trade.stop_loss:
                    pnl = open_trade.close(open_trade.stop_loss, str(df.index[idx + 1]), "stop_loss")
                    capital += pnl
                    trades.append(open_trade)
                    equity_curve.append({"time": str(df.index[idx + 1]), "equity": capital, "pnl": pnl})
                    sl_tp_hit = True
                elif open_trade.take_profit and lows[idx + 1] <= open_trade.take_profit:
                    pnl = open_trade.close(open_trade.take_profit, str(df.index[idx + 1]), "take_profit")
                    capital += pnl
                    trades.append(open_trade)
                    equity_curve.append({"time": str(df.index[idx + 1]), "equity": capital, "pnl": pnl})
                    sl_tp_hit = True

            if sl_tp_hit:
                open_trade = None
                # If signal also has a new direction, open at next bar
                if signal.direction in (1, -1):
                    entry_price = closes[idx + 1]
                    open_trade = Trade(
                        signal=signal,
                        capital=capital,
                        risk_pct=config.risk_per_trade_pct,
                        commission_bps=config.commission_bps,
                        slippage_bps=config.slippage_bps,
                        symbol=sym,
                        spread_bps=config.spread_bps,
                    )
                    open_trade.entry_price = entry_price
                    open_trade.entry_time = str(df.index[idx + 1])
                continue

            # Signal-based close: exit at NEXT bar's close
            if signal.direction == 0 or signal.direction != open_trade.direction:
                exit_price = closes[idx + 1]
                pnl = open_trade.close(exit_price, str(df.index[idx + 1]), signal.reason)
                capital += pnl
                trades.append(open_trade)
                equity_curve.append({"time": str(df.index[idx + 1]), "equity": capital, "pnl": pnl})
                open_trade = None

                # Open new trade if direction changed — also at next bar
                if signal.direction in (1, -1):
                    entry_price = closes[idx + 1]
                    open_trade = Trade(
                        signal=signal,
                        capital=capital,
                        risk_pct=config.risk_per_trade_pct,
                        commission_bps=config.commission_bps,
                        slippage_bps=config.slippage_bps,
                        symbol=sym,
                        spread_bps=config.spread_bps,
                    )
                    open_trade.entry_price = entry_price
                    open_trade.entry_time = str(df.index[idx + 1])

    # Close any remaining open trade at last bar
    if open_trade is not None:
        last_close = closes[-1]
        last_time = str(df.index[-1])
        pnl = open_trade.close(last_close, last_time, "end_of_data")
        capital += pnl
        trades.append(open_trade)
        equity_curve.append({"time": last_time, "equity": capital, "pnl": pnl})

    return trades, equity_curve


def run_campaign(config: CampaignConfig) -> CampaignResult:
    """Run a single campaign — the core execution function.

    This is the function that gets parallelised.

    IMPORTANT: Uses next-bar execution to avoid look-ahead bias.
    Signal at bar[i] executes at close[i+1].
    SL/TP checked against high[i+1]/low[i+1].
    """
    result = CampaignResult(config)
    result.start_time = datetime.now(UTC).isoformat()

    try:
        # 1. Load data
        df = load_ohlcv(config.symbol, config.timeframe)
        if df is None or len(df) < 100:
            result.error = f"Insufficient data for {config.symbol} {config.timeframe}"
            result.end_time = datetime.now(UTC).isoformat()
            return result

        result.data_bars = len(df)

        # 2. Run strategy
        strategy = _get_strategy(config.strategy_id)
        strategy_result = strategy.generate_signals(df, config.params)

        if not strategy_result.signals:
            result.error = "No signals generated"
            result.end_time = datetime.now(UTC).isoformat()
            return result

        # 3. Simulate trades — next-bar execution
        result.trades, result.equity_curve = _simulate_trades(strategy_result, df, config)

        # 4. Compute metrics
        result.compute_metrics()

    except Exception as e:
        result.error = str(e)

    result.end_time = datetime.now(UTC).isoformat()
    return result


def _sharpe_from_trades(trades: list[Trade]) -> float:
    """Frequency-corrected Sharpe from a trade subset."""
    if len(trades) < 2:
        return -float("inf")
    pnls = np.array([t.net_pnl for t in trades])
    returns = pnls / 100000
    std = np.std(returns)
    if std <= 1e-10:
        return -float("inf")
    tpy = _trades_per_year(trades)
    return float(np.mean(returns) / std * np.sqrt(tpy))


def _permutation_dsr(trades: list[Trade], n_perms: int = 2000, seed: int = 42) -> dict:
    """Per-campaign permutation test (sign-flipping) — same methodology as
    paper_engine/analyzer.py's DSR correction, applied to a single trade set (here: OOS trades).

    Builds a null distribution of Sharpe by randomly flipping the sign of each trade's net P&L
    (B=n_perms times), then reports observed Sharpe's p-value against that null. `dsr` is defined
    as 1 - p_value, matching analyzer.py's convention (not a literal Bailey/Lopez de Prado DSR
    formula, but the same "deflate for multiple testing / by-chance" correction already in use
    elsewhere in this codebase for consistency).
    """
    if len(trades) <= 3:
        return {"dsr": 0.0, "permutation_p": 1.0, "null_95": None, "null_99": None}

    pnls = np.array([t.net_pnl for t in trades])
    observed_sharpe = _sharpe_from_trades(trades)
    if observed_sharpe == -float("inf"):
        return {"dsr": 0.0, "permutation_p": 1.0, "null_95": None, "null_99": None}

    tpy = _trades_per_year(trades)
    rng = np.random.default_rng(seed)
    null_sharpes = []
    for _ in range(n_perms):
        signs = rng.choice([-1, 1], size=len(pnls))
        flipped = pnls * signs
        s_std = flipped.std(ddof=1)
        if s_std > 1e-10:
            null_sharpes.append(float(flipped.mean() / s_std * np.sqrt(tpy)))

    if not null_sharpes:
        return {"dsr": 0.0, "permutation_p": 1.0, "null_95": None, "null_99": None}

    null_arr = np.array(null_sharpes)
    p_value = float(np.mean(null_arr >= observed_sharpe))
    return {
        "dsr": round(1.0 - p_value, 4),
        "permutation_p": round(p_value, 4),
        "null_95": round(float(np.percentile(null_arr, 95)), 3),
        "null_99": round(float(np.percentile(null_arr, 99)), 3),
    }


def run_campaign_wfa(
    config: CampaignConfig,
    n_splits: int = 5,
    embargo_bars: int = 12,
    min_train_trades: int = 5,
) -> dict:
    """Walk-forward validation for a campaign — addresses the "100% in-sample" hole.

    For each fold: grid-search the strategy's param combos (the SAME fixed grid used
    at campaign-generation time in campaign.py — no new optimizer) scored by Sharpe on
    that fold's train-window trades only, then evaluate the winning combo's trades that
    fall in the test window. OOS trades are stitched across folds and scored once.

    Each param combo's signals/trades are simulated ONCE over the full history (indicators
    are strictly backward-looking — see BaseStrategy.compute_atr — so fold boundaries can't
    leak into them), then trades are bucketed into train/test per fold by entry bar index.
    This reuses run_campaign()'s exact simulation logic and campaign.py's exact param grid,
    rather than building new fitting infrastructure.
    """
    df = load_ohlcv(config.symbol, config.timeframe)
    if df is None or len(df) < 100:
        return {"campaign_id": config.campaign_id, "error": f"Insufficient data for {config.symbol} {config.timeframe}"}

    n = len(df)
    splits = _get_wfa_split()(n, n_folds=n_splits, train_ratio=0.7, embargo_bars=embargo_bars)
    if not splits:
        return {"campaign_id": config.campaign_id, "error": "Not enough bars for requested wfa_splits"}

    grid = get_param_grid(config.strategy_id)
    strategy = _get_strategy(config.strategy_id)

    # One simulation per grid combo over the full series — reused across all folds.
    combo_trades: list[list[Trade]] = []
    for params in grid:
        sr = strategy.generate_signals(df, params)
        trades, _ = _simulate_trades(sr, df, config) if sr.signals else ([], [])
        combo_trades.append(trades)

    fold_reports = []
    oos_trades: list[Trade] = []

    for (train_start, train_end), (test_start, test_end) in splits:
        best_idx, best_sharpe = None, -float("inf")
        for combo_idx, trades in enumerate(combo_trades):
            train_trades = [t for t in trades if t.entry_bar_idx is not None and train_start <= t.entry_bar_idx < train_end]
            if len(train_trades) < min_train_trades:
                continue
            sharpe = _sharpe_from_trades(train_trades)
            if sharpe > best_sharpe:
                best_sharpe, best_idx = sharpe, combo_idx

        if best_idx is None:
            fold_reports.append({
                "train_range": [train_start, train_end], "test_range": [test_start, test_end],
                "skipped": f"no combo reached {min_train_trades} train trades",
            })
            continue

        test_trades = [
            t for t in combo_trades[best_idx]
            if t.entry_bar_idx is not None and test_start <= t.entry_bar_idx < test_end
        ]
        fold_reports.append({
            "train_range": [train_start, train_end],
            "test_range": [test_start, test_end],
            "chosen_params": grid[best_idx],
            "train_sharpe": round(best_sharpe, 3),
            "test_trades": len(test_trades),
        })
        oos_trades.extend(test_trades)

    oos_trades.sort(key=lambda t: t.entry_bar_idx or 0)
    oos_result = CampaignResult(config)
    oos_result.trades = oos_trades
    oos_result.data_bars = n
    oos_metrics = oos_result.compute_metrics()
    oos_metrics.update(_permutation_dsr(oos_trades))

    return {
        "campaign_id": config.campaign_id,
        "strategy_id": config.strategy_id,
        "symbol": config.symbol,
        "timeframe": config.timeframe,
        "data_bars": n,
        "wfa_splits_requested": n_splits,
        "wfa_folds_used": sum(1 for f in fold_reports if "skipped" not in f),
        "param_grid_size": len(grid),
        "folds": fold_reports,
        "oos_metrics": oos_metrics,
        "note": (
            "Params re-selected per fold via grid search on train-window trades (same grid "
            "campaign.py uses to assign fixed params); oos_metrics computed only from "
            "test-window trades stitched across folds — no in-sample leakage."
        ),
    }
