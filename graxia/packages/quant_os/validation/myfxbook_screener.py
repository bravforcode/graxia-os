"""
Myfxbook red-flag screener.

Implements the evidence-based screening framework for externally-published
Myfxbook trading signals / systems. The screener takes stats that were *read
off the page* (no trust, no hype -- only what the page actually shows) and
applies a set of INDEPENDENT red-flag heuristics for common Myfxbook
distortions. Only ONE threshold is shared with ``validation/decision_gates.yaml``
(``minimum_effective_oos_trades: 100`` -> the TRADES_INSUFFICIENT rule). The
remaining thresholds (DD 40%, leverage 500/1000x, Sharpe 0.5, etc.) are
screener-local heuristics and are NOT derived from that file. See the
PROVENANCE block above ``screen()`` for the full side-by-side.

It does NOT fetch pages (Myfxbook is JS-rendered / bot-protected). Feed it the
stats you extracted, or a JSON export. Every flag carries the exact evidence
value that triggered it, so nothing is asserted without a source number.

Provenance is mandatory: every screened account must carry ``source_url`` and
``fetched_at`` (ISO 8601). The CLI enforces this; the library raises only when
``require_provenance=True`` so unit tests can build synthetic stats. Stale data
(> ``stale_hours`` in myfxbook_gates.yaml) triggers a warning, because Myfxbook
stats update live and a stale fetch can silently misrepresent the account.

Usage (single account, JSON file -- provenance required):
    python -m quant_os.validation.myfxbook_screener path/to/stats.json

Usage (batch -- builds the real-vs-advertised comparison table):
    python -m quant_os.validation.myfxbook_screener batch.json   # JSON list

Usage (built-in verified example -- superbreakout-h1-5):
    python -m quant_os.validation.myfxbook_screener
"""

from __future__ import annotations

import datetime
import json
import os
import sys
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

import yaml


class Severity(str, Enum):
    CRITICAL = "CRITICAL"
    HIGH = "HIGH"
    MEDIUM = "MEDIUM"
    INFO = "INFO"


class Verdict(str, Enum):
    PASS = "PASS"
    REVIEW = "REVIEW"
    FAIL = "FAIL"


_SEV_RANK = {Severity.CRITICAL: 3, Severity.HIGH: 2, Severity.MEDIUM: 1, Severity.INFO: 0}


@dataclass
class RedFlag:
    code: str
    severity: Severity
    title: str
    evidence: str
    rule: str


@dataclass
class MyfxbookStats:
    # identity
    account_name: str = ""
    trader: str = ""
    broker: str = ""
    account_type: str = ""  # Real / Demo
    leverage: str = ""  # e.g. "1:2000"
    platform: str = ""
    claimed_timeframe: str = ""  # what the NAME implies, e.g. "H1"

    # performance
    gain_pct: float | None = None
    abs_gain_pct: float | None = None
    daily_pct: float | None = None
    monthly_pct: float | None = None
    drawdown_pct: float | None = None
    balance: float | None = None
    equity: float | None = None
    deposits: float | None = None
    withdrawals: float | None = None

    # trades
    trades: int | None = None
    avg_win_pips: float | None = None
    avg_loss_pips: float | None = None
    avg_win_money: float | None = None
    avg_loss_money: float | None = None
    lots: float | None = None
    longs_won: int | None = None
    longs_total: int | None = None
    shorts_won: int | None = None
    shorts_total: int | None = None
    avg_trade_length: str = ""  # avg trade DURATION (hold time, open->close), e.g. "15s", "16h" -- NOT trade frequency
    profit_factor: float | None = None
    sharpe: float | None = None
    expectancy_pips: float | None = None
    expectancy_money: float | None = None

    # time
    started: str = ""
    age_days: int | None = None
    last_update: str = ""

    # provenance (mandatory for any real screen)
    source_url: str = ""
    fetched_at: str = ""  # ISO 8601, e.g. "2026-07-24" or "2026-07-24T12:00:00+00:00"

    # extras
    raw: dict[str, Any] = field(default_factory=dict)


@dataclass
class ScreenResult:
    stats: MyfxbookStats
    flags: list[RedFlag]
    verdict: Verdict
    notes: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


def _parse_leverage_frac(lev: str) -> float:
    """``"1:2000"`` -> 2000.0 ; ``""`` -> 0.0."""
    if not lev:
        return 0.0
    try:
        return float(str(lev).split(":")[-1].replace(",", ""))
    except (ValueError, IndexError):
        return 0.0


