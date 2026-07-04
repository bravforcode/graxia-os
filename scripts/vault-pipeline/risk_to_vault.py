"""
Risk Dashboard → Vault Pipeline

Reads quant_os risk system state and generates Obsidian-compatible
risk dashboard markdown for the Second Brain vault.

Usage:
    python risk_to_vault.py [--vault-path PATH] [--sample]

Outputs:
    {vault}/03-resources/trading/risk/dashboard.md
"""

import argparse
import json
from datetime import datetime, date
from pathlib import Path
from dataclasses import dataclass, field
from typing import Any


# ── Default paths ──────────────────────────────────────────────
QUANT_ROOT = Path(__file__).resolve().parents[2] / "graxia" / "packages" / "quant_os"
VAULT_ROOT = Path.home() / "Documents" / "ObsidianVault" / "Second Brain"
OUTPUT_DIR = VAULT_ROOT / "03-resources" / "trading" / "risk"
RISK_LEDGER_PATH = QUANT_ROOT / "data" / "risk_ledger.json"
KILL_SWITCH_PATH = QUANT_ROOT / "data" / "kill_switch_state.json"
TRADE_LOG_PATH = QUANT_ROOT / "data" / "paper_trade_log.csv"


# ── Risk limits (from golden_rules.py + config.py) ────────────
HARD_LIMITS = {
    "max_drawdown_pct": 15.0,
    "max_daily_loss_pct": 2.0,
    "max_weekly_loss_pct": 5.0,
    "max_positions": 5,
    "max_portfolio_exposure_pct": 50.0,
    "max_correlation_threshold": 0.7,
}


@dataclass
class RiskDashboard:
    """All metrics for the risk dashboard."""

    # Timestamps
    generated_at: str = ""
    trade_date: str = ""

    # Drawdown
    current_drawdown_pct: float = 0.0
    drawdown_limit_pct: float = HARD_LIMITS["max_drawdown_pct"]
    drawdown_headroom_pct: float = 0.0

    # Daily P&L
    daily_pnl: float = 0.0
    daily_loss_limit: float = HARD_LIMITS["max_daily_loss_pct"]
    daily_loss_used_pct: float = 0.0

    # Weekly P&L
    weekly_pnl: float = 0.0
    weekly_loss_limit: float = HARD_LIMITS["max_weekly_loss_pct"]

    # Positions
    open_positions: int = 0
    max_positions: int = HARD_LIMITS["max_positions"]

    # Circuit breaker
    circuit_breaker_state: str = "CLOSED"
    circuit_breaker_reason: str = ""
    circuit_breaker_losses: int = 0
    circuit_breaker_error_rate: float = 0.0

    # Kill switch
    kill_switch_active: bool = False
    kill_switch_reason: str = ""
    kill_switch_activated_at: str = ""

    # Exposure
    gross_exposure: float = 0.0
    net_exposure: float = 0.0
    long_exposure: float = 0.0
    short_exposure: float = 0.0
    symbol_exposure: dict = field(default_factory=dict)
    exposure_limit_pct: float = HARD_LIMITS["max_portfolio_exposure_pct"]

    # Correlation
    max_correlation: float = 0.0
    correlation_limit: float = HARD_LIMITS["max_correlation_threshold"]
    correlation_pairs: list = field(default_factory=list)

    # Risk budget
    risk_budget_used_pct: float = 0.0
    risk_budget_capital: float = 10000.0

    # Trade counts
    orders_today: int = 0
    trades_today: int = 0
    consecutive_losses: int = 0

    # Data source
    source: str = "sample"


def load_risk_ledger() -> dict:
    """Load risk_ledger.json if it exists."""
    if RISK_LEDGER_PATH.exists():
        return json.loads(RISK_LEDGER_PATH.read_text())
    return {}


def load_kill_switch() -> dict:
    """Load kill_switch_state.json if it exists."""
    if KILL_SWITCH_PATH.exists():
        return json.loads(KILL_SWITCH_PATH.read_text())
    return {"active": False}


def parse_trade_log() -> list[dict]:
    """Parse paper_trade_log.csv for today's trades."""
    trades = []
    if not TRADE_LOG_PATH.exists():
        return trades

    lines = TRADE_LOG_PATH.read_text().strip().split("\n")
    if len(lines) < 2:
        return trades

    headers = lines[0].split(",")
    today_str = date.today().isoformat()

    for line in lines[1:]:
        if not line.strip():
            continue
        parts = line.split(",")
        row = dict(zip(headers, parts))
        ts = row.get("timestamp", "")
        if ts.startswith(today_str):
            trades.append(row)

    return trades


