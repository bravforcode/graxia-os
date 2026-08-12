"""Generate paper trade configuration for multi-asset paper trading.

Produces config/paper_trade_config.json with symbol-specific settings,
risk parameters, trading hours, and news filter configuration.

Usage:
    python scripts/paper_trade_config.py
    python scripts/paper_trade_config.py --output config/my_config.json
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from pathlib import Path

# ── Paths ─────────────────────────────────────────────────────────────

SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = SCRIPT_DIR.parent
DEFAULT_OUTPUT = PROJECT_ROOT / "config" / "paper_trade_config.json"


# ── Symbol-specific settings ──────────────────────────────────────────


@dataclass(frozen=True)
class SymbolConfig:
    """Per-symbol trading parameters."""

    symbol: str
    asset_class: str  # metals, crypto, forex
    lot_size: float
    stop_loss_pips: float
    take_profit_pips: float
    max_positions: int
    spread_buffer_pips: float  # extra buffer for spread widening
    min_confidence: float  # minimum signal confidence to trade
    trading_hours_utc: dict  # {start: "HH:MM", end: "HH:MM"}
    notes: str = ""


SYMBOL_CONFIGS: list[SymbolConfig] = [
    SymbolConfig(
        symbol="XAUUSD",
        asset_class="metals",
        lot_size=0.01,
        stop_loss_pips=30.0,  # ~$30 = 300 points on gold
        take_profit_pips=60.0,
        max_positions=1,
        spread_buffer_pips=5.0,
        min_confidence=0.65,
        trading_hours_utc={"start": "01:00", "end": "21:00"},
        notes="Gold: avoid 21:00-01:00 low liquidity window",
    ),
    SymbolConfig(
        symbol="EURUSD",
        asset_class="forex",
        lot_size=0.01,
        stop_loss_pips=20.0,
        take_profit_pips=40.0,
        max_positions=1,
        spread_buffer_pips=1.0,
        min_confidence=0.60,
        trading_hours_utc={"start": "01:00", "end": "21:00"},
        notes="EURUSD: high liquidity during London/NY overlap",
    ),
    SymbolConfig(
        symbol="BTCUSD",
        asset_class="crypto",
        lot_size=0.01,
        stop_loss_pips=500.0,  # ~$500
        take_profit_pips=1000.0,
        max_positions=1,
        spread_buffer_pips=50.0,
        min_confidence=0.65,
        trading_hours_utc={"start": "00:00", "end": "23:59"},
        notes="BTC: 24/7 market, wider stops for volatility",
    ),
    SymbolConfig(
        symbol="ETHUSD",
        asset_class="crypto",
        lot_size=0.01,
        stop_loss_pips=30.0,  # ~$30
        take_profit_pips=60.0,
        max_positions=1,
        spread_buffer_pips=3.0,
        min_confidence=0.65,
        trading_hours_utc={"start": "00:00", "end": "23:59"},
        notes="ETH: 24/7, correlated with BTC — reduce position if BTC also open",
    ),
]


# ── Risk parameters ───────────────────────────────────────────────────


@dataclass(frozen=True)
class RiskParams:
    """Portfolio-level risk controls for paper trading."""

    max_risk_per_trade_pct: float = 1.0
    max_daily_loss_pct: float = 2.0
    max_drawdown_pct: float = 10.0
    max_portfolio_exposure_pct: float = 50.0
    max_total_positions: int = 4  # one per symbol
    max_correlated_positions: int = 2  # max positions in correlated assets
    kill_switch_drawdown_pct: float = 15.0  # halt all trading
    initial_capital: float = 10000.0
    currency: str = "USD"


# ── News filter ───────────────────────────────────────────────────────


@dataclass(frozen=True)
class NewsFilterConfig:
    """News event filter settings — integrates with news_events module."""

    enabled: bool = True
    pre_block_minutes: int = 30
    post_block_minutes: int = 15
    blocked_event_types: list[str] = field(
        default_factory=lambda: [
            "NFP",  # Non-Farm Payrolls
            "FOMC",  # Federal Reserve
            "ECB_RATE",  # ECB rate decision
            "BOJ_RATE",  # BOJ rate decision
            "CPI_US",  # US CPI
            "CPI_EU",  # EU CPI
            "GDP_US",  # US GDP
            "UNEMPLOYMENT_US",
        ]
    )
    min_importance_for_block: str = "HIGH"
    notes: str = "30min pre-block, 15min post-block for HIGH importance events"


# ── Trading schedule ──────────────────────────────────────────────────


@dataclass(frozen=True)
class TradingSchedule:
    """Daily schedule for paper trading operations."""

    data_pull_utc: str = "00:30"
    feature_build_utc: str = "01:00"
    signal_generation_utc: str = "01:15"
    execution_start_utc: str = "01:30"
    daily_review_utc: str = "22:00"
    weekly_review_day: str = "friday"
    timezone: str = "UTC"


# ── Alerts ────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class AlertConfig:
    """Alert configuration for paper trade monitoring."""

    telegram_enabled: bool = True
    alert_on_trade: bool = True
    alert_on_daily_summary: bool = True
    alert_on_risk_breach: bool = True
    alert_on_kill_switch: bool = True
    alert_on_drawdown_warning: bool = True
    drawdown_warning_threshold_pct: float = 5.0


# ── Main config ───────────────────────────────────────────────────────


@dataclass(frozen=True)
class PaperTradeConfig:
    """Complete paper trade configuration."""

    version: str = "1.0"
    created_at: str = ""
    broker: str = "Pepperstone-Demo"
    trading_mode: str = "PAPER"
    symbols: list[dict] = field(default_factory=list)
    risk: dict = field(default_factory=dict)
    news_filter: dict = field(default_factory=dict)
    schedule: dict = field(default_factory=dict)
    alerts: dict = field(default_factory=dict)


def build_config() -> PaperTradeConfig:
    """Assemble the full paper trade configuration."""
    return PaperTradeConfig(
        created_at=datetime.now(UTC).isoformat(),
        symbols=[asdict(s) for s in SYMBOL_CONFIGS],
        risk=asdict(RiskParams()),
        news_filter=asdict(NewsFilterConfig()),
        schedule=asdict(TradingSchedule()),
        alerts=asdict(AlertConfig()),
    )


def save_config(config: PaperTradeConfig, output_path: Path) -> None:
    """Save configuration to JSON file."""
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(asdict(config), f, indent=2, ensure_ascii=False)
    print(f"Config saved to: {output_path}")


def print_summary(config: PaperTradeConfig) -> None:
    """Print human-readable config summary."""
    print("\n" + "=" * 60)
    print("PAPER TRADE CONFIGURATION")
    print("=" * 60)
    print(f"Broker:      {config.broker}")
    print(f"Mode:        {config.trading_mode}")
    print(f"Created:     {config.created_at}")
    print()

    print("SYMBOLS:")
    for s in config.symbols:
        print(
            f"  {s['symbol']:8s} | lot={s['lot_size']} SL={s['stop_loss_pips']} "
            f"TP={s['take_profit_pips']} max_pos={s['max_positions']} "
            f"min_conf={s['min_confidence']} | {s['trading_hours_utc']}"
        )
    print()

    risk = config.risk
    print(
        f"RISK: risk/trade={risk['max_risk_per_trade_pct']}% "
        f"daily_loss={risk['max_daily_loss_pct']}% "
        f"drawdown={risk['max_drawdown_pct']}% "
        f"capital=${risk['initial_capital']:,.0f}"
    )
    print()

    nf = config.news_filter
    print(
        f"NEWS FILTER: enabled={nf['enabled']} "
        f"pre={nf['pre_block_minutes']}min post={nf['post_block_minutes']}min "
        f"blocked={len(nf['blocked_event_types'])} event types"
    )
    print()

    sched = config.schedule
    print(
        f"SCHEDULE: pull={sched['data_pull_utc']} features={sched['feature_build_utc']} "
        f"signals={sched['signal_generation_utc']} execute={sched['execution_start_utc']}"
    )
    print()
    print("=" * 60)


# ── CLI ───────────────────────────────────────────────────────────────


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate paper trade configuration")
    parser.add_argument("--output", "-o", type=str, default=str(DEFAULT_OUTPUT), help="Output path for config JSON")
    parser.add_argument("--summary", action="store_true", help="Print summary to stdout")
    args = parser.parse_args()

    config = build_config()
    output_path = Path(args.output)
    save_config(config, output_path)

    if args.summary or True:
        print_summary(config)

    return 0


if __name__ == "__main__":
    sys.exit(main())
