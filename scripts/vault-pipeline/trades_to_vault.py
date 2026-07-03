"""Trade Journal → Vault pipeline.

Reads paper_trade_log.csv, generates Obsidian vault daily trade journals
at Second Brain/07-Daily/trades/{date}.md.
"""

import csv
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Optional


# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

CSV_PATH = Path(
    r"C:\Users\menum\graxia os\graxia\packages\quant_os\data\paper_trade_log.csv"
)
VAULT_DIR = Path(r"C:\Users\menum\Documents\ObsidianVault\Second Brain\07-Daily\trades")
SAMPLE_CSV = Path(
    r"C:\Users\menum\graxia os\graxia\packages\quant_os\data\sample_trades.csv"
)

CSV_COLUMNS = [
    "trade_id",
    "symbol",
    "direction",
    "entry_time",
    "exit_time",
    "entry_price",
    "exit_price",
    "qty",
    "pnl",
    "pnl_pct",
    "strategy",
    "regime",
    "notes",
]

# ---------------------------------------------------------------------------
# Data
# ---------------------------------------------------------------------------


@dataclass
class Trade:
    trade_id: str
    symbol: str
    direction: str
    entry_time: datetime
    exit_time: Optional[datetime]
    entry_price: float
    exit_price: float
    qty: float
    pnl: float
    pnl_pct: float
    strategy: str
    regime: str
    notes: str = ""


@dataclass
class DailySummary:
    date: str
    trades: list[Trade] = field(default_factory=list)

    @property
    def total_trades(self) -> int:
        return len(self.trades)

    @property
    def daily_pnl(self) -> float:
        return sum(t.pnl for t in self.trades)

    @property
    def winners(self) -> list[Trade]:
        return [t for t in self.trades if t.pnl > 0]

    @property
    def losers(self) -> list[Trade]:
        return [t for t in self.trades if t.pnl <= 0]

    @property
    def win_rate(self) -> float:
        return (
            (len(self.winners) / self.total_trades * 100) if self.total_trades else 0.0
        )

    @property
    def best_trade(self) -> Optional[Trade]:
        return max(self.trades, key=lambda t: t.pnl) if self.trades else None

    @property
    def worst_trade(self) -> Optional[Trade]:
        return min(self.trades, key=lambda t: t.pnl) if self.trades else None

    def strategy_breakdown(self) -> dict[str, dict]:
        breakdown: dict[str, dict] = {}
        for t in self.trades:
            s = t.strategy or "unknown"
            if s not in breakdown:
                breakdown[s] = {"count": 0, "pnl": 0.0, "wins": 0}
            breakdown[s]["count"] += 1
            breakdown[s]["pnl"] += t.pnl
            if t.pnl > 0:
                breakdown[s]["wins"] += 1
        return breakdown

    def regime_breakdown(self) -> dict[str, int]:
        regimes: dict[str, int] = {}
        for t in self.trades:
            r = t.regime or "unknown"
            regimes[r] = regimes.get(r, 0) + 1
        return regimes


# ---------------------------------------------------------------------------
# CSV helpers
# ---------------------------------------------------------------------------


def _parse_dt(raw: str) -> Optional[datetime]:
    raw = raw.strip()
    if not raw:
        return None
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%d %H:%M", "%Y-%m-%d"):
        try:
            return datetime.strptime(raw, fmt)
        except ValueError:
            continue
    return None


def _safe_float(val: str, default: float = 0.0) -> float:
    val = val.strip()
    if not val:
        return default
    try:
        return float(val)
    except ValueError:
        return default