def _parse_trade_length_seconds(s: str) -> float | None:
    """``"15s"`` -> 15 ; ``"16h"`` -> 57600 ; ``"2d"`` -> 172800 ; ``""`` -> None."""
    if not s:
        return None
    s = str(s).strip().lower()
    mult = {"s": 1, "m": 60, "h": 3600, "d": 86400, "w": 604800}
    for unit, factor in mult.items():
        if s.endswith(unit):
            try:
                return float(s[:-1]) * factor
            except ValueError:
                return None
    try:
        return float(s)
    except ValueError:
        return None


def _win_rate(stats: MyfxbookStats) -> float | None:
    won = (stats.longs_won or 0) + (stats.shorts_won or 0)
    tot = (stats.longs_total or 0) + (stats.shorts_total or 0)
    if tot == 0:
        return None
    return 100.0 * won / tot


_GATES_CACHE: dict[str, Any] | None = None


def _load_gates() -> dict[str, Any]:
    """Load screener thresholds from ``myfxbook_gates.yaml``.

    ``trades_min`` is the one value shared with ``decision_gates.yaml``; it is
    read from there directly so the two files cannot silently drift apart.
    """
    global _GATES_CACHE
    if _GATES_CACHE is not None:
        return _GATES_CACHE
    here = os.path.dirname(os.path.abspath(__file__))
    with open(os.path.join(here, "myfxbook_gates.yaml"), encoding="utf-8") as fh:
        gates = yaml.safe_load(fh)
    dg_path = os.path.join(here, "decision_gates.yaml")
    with open(dg_path, encoding="utf-8") as fh:
        dg = yaml.safe_load(fh)
    gates["trades_min"] = dg["xau_candidate_gate"]["minimum_effective_oos_trades"]
    _GATES_CACHE = gates
    return gates


def _parse_fetched_at(s: str) -> datetime.datetime:
    """Parse an ISO-8601 timestamp into a timezone-aware datetime (UTC if naive)."""
    dt = datetime.datetime.fromisoformat(s)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=datetime.UTC)
    return dt


# ---------------------------------------------------------------------------
# PROVENANCE / THRESHOLD SOURCES  (side-by-side with validation/decision_gates.yaml)
# ---------------------------------------------------------------------------
# Rule                  | Screener threshold           | Source
# --------------------- | ---------------------------- | --------------------------------
# TRADES_INSUFFICIENT   | trades < 100                 | decision_gates.yaml: minimum_effective_oos_trades: 100   ✅ TRACES
# AGE_SHORT             | age_days < 180               | LOOSE: yaml minimum_time_segments: 12  (screener maps 12 segments -> 180d; NOT literal)
# DD_HIGH / DD_ELEVATED | >=40% / 25-40%               | screener-local heuristic   ❌ not in yaml
# LEVERAGE_HIGH         | >=500x (HIGH if >=1000x)     | screener-local heuristic   ❌ not in yaml
# GAIN_ABS_DIVERGENCE   | ratio>=3x / gap>200pp        | screener-local heuristic   ❌ not in yaml
# WIN_SMALL_LOSE_BIG    | wr>=70 & loss>1.5*win        | screener-local heuristic   ❌ not in yaml
# TIMEFRAME_CONTRADICTION| h1 name & dur<3600s         | screener-local heuristic   ❌ not in yaml
# PF_UNSTABLE           | PF>=2 & trades<50            | screener-local heuristic   ❌ not in yaml
# SHARPE_LOW            | <0.5                         | screener-local heuristic   ❌ not in yaml
# DEMO_ACCOUNT          | type contains "demo"         | screener-local heuristic   ❌ not in yaml
#
# decision_gates.yaml is the BE-P6 XAU *candidate* gate (stress tests, segment
# expectancy, oracle alignment, ledger integrity...). It does NOT define Myfxbook
# red-flag thresholds. The screener is a SEPARATE, independent due-diligence
# filter. Do not attribute its verdicts to decision_gates.yaml.
# ---------------------------------------------------------------------------


