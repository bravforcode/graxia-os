"""Simple text-based live dashboard for quant_os monitoring."""

import time
import os
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional


HEADER = "=" * 60
DIVIDER = "-" * 60


def _fmt_pnl(val: float) -> str:
    sign = "+" if val >= 0 else ""
    return f"{sign}{val:.2f}"


def _fmt_time(ts: Optional[float]) -> str:
    if ts is None:
        return "N/A"
    return time.strftime("%H:%M:%S", time.localtime(ts))


def render_positions(positions: List[Dict[str, Any]]) -> str:
    """Render current positions table."""
    lines = ["  SYMBOL        SIDE    ENTRY      PNL", f"  {DIVIDER[:44]}"]
    if not positions:
        lines.append("  (no open positions)")
    for pos in positions:
        sym = pos.get("symbol", "?")
        side = pos.get("side", "?").upper()
        entry = pos.get("entry_price", 0.0)
        pnl = pos.get("pnl", 0.0)
        lines.append(f"  {sym:<14}{side:<8}{entry:<10.5f}{_fmt_pnl(pnl):>10}")
    return "\n".join(lines)


def render_pnl(pnl: float, win_rate: float, trades_count: int) -> str:
    """Render PnL summary."""
    return (
        f"  Daily PnL:   {_fmt_pnl(pnl)}\n"
        f"  Win Rate:    {win_rate:.1f}%\n"
        f"  Total Trades: {trades_count}"
    )


def render_risk(risk_level: float, exposure: float) -> str:
    """Render risk gauge as text bar."""
    bar_len = int(risk_level / 5)
    bar = "#" * bar_len + "." * (20 - bar_len)
    return (
        f"  Risk Level:  [{bar}] {risk_level:.0f}/100\n"
        f"  Exposure:    {exposure:.2f}"
    )


def render_recent_trades(trades: List[Dict[str, Any]], limit: int = 10) -> str:
    """Render recent trades table."""
    lines = [
        "  TIME     SYMBOL     SIDE  PNL",
        f"  {DIVIDER[:40]}",
    ]
    if not trades:
        lines.append("  (no recent trades)")
    recent = trades[-limit:]
    for t in recent:
        ts = _fmt_time(t.get("timestamp"))
        sym = t.get("symbol", "?")
        side = t.get("side", "?").upper()
        pnl = t.get("pnl", 0.0)
        lines.append(f"  {ts}  {sym:<10}{side:<6}{_fmt_pnl(pnl):>10}")
    return "\n".join(lines)


def render_health(
    feed_status: str = "connected",
    latency_ms: float = 0.0,
    data_age_s: float = 0.0,
    alerts: Optional[List[str]] = None,
) -> str:
    """Render system health section."""
    lines = [
        f"  Feed:        {feed_status}",
        f"  Latency:     {latency_ms:.1f}ms",
        f"  Data Age:    {data_age_s:.1f}s",
    ]
    if alerts:
        lines.append("  ALERTS:")
        for a in alerts:
            lines.append(f"    !! {a}")
    return "\n".join(lines)


def render_dashboard(
    positions: Optional[List[Dict[str, Any]]] = None,
    pnl: float = 0.0,
    win_rate: float = 0.0,
    trades_count: int = 0,
    risk_level: float = 0.0,
    exposure: float = 0.0,
    recent_trades: Optional[List[Dict[str, Any]]] = None,
    feed_status: str = "connected",
    latency_ms: float = 0.0,
    data_age_s: float = 0.0,
    alerts: Optional[List[str]] = None,
) -> str:
    """Render complete dashboard as string."""
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
    parts = [
        HEADER,
        f"  QUANT OS LIVE DASHBOARD  |  {now}",
        HEADER,
        "",
        "  [POSITIONS]",
        render_positions(positions or []),
        "",
        "  [PnL SUMMARY]",
        render_pnl(pnl, win_rate, trades_count),
        "",
        "  [RISK]",
        render_risk(risk_level, exposure),
        "",
        "  [RECENT TRADES]",
        render_recent_trades(recent_trades or []),
        "",
        "  [SYSTEM HEALTH]",
        render_health(feed_status, latency_ms, data_age_s, alerts),
        "",
        HEADER,
    ]
    return "\n".join(parts)


def run_dashboard_loop(
    state_fn,
    interval: float = 5.0,
):
    """Standalone dashboard loop. state_fn() returns a dict with all fields."""
    try:
        while True:
            os.system("cls" if os.name == "nt" else "clear")
            state = state_fn()
            print(render_dashboard(**state))
            time.sleep(interval)
    except KeyboardInterrupt:
        print("\nDashboard stopped.")


if __name__ == "__main__":
    def sample_state():
        return {
            "positions": [
                {"symbol": "XAUUSD", "side": "buy", "entry_price": 2350.50, "pnl": 12.30},
            ],
            "pnl": 45.80,
            "win_rate": 62.5,
            "trades_count": 8,
            "risk_level": 35.0,
            "exposure": 1500.0,
            "recent_trades": [
                {"timestamp": time.time() - 300, "symbol": "XAUUSD", "side": "buy", "pnl": 12.30},
                {"timestamp": time.time() - 600, "symbol": "XAUUSD", "side": "sell", "pnl": -8.50},
            ],
            "feed_status": "connected",
            "latency_ms": 12.5,
            "data_age_s": 3.0,
            "alerts": [],
        }
    run_dashboard_loop(sample_state, interval=2.0)
