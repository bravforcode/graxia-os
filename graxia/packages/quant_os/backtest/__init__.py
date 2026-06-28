"""Backtesting module for Quant OS"""

try:
    from .data_loader import (
        load_arrow,
        load_csv_data,
        load_mt5_data,
        to_arrow,
    )
    from .engine import BacktestEngine
    from .metrics import BacktestMetrics, calculate_metrics
except ImportError:
    from backtest.data_loader import (
        load_arrow,
        load_csv_data,
        load_mt5_data,
        to_arrow,
    )
    from backtest.engine import BacktestEngine
    from backtest.metrics import BacktestMetrics, calculate_metrics

__all__ = [
    "BacktestEngine",
    "calculate_metrics",
    "BacktestMetrics",
    "load_csv_data",
    "load_mt5_data",
    "load_arrow",
    "to_arrow",
]