def screen(stats: MyfxbookStats, require_provenance: bool = False) -> ScreenResult:
    """Apply the red-flag rules. Returns a :class:`ScreenResult` with evidence."""
    flags: list[RedFlag] = []
    warnings: list[str] = []
    gates = _load_gates()

    # R1: Gain vs Abs Gain divergence (withdrawal / deposit distortion)
    if stats.gain_pct is not None and stats.abs_gain_pct is not None:
        if stats.abs_gain_pct > 0:
            ratio = stats.gain_pct / stats.abs_gain_pct
            if ratio >= gates["gain_abs_divergence_ratio"]:
                flags.append(
                    RedFlag(
                        code="GAIN_ABS_DIVERGENCE",
                        severity=Severity.HIGH,
                        title="Gain ห่างจาก Abs Gain มากผิดปกติ",
                        evidence=f"Gain={stats.gain_pct:.2f}% vs AbsGain={stats.abs_gain_pct:.2f}% (ratio {ratio:.1f}x)",
                        rule="Gain/AbsGain >= 3x มักบ่งบอกการฝาก/ถอนระหว่างทางทำให้เปอร์เซ็นต์เพี้ยน",
                    )
                )
        if stats.gain_pct - stats.abs_gain_pct > gates["gain_abs_gap_pp"]:
            flags.append(
                RedFlag(
                    code="GAIN_ABS_GAP_PP",
                    severity=Severity.MEDIUM,
                    title="ช่องว่าง Gain-AbsGain เกิน 200 pp",
                    evidence=f"Gap={stats.gain_pct - stats.abs_gain_pct:.2f} pp",
                    rule="ช่องว่างใหญ่ = ฐานทุน/การถอนทำให้ตัวเลขดูสวยเกินจริง",
                )
            )

    # R2: Max drawdown too high
    if stats.drawdown_pct is not None:
        if stats.drawdown_pct >= gates["dd_high"]:
            flags.append(
                RedFlag(
                    code="DD_HIGH",
                    severity=Severity.HIGH,
                    title="Max Drawdown สูงเกินเกณฑ์",
                    evidence=f"Drawdown={stats.drawdown_pct:.2f}%",
                    rule="DD >= 40% เกินระดับความเสี่ยงที่รับได้สำหรับระบบใช้งานเงินจริง",
                )
            )
        elif stats.drawdown_pct >= gates["dd_elevated"]:
            flags.append(
                RedFlag(
                    code="DD_ELEVATED",
                    severity=Severity.MEDIUM,
                    title="Max Drawdown สูงปานกลาง",
                    evidence=f"Drawdown={stats.drawdown_pct:.2f}%",
                    rule="DD 25-40% ควรระวังและต้องชดเชยด้วยผลตอบแทนสูงพอ",
                )
            )

    # R3: Account age / sample size (mirrors decision_gates.yaml)
    if stats.age_days is not None and stats.age_days < gates["age_days_min"]:
        flags.append(
            RedFlag(
                code="AGE_SHORT",
                severity=Severity.HIGH,
                title="อายุบัญชีสั้นเกินไป",
                evidence=f"Age={stats.age_days} วัน (< {gates['age_days_min']} วัน)",
                rule="decision_gates ต้องการ >= 12 time segments; ข้อมูล < 6 เดือนไม่พอพิสูจน์ edge",
            )
        )
    if stats.trades is not None and stats.trades < gates["trades_min"]:
        flags.append(
            RedFlag(
                code="TRADES_INSUFFICIENT",
                severity=Severity.HIGH,
                title="จำนวนเทรดไม่พอ",
                evidence=f"Trades={stats.trades} (< {gates['trades_min']})",
                rule="decision_gates minimum_effective_oos_trades: 100",
            )
        )

    # R4: Leverage too high
    lev = _parse_leverage_frac(stats.leverage)
    if lev >= gates["leverage_high"]:
        flags.append(
            RedFlag(
                code="LEVERAGE_HIGH",
                severity=Severity.HIGH if lev >= gates["leverage_critical"] else Severity.MEDIUM,
                title="เลเวอเรจสูงผิดปกติ",
                evidence=f"Leverage={stats.leverage} (={lev:.0f}x)",
                rule="เลเวอเรจ >= 500x (โดยเฉพาะ >=1000x) บ่งบอกโบรกเกอร์ offshore + ความเสี่ยงล้างพอร์ต",
            )
        )

    # R5: Win rate vs avg win/avg loss (win-small-lose-big)
    wr = _win_rate(stats)
    if wr is not None and stats.avg_win_pips is not None and stats.avg_loss_pips is not None:
        loss_abs = abs(stats.avg_loss_pips)
        if wr >= gates["win_rate_high"] and loss_abs > stats.avg_win_pips * gates["win_loss_ratio"]:
            flags.append(
                RedFlag(
                    code="WIN_SMALL_LOSE_BIG",
                    severity=Severity.MEDIUM,
                    title="ชนะบ่อยแต่แพ้ทีเดียวหนัก (win-small-lose-big)",
                    evidence=f"Win%={wr:.0f}%, AvgWin={stats.avg_win_pips:.1f} vs AvgLoss={stats.avg_loss_pips:.1f} pips",
                    rule="แพ้ครั้งเดียวอาจลบล้างกำไรหลายครั้ง",
                )
            )

    # R6: Structural contradiction -- claimed timeframe vs actual trade length
    if stats.claimed_timeframe and stats.avg_trade_length:
        secs = _parse_trade_length_seconds(stats.avg_trade_length)
        if (
            secs is not None
            and secs < gates["timeframe_contradiction_seconds"]
            and "h1" in stats.claimed_timeframe.lower()
        ):
            flags.append(
                RedFlag(
                    code="TIMEFRAME_CONTRADICTION",
                    severity=Severity.CRITICAL,
                    title="ชื่ออ้าง timeframe ขัดแย้งกับพฤติกรรมจริง",
                    evidence=f"Claimed={stats.claimed_timeframe}, AvgTradeLength={stats.avg_trade_length} ({secs:.0f}s)",
                    rule=f"ชื่อบอก H1 แต่เทรดยาวแค่ {secs:.0f}s = scalper ตั้งชื่อ misleading",
                )
            )

    # R7: Profit factor with few trades (unstable stats)
    if stats.profit_factor is not None and stats.trades is not None:
        if stats.profit_factor >= gates["pf_unstable"] and stats.trades < gates["pf_unstable_trades"]:
            flags.append(
                RedFlag(
                    code="PF_UNSTABLE",
                    severity=Severity.MEDIUM,
                    title="PF สวยแต่เทรดน้อย (สถิติไม่นิ่ง)",
                    evidence=f"PF={stats.profit_factor:.2f}, Trades={stats.trades}",
                    rule="PF สูงกับ sample เล็กพังง่ายเมื่อเจอ regime ใหม่",
                )
            )

    # R8: Sharpe too low
    if stats.sharpe is not None and stats.sharpe < gates["sharpe_low"]:
        flags.append(
            RedFlag(
                code="SHARPE_LOW",
                severity=Severity.MEDIUM,
                title="Sharpe ต่ำ (ผลตอบแทนปรับความเสี่ยงแย่)",
                evidence=f"Sharpe={stats.sharpe:.2f}",
                rule="Sharpe < 0.5 บ่งบอก edge ปรับความเสี่ยงแล้วอ่อน",
            )
        )

    # R9: Demo account
    if stats.account_type and "demo" in stats.account_type.lower():
        flags.append(
            RedFlag(
                code="DEMO_ACCOUNT",
                severity=Severity.HIGH,
                title="บัญชี Demo -- ไม่มีความหมายกับเงินจริง",
                evidence=f"Account type={stats.account_type}",
                rule="ผล Demo ไม่สะท้อนสภาพคล่อง/slippage/psychology ของเงินจริง",
            )
        )

    # Provenance gate (doc-13 lesson): numbers must be attributed + fresh.
    if not stats.source_url or not stats.fetched_at:
        warnings.append(
            "No source_url/fetched_at on input -- numbers are unattributed. "
            "Re-fetch from the live Myfxbook page before trusting this screen."
        )
        if require_provenance:
            raise ValueError(
                "Refusing to screen: source_url and fetched_at are required "
                "(require_provenance=True). Never screen hand-recalled or "
                "unattributed numbers."
            )
    else:
        try:
            fetched = _parse_fetched_at(stats.fetched_at)
        except ValueError:
            warnings.append(f"fetched_at '{stats.fetched_at}' is not valid ISO 8601; cannot assess staleness.")
        else:
            age = datetime.datetime.now(datetime.UTC) - fetched
            if age > datetime.timedelta(hours=gates["stale_hours"]):
                warnings.append(
                    f"Data is {age} old (> {gates['stale_hours']}h) -- re-fetch recommended; "
                    "Myfxbook stats update live and may no longer match this account."
                )

    # Verdict
    max_sev = max((_SEV_RANK[f.severity] for f in flags), default=0)
    if max_sev >= 3 or (stats.drawdown_pct is not None and stats.drawdown_pct >= gates["dd_high"]):
        verdict = Verdict.FAIL
    elif max_sev >= 1:
        verdict = Verdict.REVIEW
    else:
        verdict = Verdict.PASS

    notes: list[str] = []
    if stats.gain_pct is not None and stats.abs_gain_pct is not None:
        notes.append(
            f"อ่าน Gain/AbsGain: Gain={stats.gain_pct:.2f}% เป็น time-weighted "
            f"ส่วน AbsGain={stats.abs_gain_pct:.2f}% คือผลเทียบเงินฝากจริง -- ดูอันหลังด้วยเสมอ"
        )
    if not flags:
        notes.append("ไม่พบ red flag จากข้อมูลที่ให้มา (แต่ยังต้องตรวจ equity-curve เต็มรูปแบบเพิ่มเติม)")

    return ScreenResult(stats=stats, flags=flags, verdict=verdict, notes=notes, warnings=warnings)


