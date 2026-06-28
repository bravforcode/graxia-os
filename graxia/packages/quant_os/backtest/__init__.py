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
    try:
        from backtest.data_loader import (
            load_arrow,
            load_csv_data,
            load_mt5_data,
            to_arrow,
        )
        from backtest.engine import BacktestEngine
        from backtest.metrics import BacktestMetrics, calculate_metrics
    except ImportError:
        # Last resort: lazy imports
        def __getattr__(name):
            if name == "BacktestEngine":
                from .engine import BacktestEngine
                return BacktestEngine
            raise AttributeError(f"module {__name__!r} has no attribute {name!r}")

__all__ = [
    "BacktestEngine",
    "calculate_metrics",
    "BacktestMetrics",
    "load_csv_data",
    "load_mt5_data",
    "load_arrow",
    "to_arrow",
]
