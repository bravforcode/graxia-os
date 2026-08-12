"""Monitor paper trades — P&L computation, risk limit checks, Telegram alerts.

Reads MT5 deal history (or paper trade log CSV), computes daily P&L,
checks risk limits, and sends alerts via Telegram if configured.
Saves daily reports to reports/paper_trades/.

Usage:
    python scripts/monitor_paper_trades.py                # daily report
    python scripts/monitor_paper_trades.py --live         # continuous monitoring
    python scripts/monitor_paper_trades.py --check-risk   # risk limit check only
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
import time
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from pathlib import Path

# ── Paths ─────────────────────────────────────────────────────────────

SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = SCRIPT_DIR.parent
REPORTS_DIR = PROJECT_ROOT / "reports" / "paper_trades"
CONFIG_PATH = PROJECT_ROOT / "config" / "paper_trade_config.json"
TRADE_LOG_PATH = PROJECT_ROOT / "data" / "paper_trade_log.csv"
STATE_PATH = PROJECT_ROOT / "data" / "monitor_state.json"
TELEGRAM_CONFIG = PROJECT_ROOT / "scripts" / "telegram_config.toml"

# ── Logging ───────────────────────────────────────────────────────────

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    stream=sys.stdout,
)
logger = logging.getLogger(__name__)

# Load .env
try:
    from dotenv import load_dotenv

    load_dotenv(PROJECT_ROOT / ".env")
except ImportError:
    pass


# ── Telegram helper ───────────────────────────────────────────────────


def send_telegram(text: str) -> bool:
    """Send message via Telegram if configured."""
    try:
        import tomllib

        import requests
    except ImportError:
        return False

    if not TELEGRAM_CONFIG.exists():
        return False

    try:
        with open(TELEGRAM_CONFIG, "rb") as f:
            cfg = tomllib.load(f)
        token = cfg.get("bot_token", "")
        chat_id = cfg.get("chat_id", "")
        if not token or token == "YOUR_BOT_TOKEN":
            return False
        url = f"https://api.telegram.org/bot{token}/sendMessage"
        r = requests.post(url, json={"chat_id": chat_id, "text": text, "parse_mode": "HTML"}, timeout=15)
        return r.ok
    except Exception as e:
        logger.warning("Telegram send failed: %s", e)
        return False


# ── Data loading ──────────────────────────────────────────────────────


def load_paper_trade_log() -> list[dict]:
    """Load paper trade log from CSV (paper_trade_bot.py format)."""
    if not TRADE_LOG_PATH.exists():
        logger.warning("No trade log at %s", TRADE_LOG_PATH)
        return []

    import pandas as pd

    try:
        df = pd.read_csv(TRADE_LOG_PATH)
        return df.to_dict("records")
    except Exception as e:
        logger.error("Failed to read trade log: %s", e)
        return []


def load_config() -> dict:
    """Load paper trade config, defaults if missing."""
    if CONFIG_PATH.exists():
        with open(CONFIG_PATH) as f:
            return json.load(f)
    return {
        "risk": {
            "max_risk_per_trade_pct": 1.0,
            "max_daily_loss_pct": 2.0,
            "max_drawdown_pct": 10.0,
            "initial_capital": 10000.0,
        },
        "alerts": {
            "alert_on_risk_breach": True,
            "alert_on_daily_summary": True,
            "drawdown_warning_threshold_pct": 5.0,
        },
    }


# ── MT5 deal history ─────────────────────────────────────────────────


def load_mt5_deals() -> list[dict]:
    """Try to read deal history from MT5. Returns list of deal dicts."""
    try:
        import MetaTrader5 as mt5
    except ImportError:
        return []

    try:
        if not mt5.initialize():
            logger.warning("MT5 not initialized — skipping deal history")
            return []

        now = datetime.now(UTC)
        from_date = now - timedelta(days=30)
        deals = mt5.history_deals_get(from_date, now)
        if deals is None:
            return []

        result = []
        for d in deals:
            result.append(
                {
                    "ticket": d.ticket,
                    "time": datetime.fromtimestamp(d.time, tz=UTC).isoformat(),
                    "type": "BUY" if d.type == 0 else "SELL" if d.type == 1 else str(d.type),
                    "symbol": d.symbol,
                    "volume": d.volume,
                    "price": d.price,
                    "profit": d.profit,
                    "swap": d.swap,
                    "commission": d.commission,
                    "magic": d.magic,
                }
            )
        return result
    except Exception as e:
        logger.warning("MT5 deal fetch failed: %s", e)
        return []


# ── P&L computation ──────────────────────────────────────────────────


@dataclass
class DailyPnL:
    date: str
    trades: int
    wins: int
    losses: int
    total_pnl: float
    realized_pnl: float
    unrealized_pnl: float
    win_rate: float
    max_drawdown_pct: float
    equity_high: float
    equity_current: float
    risk_breaches: list[str] = field(default_factory=list)


def compute_daily_pnl(
    trades: list[dict],
    initial_capital: float = 10000.0,
) -> DailyPnL:
    """Compute daily P&L summary from trade records."""
    today = datetime.now(UTC).strftime("%Y-%m-%d")
    today_trades = [t for t in trades if t.get("time", "")[:10] == today]

    if not today_trades:
        return DailyPnL(
            date=today,
            trades=0,
            wins=0,
            losses=0,
            total_pnl=0.0,
            realized_pnl=0.0,
            unrealized_pnl=0.0,
            win_rate=0.0,
            max_drawdown_pct=0.0,
            equity_high=initial_capital,
            equity_current=initial_capital,
        )

    realized = sum(float(t.get("profit", 0)) for t in today_trades)
    wins = sum(1 for t in today_trades if float(t.get("profit", 0)) > 0)
    losses = sum(1 for t in today_trades if float(t.get("profit", 0)) < 0)
    total = len(today_trades)
    win_rate = wins / total if total > 0 else 0.0

    equity = initial_capital + realized
    drawdown_pct = max(0, (initial_capital - equity) / initial_capital * 100) if equity < initial_capital else 0.0

    return DailyPnL(
        date=today,
        trades=total,
        wins=wins,
        losses=losses,
        total_pnl=realized,
        realized_pnl=realized,
        unrealized_pnl=0.0,
        win_rate=win_rate,
        max_drawdown_pct=drawdown_pct,
        equity_high=initial_capital,
        equity_current=equity,
    )


# ── Risk limit checks ────────────────────────────────────────────────


@dataclass
class RiskCheckResult:
    daily_loss_ok: bool = True
    drawdown_ok: bool = True
    position_count_ok: bool = True
    max_positions_ok: bool = True
    messages: list[str] = field(default_factory=list)


def check_risk_limits(
    daily_pnl: DailyPnL,
    risk_config: dict,
    open_positions: int = 0,
) -> RiskCheckResult:
    """Check all risk limits. Returns check result with pass/fail per limit."""
    result = RiskCheckResult()
    initial = risk_config.get("initial_capital", 10000.0)
    max_daily_pct = risk_config.get("max_daily_loss_pct", 2.0)
    max_dd_pct = risk_config.get("max_drawdown_pct", 10.0)
    max_pos = risk_config.get("max_total_positions", 4)

    # Daily loss check
    if initial > 0:
        daily_loss_pct = abs(daily_pnl.total_pnl) / initial * 100
        if daily_pnl.total_pnl < 0 and daily_loss_pct >= max_daily_pct:
            result.daily_loss_ok = False
            result.messages.append(f"DAILY LOSS BREACH: {daily_loss_pct:.2f}% >= {max_daily_pct}% limit")

    # Drawdown check
    if daily_pnl.max_drawdown_pct >= max_dd_pct:
        result.drawdown_ok = False
        result.messages.append(f"DRAWDOWN BREACH: {daily_pnl.max_drawdown_pct:.2f}% >= {max_dd_pct}% limit")

    # Position count check
    if open_positions >= max_pos:
        result.max_positions_ok = False
        result.messages.append(f"MAX POSITIONS: {open_positions} >= {max_pos} limit")

    if not result.messages:
        result.messages.append("All risk limits OK")

    return result


# ── Report generation ─────────────────────────────────────────────────


def generate_report(daily_pnl: DailyPnL, risk_check: RiskCheckResult) -> str:
    """Generate markdown daily report."""
    lines = [
        f"# Paper Trade Daily Report — {daily_pnl.date}",
        "",
        "## Summary",
        f"- **Trades:** {daily_pnl.trades}",
        f"- **Wins/Losses:** {daily_pnl.wins}/{daily_pnl.losses}",
        f"- **Win Rate:** {daily_pnl.win_rate:.1%}",
        f"- **Realized P&L:** ${daily_pnl.realized_pnl:+.2f}",
        f"- **Unrealized P&L:** ${daily_pnl.unrealized_pnl:+.2f}",
        f"- **Total P&L:** ${daily_pnl.total_pnl:+.2f}",
        f"- **Equity:** ${daily_pnl.equity_current:,.2f} (high: ${daily_pnl.equity_high:,.2f})",
        f"- **Drawdown:** {daily_pnl.max_drawdown_pct:.2f}%",
        "",
        "## Risk Check",
    ]
    for msg in risk_check.messages:
        lines.append(f"- {msg}")
    lines.append("")

    if daily_pnl.risk_breaches:
        lines.append("## Risk Breaches")
        for b in daily_pnl.risk_breaches:
            lines.append(f"- **{b}**")
        lines.append("")

    return "\n".join(lines)


def save_daily_report(daily_pnl: DailyPnL, risk_check: RiskCheckResult) -> Path:
    """Save report to reports/paper_trades/."""
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    report_path = REPORTS_DIR / f"daily_{daily_pnl.date}.md"
    report = generate_report(daily_pnl, risk_check)
    report_path.write_text(report, encoding="utf-8")
    logger.info("Report saved: %s", report_path)
    return report_path


def save_state(state: dict) -> None:
    """Persist monitor state."""
    STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(STATE_PATH, "w") as f:
        json.dump(state, f, indent=2)


def load_state() -> dict:
    """Load monitor state."""
    if STATE_PATH.exists():
        with open(STATE_PATH) as f:
            return json.load(f)
    return {"last_check": None, "alerts_sent": 0}


# ── Alert formatting ──────────────────────────────────────────────────


def format_alert(daily_pnl: DailyPnL, risk_check: RiskCheckResult) -> str:
    """Format Telegram alert message."""
    status = "OK" if risk_check.daily_loss_ok and risk_check.drawdown_ok else "BREACH"
    lines = [
        f"<b>Paper Trade {status}</b> — {daily_pnl.date}",
        f"Trades: {daily_pnl.trades} (W:{daily_pnl.wins} L:{daily_pnl.losses})",
        f"P&amp;L: <code>${daily_pnl.total_pnl:+.2f}</code>",
        f"Win rate: {daily_pnl.win_rate:.1%}",
        f"Equity: ${daily_pnl.equity_current:,.2f}",
        f"Drawdown: {daily_pnl.max_drawdown_pct:.2f}%",
    ]
    if not risk_check.daily_loss_ok:
        lines.append("DAILY LOSS LIMIT HIT")
    if not risk_check.drawdown_ok:
        lines.append("DRAWDOWN LIMIT HIT")
    return "\n".join(lines)


# ── Main ──────────────────────────────────────────────────────────────


def run_check(send_alerts: bool = True) -> tuple[DailyPnL, RiskCheckResult]:
    """Run one monitoring cycle: load data, compute, check, report, alert."""
    config = load_config()
    risk_config = config.get("risk", {})
    alert_config = config.get("alerts", {})
    initial_capital = risk_config.get("initial_capital", 10000.0)

    # Try MT5 first, fall back to CSV log
    trades = load_mt5_deals()
    if not trades:
        trades = load_paper_trade_log()

    daily_pnl = compute_daily_pnl(trades, initial_capital)
    risk_check = check_risk_limits(daily_pnl, risk_config)

    # Save report
    save_daily_report(daily_pnl, risk_check)

    # Telegram alerts
    if send_alerts:
        alert_text = format_alert(daily_pnl, risk_check)
        if alert_config.get("alert_on_daily_summary", True):
            send_telegram(alert_text)
        if alert_config.get("alert_on_risk_breach", True):
            if not risk_check.daily_loss_ok or not risk_check.drawdown_ok:
                send_telegram(f"RISK ALERT: {alert_text}")

    # Update state
    state = load_state()
    state["last_check"] = datetime.now(UTC).isoformat()
    state["last_pnl"] = daily_pnl.total_pnl
    state["last_equity"] = daily_pnl.equity_current
    state["risk_ok"] = risk_check.daily_loss_ok and risk_check.drawdown_ok
    save_state(state)

    return daily_pnl, risk_check


def run_continuous(interval_seconds: int = 300) -> None:
    """Continuous monitoring loop."""
    logger.info("Starting continuous monitoring (interval=%ds)", interval_seconds)
    while True:
        try:
            daily_pnl, risk_check = run_check(send_alerts=True)
            logger.info(
                "Check: pnl=$%.2f equity=$%.2f risk=%s",
                daily_pnl.total_pnl,
                daily_pnl.equity_current,
                "OK" if risk_check.daily_loss_ok else "BREACH",
            )
        except Exception as e:
            logger.error("Monitor error: %s", e)
            send_telegram(f"Monitor error: {e}")
        time.sleep(interval_seconds)


def main() -> int:
    parser = argparse.ArgumentParser(description="Monitor paper trades")
    parser.add_argument("--live", action="store_true", help="Continuous monitoring mode")
    parser.add_argument("--check-risk", action="store_true", help="Risk check only")
    parser.add_argument("--no-alerts", action="store_true", help="Skip Telegram alerts")
    parser.add_argument("--interval", type=int, default=300, help="Monitoring interval (seconds)")
    args = parser.parse_args()

    if args.live:
        run_continuous(args.interval)
        return 0

    daily_pnl, risk_check = run_check(send_alerts=not args.no_alerts)

    print(f"\n{'='*60}")
    print(f"Paper Trade Monitor — {daily_pnl.date}")
    print(f"{'='*60}")
    print(f"Trades:   {daily_pnl.trades}")
    print(f"P&L:      ${daily_pnl.total_pnl:+.2f}")
    print(f"Equity:   ${daily_pnl.equity_current:,.2f}")
    print(f"Win rate: {daily_pnl.win_rate:.1%}")
    print(f"Risk:     {'OK' if risk_check.daily_loss_ok and risk_check.drawdown_ok else 'BREACH'}")
    for msg in risk_check.messages:
        print(f"  {msg}")
    print(f"{'='*60}\n")

    return 0 if (risk_check.daily_loss_ok and risk_check.drawdown_ok) else 1


if __name__ == "__main__":
    sys.exit(main())