def parse_symbol_exposure(raw: Any) -> dict:
    """Normalize symbol exposure from ledger."""
    if isinstance(raw, dict):
        return raw
    return {}


def compute_exposure_directions(symbol_exposure: dict) -> tuple[float, float]:
    """Compute long/short totals from symbol_exposure dict.
    Values are positive for long, negative for short.
    """
    long_total = 0.0
    short_total = 0.0
    for val in symbol_exposure.values():
        v = float(val)
        if v >= 0:
            long_total += v
        else:
            short_total += abs(v)
    return long_total, short_total


def build_dashboard_from_ledger(
    ledger: dict, kill_sw: dict, trades: list[dict]
) -> RiskDashboard:
    """Build RiskDashboard from live ledger + kill switch state."""
    now = datetime.utcnow()

    symbol_exposure = parse_symbol_exposure(ledger.get("symbol_exposure", {}))
    long_exp, short_exp = compute_exposure_directions(symbol_exposure)
    gross = float(ledger.get("gross_exposure", 0.0))
    net = long_exp - short_exp

    # Daily loss as percentage of $10k capital
    daily_loss_abs = float(ledger.get("daily_realized_loss", 0.0))
    capital = 10000.0
    daily_loss_pct = (daily_loss_abs / capital * 100) if capital > 0 else 0.0

    # Drawdown from ledger
    drawdown_pct = float(ledger.get("total_drawdown", 0.0))

    # Risk budget: approximate as sum of all limit utilizations
    drawdown_used = (drawdown_pct / HARD_LIMITS["max_drawdown_pct"]) * 100
    daily_used = (daily_loss_pct / HARD_LIMITS["max_daily_loss_pct"]) * 100
    pos_used = (ledger.get("open_positions", 0) / HARD_LIMITS["max_positions"]) * 100
    risk_budget = (drawdown_used + daily_used + pos_used) / 3.0

    # Trades
    pnl_today = sum(float(t.get("pnl_net", 0) or 0) for t in trades)
    open_pos = ledger.get("open_positions", 0)

    return RiskDashboard(
        generated_at=now.strftime("%Y-%m-%d %H:%M:%S UTC"),
        trade_date=date.today().isoformat(),
        current_drawdown_pct=drawdown_pct,
        drawdown_headroom_pct=max(0, HARD_LIMITS["max_drawdown_pct"] - drawdown_pct),
        daily_pnl=pnl_today,
        daily_loss_limit=HARD_LIMITS["max_daily_loss_pct"],
        daily_loss_used_pct=round(daily_loss_pct, 2),
        weekly_pnl=float(ledger.get("weekly_realized_loss", 0.0)),
        weekly_loss_limit=HARD_LIMITS["max_weekly_loss_pct"],
        open_positions=open_pos,
        max_positions=HARD_LIMITS["max_positions"],
        circuit_breaker_state="CLOSED",  # requires live instance
        kill_switch_active=kill_sw.get("active", False),
        kill_switch_reason=kill_sw.get("reason", ""),
        kill_switch_activated_at=kill_sw.get("activated_at_utc", ""),
        gross_exposure=gross,
        net_exposure=net,
        long_exposure=long_exp,
        short_exposure=short_exp,
        symbol_exposure=symbol_exposure,
        orders_today=ledger.get("orders_today", 0),
        trades_today=len(trades),
        risk_budget_used_pct=round(risk_budget, 2),
        risk_budget_capital=capital,
        source="ledger",
    )


def build_sample_dashboard() -> RiskDashboard:
    """Build a sample dashboard for testing."""
    now = datetime.utcnow()
    return RiskDashboard(
        generated_at=now.strftime("%Y-%m-%d %H:%M:%S UTC"),
        trade_date=date.today().isoformat(),
        current_drawdown_pct=3.2,
        drawdown_limit_pct=15.0,
        drawdown_headroom_pct=11.8,
        daily_pnl=-42.50,
        daily_loss_limit=2.0,
        daily_loss_used_pct=0.43,
        weekly_pnl=-185.00,
        weekly_loss_limit=5.0,
        open_positions=3,
        max_positions=5,
        circuit_breaker_state="CLOSED",
        circuit_breaker_reason="",
        circuit_breaker_losses=1,
        circuit_breaker_error_rate=0.0,
        kill_switch_active=False,
        kill_switch_reason="",
        kill_switch_activated_at="",
        gross_exposure=12500.0,
        net_exposure=3200.0,
        long_exposure=7850.0,
        short_exposure=4650.0,
        symbol_exposure={
            "XAUUSD": 5200.0,
            "EURUSD": 2650.0,
            "USDJPY": -4650.0,
            "GBPUSD": 2650.0,
        },
        exposure_limit_pct=50.0,
        max_correlation=0.62,
        correlation_limit=0.7,
        correlation_pairs=[("XAUUSD", "EURUSD", 0.62)],
        risk_budget_used_pct=38.5,
        risk_budget_capital=10000.0,
        orders_today=4,
        trades_today=2,
        consecutive_losses=1,
        source="sample",
    )