def generate_report(result: ScreenResult) -> str:
    s = result.stats
    lines: list[str] = []
    lines.append("=" * 64)
    lines.append("MYFXBOOK RED-FLAG SCREEN")
    lines.append("=" * 64)
    lines.append(f"Account : {s.account_name} ({s.trader})")
    lines.append(f"Broker  : {s.broker} | {s.account_type} | Lev {s.leverage} | {s.platform}")
    lines.append(f"Claimed : {s.claimed_timeframe or 'n/a'}")
    lines.append("-" * 64)
    lines.append(f"Gain={s.gain_pct}  AbsGain={s.abs_gain_pct}  DD={s.drawdown_pct}%")
    lines.append(f"Trades={s.trades}  PF={s.profit_factor}  Sharpe={s.sharpe}")
    lines.append(f"AvgWin={s.avg_win_pips}p  AvgLoss={s.avg_loss_pips}p  Lots={s.lots}")
    lines.append(f"TradeLen={s.avg_trade_length}  Age={s.age_days}d")
    lines.append("-" * 64)
    lines.append(f"VERDICT : {result.verdict.value}")
    lines.append("-" * 64)
    if result.flags:
        ordered = sorted(result.flags, key=lambda f: _SEV_RANK[f.severity], reverse=True)
        for f in ordered:
            lines.append(f"[{f.severity.value}] {f.code}: {f.title}")
            lines.append(f"    evidence : {f.evidence}")
            lines.append(f"    rule     : {f.rule}")
    else:
        lines.append("No red flags from provided data.")
    if result.warnings:
        lines.append("-" * 64)
        for w in result.warnings:
            lines.append(f"warn: {w}")
    lines.append("-" * 64)
    for n in result.notes:
        lines.append(f"note: {n}")
    lines.append("=" * 64)
    return "\n".join(lines)


