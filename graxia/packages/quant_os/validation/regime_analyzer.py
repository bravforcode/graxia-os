from dataclasses import dataclass
from enum import Enum
from typing import Any


class RegimeType(Enum):
    TRENDING_UP = "trending_up"
    TRENDING_DOWN = "trending_down"
    RANGING = "ranging"
    HIGH_VOLATILITY = "high_volatility"
    LOW_VOLATILITY = "low_volatility"
    UNKNOWN = "unknown"


@dataclass
class RegimeSlice:
    regime: RegimeType
    trade_count: int
    win_rate: float
    total_pnl: float
    avg_pnl_per_trade: float
    max_drawdown_pct: float

    def concentration_ratio(self, total_trades: int) -> float:
        return self.trade_count / total_trades if total_trades > 0 else 0


@dataclass
class TradeConcentration:
    """Trade contribution concentration test: no single trade or month dominates."""

    max_single_trade_pnl: float
    max_single_trade_pct_of_total: float
    max_month_pnl: float
    max_month_pct_of_total: float
    gini_coefficient: float

    def passes(self, max_trade_pct: float = 0.30, max_month_pct: float = 0.40) -> tuple[bool, list[str]]:
        issues = []
        if self.max_single_trade_pct_of_total > max_trade_pct:
            issues.append(f"SINGLE_TRADE_DOMINATES:{self.max_single_trade_pct_of_total:.1%}")
        if self.max_month_pct_of_total > max_month_pct:
            issues.append(f"SINGLE_MONTH_DOMINATES:{self.max_month_pct_of_total:.1%}")
        return len(issues) == 0, issues


class RegimeAnalyzer:
    def __init__(self):
        self._slices: list[RegimeSlice] = []

    def classify_bar(self, close_prices: list[float], index: int, lookback: int = 20) -> RegimeType:
        if index < lookback:
            return RegimeType.UNKNOWN

        window = close_prices[index - lookback : index + 1]
        if len(window) < 2:
            return RegimeType.UNKNOWN

        returns = [(window[i] - window[i - 1]) / window[i - 1] for i in range(1, len(window))]
        avg_return = sum(returns) / len(returns)
        volatility = (sum((r - avg_return) ** 2 for r in returns) / len(returns)) ** 0.5

        if volatility > 0.015:
            return RegimeType.HIGH_VOLATILITY
        elif volatility < 0.003:
            return RegimeType.LOW_VOLATILITY
        elif avg_return > 0.001:
            return RegimeType.TRENDING_UP
        elif avg_return < -0.001:
            return RegimeType.TRENDING_DOWN
        else:
            return RegimeType.RANGING

    def add_regime_slice(self, slice_data: RegimeSlice) -> None:
        self._slices.append(slice_data)

    def analyze_trades(self, trades: list[dict], close_prices: list[float]) -> dict[str, Any]:
        """Analyze regime distribution and trade concentration."""
        regime_trades = {r: [] for r in RegimeType}

        for trade in trades:
            bar_idx = trade.get("bar_index", 0)
            regime = self.classify_bar(close_prices, bar_idx)
            regime_trades[regime].append(trade)

        slices = []
        total_trades = len(trades)
        for regime, r_trades in regime_trades.items():
            if not r_trades:
                continue
            pnls = [t.get("pnl", 0) for t in r_trades]
            wins = [p for p in pnls if p > 0]
            slices.append(
                RegimeSlice(
                    regime=regime,
                    trade_count=len(r_trades),
                    win_rate=len(wins) / len(r_trades) if r_trades else 0,
                    total_pnl=sum(pnls),
                    avg_pnl_per_trade=sum(pnls) / len(pnls) if pnls else 0,
                    max_drawdown_pct=0.0,
                )
            )

        self._slices = slices

        # Trade concentration
        pnls = [t.get("pnl", 0) for t in trades]
        total_pnl = sum(abs(p) for p in pnls) if pnls else 1

        max_trade = max(pnls, key=abs) if pnls else 0
        max_trade_pct = abs(max_trade) / total_pnl if total_pnl > 0 else 0

        # Group by month
        monthly = {}
        for t in trades:
            month = t.get("entry_time", "")[:7]
            monthly.setdefault(month, []).append(t.get("pnl", 0))
        month_pnls = {m: sum(p) for m, p in monthly.items()}
        max_month = max(month_pnls.values(), key=abs) if month_pnls else 0
        total_monthly = sum(abs(v) for v in month_pnls.values()) if month_pnls else 1
        max_month_pct = abs(max_month) / total_monthly if total_monthly > 0 else 0

        # Gini coefficient
        sorted_pnls = sorted([abs(p) for p in pnls])
        n = len(sorted_pnls)
        if n == 0:
            gini = 0.0
        else:
            cumulative = sum((2 * (i + 1) - n - 1) * sorted_pnls[i] for i in range(n))
            gini = cumulative / (n * sum(sorted_pnls)) if sum(sorted_pnls) > 0 else 0

        concentration = TradeConcentration(
            max_single_trade_pnl=max_trade,
            max_single_trade_pct_of_total=max_trade_pct,
            max_month_pnl=max_month,
            max_month_pct_of_total=max_month_pct,
            gini_coefficient=gini,
        )

        return {
            "slices": slices,
            "concentration": concentration,
            "total_trades": total_trades,
        }

    def get_slices(self) -> list[RegimeSlice]:
        return self._slices