def status_indicator(current: float, limit: float, invert: bool = False) -> str:
    """Return a visual status indicator."""
    if limit == 0:
        return "---"
    ratio = current / limit if not invert else (limit - current) / limit
    if ratio < 0.5:
        return "🟢"
    elif ratio < 0.75:
        return "🟡"
    else:
        return "🔴"


def render_dashboard(d: RiskDashboard) -> str:
    """Render the risk dashboard as Obsidian markdown."""

    # Circuit breaker display
    cb_status = (
        "OFF"
        if d.circuit_breaker_state == "CLOSED"
        else f"ON ({d.circuit_breaker_state})"
    )
    cb_indicator = "🟢 OFF" if d.circuit_breaker_state == "CLOSED" else "🔴 ON"

    # Kill switch display
    ks_status = "DISENGAGED" if not d.kill_switch_active else "ENGAGED"
    ks_indicator = "🟢 DISENGAGED" if not d.kill_switch_active else "🔴 ENGAGED"

    # Exposure by symbol
    symbol_rows = []
    for sym, val in sorted(
        d.symbol_exposure.items(), key=lambda x: abs(x[1]), reverse=True
    ):
        direction = "LONG" if float(val) >= 0 else "SHORT"
        abs_val = abs(float(val))
        pct = (
            (abs_val / d.risk_budget_capital * 100) if d.risk_budget_capital > 0 else 0
        )
        symbol_rows.append(f"| {sym} | {direction} | ${abs_val:,.2f} | {pct:.1f}% |")

    # Correlation pairs
    corr_rows = []
    for pair in d.correlation_pairs:
        if len(pair) == 3:
            s1, s2, c = pair
            risk = "HIGH" if c > d.correlation_limit else "OK"
            corr_rows.append(f"| {s1} / {s2} | {c:.2f} | {risk} |")

    # Risk budget bar
    budget_pct = d.risk_budget_used_pct
    filled = int(budget_pct / 5)
    bar = "█" * filled + "░" * (20 - filled)

    md = f"""---
type: risk-dashboard
last_updated: {d.generated_at}
drawdown_pct: {d.current_drawdown_pct}
circuit_breaker: {d.circuit_breaker_state}
kill_switch: {"ENGAGED" if d.kill_switch_active else "DISENGAGED"}
source: {d.source}
---

# Risk Dashboard

> Generated: {d.generated_at} | Trade date: {d.trade_date}

## Core Limits

| Metric | Current | Limit | Headroom | Status |
|--------|---------|-------|----------|--------|
| Drawdown | {d.current_drawdown_pct:.2f}% | {d.drawdown_limit_pct:.1f}% | {d.drawdown_headroom_pct:.1f}% | {status_indicator(d.current_drawdown_pct, d.drawdown_limit_pct)} |
| Daily P&L | ${d.daily_pnl:+,.2f} | {d.daily_loss_limit:.1f}% loss cap | {d.daily_loss_used_pct:.2f}% used | {status_indicator(d.daily_loss_used_pct, 100)} |
| Weekly P&L | ${d.weekly_pnl:+,.2f} | {d.weekly_loss_limit:.1f}% loss cap | -- | {status_indicator(abs(d.weekly_pnl), d.risk_budget_capital * d.weekly_loss_limit / 100)} |
| Open Positions | {d.open_positions} | {d.max_positions} | {d.max_positions - d.open_positions} slots | {status_indicator(d.open_positions, d.max_positions)} |

## Circuit Breaker

| Field | Value |
|-------|-------|
| Status | {cb_indicator} |
| State | {d.circuit_breaker_state} |
| Reason | {d.circuit_breaker_reason or "None"} |
| Consecutive Losses | {d.circuit_breaker_losses} |
| Error Rate | {d.circuit_breaker_error_rate:.1f}% |

## Kill Switch

| Field | Value |
|-------|-------|
| Status | {ks_indicator} |
| Reason | {d.kill_switch_reason or "N/A"} |
| Activated At | {d.kill_switch_activated_at or "N/A"} |

## Exposure

| Metric | Value | Limit |
|--------|-------|-------|
| Gross Exposure | ${d.gross_exposure:,.2f} | {d.exposure_limit_pct:.0f}% of capital |
| Net Exposure | ${d.net_exposure:,.2f} | -- |
| Long Exposure | ${d.long_exposure:,.2f} | -- |
| Short Exposure | ${d.short_exposure:,.2f} | -- |

### Exposure by Symbol

| Symbol | Direction | Value | % of Capital |
|--------|-----------|-------|--------------|
{chr(10).join(symbol_rows) if symbol_rows else "| (no positions) | -- | $0.00 | 0.0% |"}

## Direction Summary

```mermaid
pie title Net Exposure
    "Long" : {d.long_exposure:.0f}
    "Short" : {d.short_exposure:.0f}
```

- **Net bias:** {"Long" if d.net_exposure > 0 else "Short" if d.net_exposure < 0 else "Flat"} (${abs(d.net_exposure):,.2f})

## Correlation Risk

| Pair | Correlation | Risk |
|------|-------------|------|
{chr(10).join(corr_rows) if corr_rows else "| (no pairs) | -- | -- |"}

> Threshold: {d.correlation_limit:.2f} — Pairs above are correlated.

## Risk Budget

```
{bar} {d.risk_budget_used_pct:.1f}%
```

| Component | Utilization |
|-----------|-------------|
| Drawdown budget | {(d.current_drawdown_pct / d.drawdown_limit_pct * 100) if d.drawdown_limit_pct > 0 else 0:.1f}% |
| Daily loss budget | {d.daily_loss_used_pct:.1f}% |
| Position slots | {(d.open_positions / d.max_positions * 100) if d.max_positions > 0 else 0:.1f}% |
| **Total budget** | **{d.risk_budget_used_pct:.1f}%** |

## Trade Activity

| Metric | Value |
|--------|-------|
| Orders Today | {d.orders_today} |
| Trades Today | {d.trades_today} |
| Consecutive Losses | {d.consecutive_losses} |

## Quick Actions

- [[risk/kill-switch-control|Kill Switch Control]]
- [[risk/exposure-breakdown|Exposure Breakdown]]
- [[risk/trade-log|Trade Log]]
- [[moc/MOC-trading|Trading MOC]]

---
*Auto-generated by risk_to_vault.py — Pipeline 7: Risk Dashboard → Vault*
"""

    return md