def generate_batch_table(results: list[ScreenResult]) -> str:
    """Real-vs-advertised comparison table across multiple accounts."""
    header = f"{'Account':<28} {'Verdict':<8} {'#Flags':<7} {'TopFlag'}"
    lines = [header, "-" * len(header)]
    for r in results:
        top = max(r.flags, key=lambda f: _SEV_RANK[f.severity]).code if r.flags else "-"
        name = r.stats.account_name[:27]
        lines.append(f"{name:<28} {r.verdict.value:<8} {len(r.flags):<7} {top}")
    return "\n".join(lines)


def _example_superbreakout() -> MyfxbookStats:
    """Verified stats from members/Pisansri/superbreakout-h1-5/12117953 (This-Year view).

    Data is externalized to ``validation/fixtures/superbreakout_h1_5_20260722.json``
    so the provenance (source URL + fetch date) travels with it. See that file's
    sibling PROVENANCE.md.
    """
    here = os.path.dirname(os.path.abspath(__file__))
    path = os.path.join(here, "fixtures", "superbreakout_h1_5_20260722.json")
    with open(path, encoding="utf-8") as fh:
        data = json.load(fh)
    return _load_stats_from_dict(data)


def _load_stats_from_dict(data: dict[str, Any]) -> MyfxbookStats:
    known = {f for f in MyfxbookStats.__dataclass_fields__}  # type: ignore[attr-defined]
    clean = {k: v for k, v in data.items() if k in known}
    extra = {k: v for k, v in data.items() if k not in known}
    stats = MyfxbookStats(**clean)
    stats.raw = extra
    return stats


def main(argv: list[str]) -> int:
    # Windows consoles default to a non-UTF8 codepage; the report contains Thai
    # text, so reconfigure stdout defensively (no-op on terminals that already
    # emit UTF-8). errors="replace" keeps the run alive if a glyph is missing.
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")  # type: ignore[attr-defined]
    except Exception:
        pass
    if len(argv) > 1:
        path = argv[1]
        with open(path, encoding="utf-8") as fh:
            data = json.load(fh)
        if isinstance(data, list):
            results = [screen(_load_stats_from_dict(d), require_provenance=True) for d in data]
            print(generate_batch_table(results))
            for r in results:
                print()
                print(generate_report(r))
            return 0
        stats = _load_stats_from_dict(data)
        try:
            result = screen(stats, require_provenance=True)
        except ValueError as exc:
            print(f"ERROR: {exc}", file=sys.stderr)
            return 2
    else:
        stats = _example_superbreakout()
        result = screen(stats)
    print(generate_report(result))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
