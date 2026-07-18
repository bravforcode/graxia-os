"""Prometheus metrics exporter for quant_os."""

import time as _time

from prometheus_client import REGISTRY, Counter, Gauge, Histogram, start_http_server


def _get_or_create(metric_cls, name, doc, labelnames=()):
    """Get existing metric from registry or create a new one.

    prometheus_client stores the base name (e.g. 'quant_os_trades' for
    'quant_os_trades_total'). We check both the given name and strip
    the common suffixes to find existing metrics.
    """
    # Direct lookup
    if name in REGISTRY._names_to_collectors:
        return REGISTRY._names_to_collectors[name]
    # Strip _total suffix (Counter/Histogram add this automatically)
    if name.endswith("_total") and name[:-6] in REGISTRY._names_to_collectors:
        return REGISTRY._names_to_collectors[name[:-6]]
    return metric_cls(name, doc, labelnames)


# Define metrics
TRADES_TOTAL = _get_or_create(Counter, "quant_os_trades_total", "Total trades executed", ["symbol", "side"])
DAILY_PNL = _get_or_create(Gauge, "quant_os_daily_pnl", "Daily P&L in USD")
WIN_RATE = _get_or_create(Gauge, "quant_os_win_rate", "Current win rate")
OPEN_POSITIONS = _get_or_create(Gauge, "quant_os_open_positions", "Number of open positions")
DRAWDOWN = _get_or_create(Gauge, "quant_os_drawdown_pct", "Current drawdown percentage")
KILL_SWITCH = _get_or_create(Gauge, "quant_os_kill_switch_active", "Kill switch state (1=active)")
EXECUTION_LATENCY = _get_or_create(Histogram, "quant_os_execution_latency_seconds", "Order execution latency")
HEARTBEAT_TIMESTAMP = _get_or_create(Gauge, "quant_os_heartbeat_timestamp", "Last heartbeat UNIX timestamp")
MODEL_STALENESS = _get_or_create(Gauge, "quant_os_model_staleness_seconds", "Seconds since model was last retrained")
TSM_LAST_DATA_TIMESTAMP = _get_or_create(
    Gauge, "quant_os_tsm_last_data_timestamp", "Last data feed UNIX timestamp", ["portfolio"]
)
TSM_LAST_REBALANCE_TIMESTAMP = _get_or_create(
    Gauge, "quant_os_tsm_last_rebalance_timestamp", "Last rebalance UNIX timestamp", ["portfolio"]
)

_metrics_started = False


def start_metrics_server(port: int = 9090):
    """Start Prometheus metrics HTTP server."""
    global _metrics_started
    if not _metrics_started:
        try:
            start_http_server(port)
            _metrics_started = True
        except Exception:
            pass


def record_trade(symbol: str, side: str, pnl: float):
    """Record a trade."""
    TRADES_TOTAL.labels(symbol=symbol, side=side).inc()
    DAILY_PNL.set(pnl)


def update_win_rate(rate: float):
    WIN_RATE.set(rate)


def update_positions(count: int):
    OPEN_POSITIONS.set(count)


def update_drawdown(pct: float):
    DRAWDOWN.set(pct)


def update_kill_switch(active: bool):
    KILL_SWITCH.set(1 if active else 0)


def update_heartbeat_timestamp():
    """Set heartbeat timestamp to current time."""
    HEARTBEAT_TIMESTAMP.set(_time.time())


def update_rebalance_timestamp(portfolio: str = "tsm"):
    """Set last rebalance timestamp to current time."""
    TSM_LAST_REBALANCE_TIMESTAMP.labels(portfolio=portfolio).set(_time.time())


def update_data_feed_timestamp(portfolio: str = "tsm"):
    """Set last data feed timestamp to current time."""
    TSM_LAST_DATA_TIMESTAMP.labels(portfolio=portfolio).set(_time.time())