def main():
    parser = argparse.ArgumentParser(description="Risk Dashboard → Vault pipeline")
    parser.add_argument("--vault-path", help="Override vault root path")
    parser.add_argument(
        "--sample", action="store_true", help="Generate sample dashboard (no live data)"
    )
    parser.add_argument("--output", help="Override output file path")
    args = parser.parse_args()

    output_dir = Path(args.output).parent if args.output else OUTPUT_DIR
    output_file = Path(args.output) if args.output else OUTPUT_DIR / "dashboard.md"

    if args.sample:
        dashboard = build_sample_dashboard()
        print("[risk_to_vault] Using sample data")
    else:
        ledger = load_risk_ledger()
        kill_sw = load_kill_switch()
        trades = parse_trade_log()
        dashboard = build_dashboard_from_ledger(ledger, kill_sw, trades)
        print(f"[risk_to_vault] Loaded ledger from {RISK_LEDGER_PATH}")
        print(f"[risk_to_vault] Loaded kill switch from {KILL_SWITCH_PATH}")
        print(f"[risk_to_vault] Found {len(trades)} trades today")

    md = render_dashboard(dashboard)

    output_dir.mkdir(parents=True, exist_ok=True)
    output_file.write_text(md, encoding="utf-8")

    print(f"[risk_to_vault] Dashboard written to {output_file}")
    print(
        f"[risk_to_vault] Drawdown: {dashboard.current_drawdown_pct:.2f}% | "
        f"CB: {dashboard.circuit_breaker_state} | "
        f"KS: {'ENGAGED' if dashboard.kill_switch_active else 'DISENGAGED'}"
    )


if __name__ == "__main__":
    main()