def read_trades(csv_path: Path) -> list[Trade]:
    """Read trades from CSV. Handles both full-schema and live-log schemas."""
    trades: list[Trade] = []
    if not csv_path.exists():
        print(f"[warn] CSV not found: {csv_path}")
        return trades

    with open(csv_path, newline="", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        headers = [h.strip().lower() for h in (reader.fieldnames or [])]

        # Detect schema: live-log uses "timestamp" instead of "entry_time"
        is_live_log = "timestamp" in headers and "entry_time" not in headers

        for row in reader:
            # Normalize keys to lowercase
            row = {k.strip().lower(): v for k, v in row.items()}

            if is_live_log:
                # Live-log schema: timestamp, direction, entry_price, exit_price,
                # pnl_gross, pnl_net, notes, ...
                entry_dt = _parse_dt(row.get("timestamp", ""))
                exit_dt = None  # live log may not have exit_time
                symbol = row.get("symbol", "XAUUSD")  # default to XAUUSD
                direction = row.get("direction", "")
                pnl = _safe_float(row.get("pnl_net", "") or row.get("pnl_gross", ""))
                strategy = row.get("strategy", "")
                regime = row.get("regime", "")
                qty = _safe_float(row.get("qty", "1"))
                pnl_pct = _safe_float(row.get("pnl_pct", ""))
            else:
                # Full schema
                entry_dt = _parse_dt(row.get("entry_time", ""))
                exit_dt = _parse_dt(row.get("exit_time", ""))
                symbol = row.get("symbol", "")
                direction = row.get("direction", "")
                pnl = _safe_float(row.get("pnl", ""))
                strategy = row.get("strategy", "")
                regime = row.get("regime", "")
                qty = _safe_float(row.get("qty", "1"))
                pnl_pct = _safe_float(row.get("pnl_pct", ""))

            trades.append(
                Trade(
                    trade_id=row.get("trade_id", ""),
                    symbol=symbol,
                    direction=direction,
                    entry_time=entry_dt,
                    exit_time=exit_dt,
                    entry_price=_safe_float(row.get("entry_price", "")),
                    exit_price=_safe_float(row.get("exit_price", "")),
                    qty=qty,
                    pnl=pnl,
                    pnl_pct=pnl_pct,
                    strategy=strategy,
                    regime=regime,
                    notes=row.get("notes", ""),
                )
            )
    return trades


def group_by_day(trades: list[Trade]) -> dict[str, DailySummary]:
    groups: dict[str, DailySummary] = {}
    for t in trades:
        key = t.entry_time.strftime("%Y-%m-%d") if t.entry_time else "unknown"
        if key not in groups:
            groups[key] = DailySummary(date=key)
        groups[key].trades.append(t)
    return groups


# ---------------------------------------------------------------------------
# Markdown generation
# ---------------------------------------------------------------------------


def _pnl_badge(pnl: float) -> str:
    return f"🟢 +{pnl:.2f}" if pnl > 0 else f"🔴 {pnl:.2f}"


def _fmt_dt(dt: Optional[datetime]) -> str:
    return dt.strftime("%H:%M") if dt else "—"


def render_journal(ds: DailySummary) -> str:
    lines: list[str] = []

    # frontmatter
    lines.append("---")
    lines.append("type: trade-journal")
    lines.append(f"date: {ds.date}")
    lines.append(f"total_trades: {ds.total_trades}")
    lines.append(f"daily_pnl: {ds.daily_pnl:.2f}")
    lines.append(f"win_rate: {ds.win_rate:.1f}%")
    lines.append(f"generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    lines.append("---")
    lines.append("")

    # header
    lines.append(f"# Trade Journal — {ds.date}")
    lines.append("")
    lines.append(
        f"> {ds.total_trades} trades  |  P&L **{_pnl_badge(ds.daily_pnl)}**  |  Win rate **{ds.win_rate:.1f}%**"
    )
    lines.append("")

    # daily summary
    lines.append("## Daily Summary")
    lines.append("")
    lines.append("| Metric | Value |")
    lines.append("|--------|-------|")
    lines.append(f"| Total trades | {ds.total_trades} |")
    lines.append(f"| Winners | {len(ds.winners)} |")
    lines.append(f"| Losers | {len(ds.losers)} |")
    lines.append(f"| Daily P&L | {ds.daily_pnl:+.2f} |")
    lines.append(f"| Win rate | {ds.win_rate:.1f}% |")
    if ds.best_trade:
        lines.append(
            f"| Best trade | {ds.best_trade.symbol} {_pnl_badge(ds.best_trade.pnl)} |"
        )
    if ds.worst_trade:
        lines.append(
            f"| Worst trade | {ds.worst_trade.symbol} {_pnl_badge(ds.worst_trade.pnl)} |"
        )
    lines.append("")

    # strategy breakdown
    strat = ds.strategy_breakdown()
    if strat:
        lines.append("## Strategy Breakdown")
        lines.append("")
        lines.append("| Strategy | Trades | P&L | Win Rate |")
        lines.append("|----------|--------|-----|----------|")
        for name, data in sorted(strat.items()):
            wr = (data["wins"] / data["count"] * 100) if data["count"] else 0
            lines.append(
                f"| {name} | {data['count']} | {data['pnl']:+.2f} | {wr:.0f}% |"
            )
        lines.append("")

    # individual trades
    lines.append("## Trade Log")
    lines.append("")
    lines.append(
        "| # | Symbol | Dir | Entry | Exit | Entry$ | Exit$ | P&L | Strategy |"
    )
    lines.append(
        "|---|--------|-----|-------|------|--------|-------|-----|----------|"
    )
    for i, t in enumerate(ds.trades, 1):
        lines.append(
            f"| {i} | {t.symbol} | {t.direction} "
            f"| {_fmt_dt(t.entry_time)} | {_fmt_dt(t.exit_time)} "
            f"| {t.entry_price:.5f} | {t.exit_price:.5f} "
            f"| {_pnl_badge(t.pnl)} | {t.strategy} |"
        )
    lines.append("")

    # best / worst detail
    if ds.best_trade:
        bt = ds.best_trade
        lines.append("## Best Trade")
        lines.append("")
        lines.append(
            f"- **{bt.symbol}** {bt.direction} — P&L: {_pnl_badge(bt.pnl)} ({bt.pnl_pct:+.2f}%)"
        )
        lines.append(f"- Strategy: {bt.strategy}  |  Regime: {bt.regime}")
        if bt.entry_time:
            lines.append(
                f"- Entry: {bt.entry_time:%Y-%m-%d %H:%M} @ {bt.entry_price:.5f}"
            )
        else:
            lines.append(f"- Entry: ? @ {bt.entry_price:.5f}")
        if bt.exit_time:
            lines.append(f"- Exit: {bt.exit_time:%H:%M} @ {bt.exit_price:.5f}")
        else:
            lines.append("- Exit: open")
        lines.append("")

    if ds.worst_trade and ds.worst_trade != ds.best_trade:
        wt = ds.worst_trade
        lines.append("## Worst Trade")
        lines.append("")
        lines.append(
            f"- **{wt.symbol}** {wt.direction} -- P&L: {_pnl_badge(wt.pnl)} ({wt.pnl_pct:+.2f}%)"
        )
        lines.append(f"- Strategy: {wt.strategy}  |  Regime: {wt.regime}")
        if wt.entry_time:
            lines.append(
                f"- Entry: {wt.entry_time:%Y-%m-%d %H:%M} @ {wt.entry_price:.5f}"
            )
        else:
            lines.append(f"- Entry: ? @ {wt.entry_price:.5f}")
        if wt.exit_time:
            lines.append(f"- Exit: {wt.exit_time:%H:%M} @ {wt.exit_price:.5f}")
        else:
            lines.append("- Exit: open")
        lines.append("")

    # regime note
    regimes = ds.regime_breakdown()
    if regimes:
        lines.append("## Regime Distribution")
        lines.append("")
        for regime, count in sorted(regimes.items(), key=lambda x: -x[1]):
            lines.append(f"- **{regime}**: {count} trades")
        lines.append("")

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Sample data
# ---------------------------------------------------------------------------

SAMPLE_TRADES = [
    (
        "T001",
        "XAUUSD",
        "LONG",
        "2026-06-25 08:15:00",
        "2026-06-25 10:30:00",
        3310.50,
        3318.75,
        0.05,
        41.25,
        0.25,
        "trend_following",
        "trending_up",
        "morning breakout",
    ),
    (
        "T002",
        "XAUUSD",
        "SHORT",
        "2026-06-25 13:00:00",
        "2026-06-25 14:45:00",
        3322.00,
        3319.50,
        0.05,
        12.50,
        0.08,
        "mean_reversion",
        "range_bound",
        "resistance rejection",
    ),
    (
        "T003",
        "XAUUSD",
        "LONG",
        "2026-06-25 16:00:00",
        "2026-06-25 17:30:00",
        3319.00,
        3315.25,
        0.05,
        -18.75,
        -0.12,
        "trend_following",
        "trending_up",
        "failed breakout",
    ),
    (
        "T004",
        "EURUSD",
        "LONG",
        "2026-06-26 07:00:00",
        "2026-06-26 09:15:00",
        1.0845,
        1.0872,
        10000,
        27.00,
        0.25,
        "breakout",
        "trending",
        "session open",
    ),
    (
        "T005",
        "EURUSD",
        "SHORT",
        "2026-06-26 11:30:00",
        "2026-06-26 12:00:00",
        1.0878,
        1.0885,
        10000,
        -7.00,
        -0.06,
        "scalp",
        "range_bound",
        "stopped out",
    ),
    (
        "T006",
        "XAUUSD",
        "LONG",
        "2026-06-26 08:30:00",
        "2026-06-26 11:45:00",
        3305.00,
        3321.50,
        0.05,
        82.50,
        0.50,
        "trend_following",
        "trending_up",
        "strong momentum",
    ),
    (
        "T007",
        "XAUUSD",
        "SHORT",
        "2026-06-26 14:00:00",
        "2026-06-26 15:30:00",
        3325.00,
        3320.25,
        0.05,
        23.75,
        0.15,
        "mean_reversion",
        "range_bound",
        "reversal",
    ),
    (
        "T008",
        "GBPUSD",
        "LONG",
        "2026-06-27 08:00:00",
        "2026-06-27 10:00:00",
        1.2710,
        1.2735,
        8000,
        20.00,
        0.20,
        "breakout",
        "trending",
        "london session",
    ),
]


def write_sample_csv(path: Path) -> None:
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(CSV_COLUMNS)
        w.writerows(SAMPLE_TRADES)
    print(f"[ok] wrote sample CSV → {path}")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def generate(csv_path: Path = CSV_PATH, vault_dir: Path = VAULT_DIR) -> list[Path]:
    """Read CSV, generate vault journals. Returns list of written md files."""
    trades = read_trades(csv_path)
    if not trades:
        print("[info] no trades to journal")
        return []

    groups = group_by_day(trades)
    vault_dir.mkdir(parents=True, exist_ok=True)
    written: list[Path] = []

    for day, summary in sorted(groups.items()):
        md = render_journal(summary)
        out = vault_dir / f"{day}.md"
        out.write_text(md, encoding="utf-8")
        written.append(out)
        print(
            f"[ok] {out.name} — {summary.total_trades} trades, P&L {summary.daily_pnl:+.2f}"
        )

    return written


if __name__ == "__main__":
    # If no real CSV exists, generate sample data for testing
    csv_to_use = CSV_PATH
    if not CSV_PATH.exists():
        print("[info] paper_trade_log.csv not found — using sample data")
        write_sample_csv(SAMPLE_CSV)
        csv_to_use = SAMPLE_CSV

    outputs = generate(csv_path=csv_to_use)
    if outputs:
        print(f"\n[V] {len(outputs)} journal(s) written to {VAULT_DIR}")
    else:
        print("\n[done] nothing to write")
