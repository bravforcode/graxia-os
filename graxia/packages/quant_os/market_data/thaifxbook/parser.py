"""Parsers for Thaifxbook public pages.

All pages are Next.js RSC flight payloads (see ``rsc.py``). These parsers run
label-anchored regexes over the decoded payload — the same strategy the myfxbook
collector uses on flattened HTML — and are tested against real saved fixtures in
``fixtures/``.

Money masking: accounts that opted to hide money fields render ``***``. Parsers
return ``None`` for those (missing != zero, see ``models.py``).

Trade-history pagination: the initial RSC payload only contains the first page
of closed trades. Plain-HTTP collection therefore captures page 1 only; full
history needs the pagination path (browser session or authenticated endpoint).
"""

from __future__ import annotations

import json
import re
from datetime import datetime

from .models import ProfileSnapshot, SentimentSnapshot, TradeRecord
from .rsc import decode_flight_payload

# ---------------------------------------------------------------------------
# value helpers
# ---------------------------------------------------------------------------

_AMOUNT = r"(?:\d[\d,]*(?:\.\d+)?)"

# "$1,132.92", "$$40.52", "-$1.1M", "+$292", "¢93,792.61", "***"
_MONEY_RE = re.compile(rf"^(?P<sign>[+-]?)\${{1,2}}?(?P<val>{_AMOUNT})(?P<sfx>[KMB]?)$")
_CENT_RE = re.compile(rf"^(?P<sign>[+-]?)¢(?P<val>{_AMOUNT})(?P<sfx>[KMB]?)$")


def parse_money(raw: str) -> float | None:
    """Parse a platform money string to float USD (cents => /100), None if masked."""
    if raw is None or raw.strip() in ("", "***", "—", "-"):
        return None
    s = raw.strip().replace(",", "")
    m = _MONEY_RE.match(s)
    if m:
        val = float(m.group("val"))
        sfx = m.group("sfx")
        if sfx == "K":
            val *= 1_000
        elif sfx == "M":
            val *= 1_000_000
        elif sfx == "B":
            val *= 1_000_000_000
        return val if m.group("sign") != "-" else -val
    m = _CENT_RE.match(s)
    if m:
        val = float(m.group("val")) / 100.0
        sfx = m.group("sfx")
        if sfx == "K":
            val *= 1_000
        elif sfx == "M":
            val *= 1_000_000
        return val if m.group("sign") != "-" else -val
    # e.g. "1,431.05" bare number
    try:
        return float(s)
    except ValueError:
        return None


def parse_pct(raw: str) -> float | None:
    if raw is None or raw.strip() in ("", "***", "—", "-"):
        return None
    s = raw.strip().replace("%", "").replace(",", "")
    try:
        return float(s)
    except ValueError:
        return None


def parse_int(raw: str) -> int | None:
    if raw is None or raw.strip() in ("", "***", "—", "-"):
        return None
    s = raw.strip().replace(",", "")
    try:
        return int(float(s))
    except ValueError:
        return None


# ---------------------------------------------------------------------------
# label-value card extraction (profile stats)
# ---------------------------------------------------------------------------

# Stat cards (Profit Factor, Sharpe, win rate, ...) and money/% cards
# (กำไร, ยอดเงิน, ฝากเงิน, ...) share one layout; only padding differs:
#   ["$","div","LABEL",{"className":"flex items-center justify-between px-5 py-(2.5|3)",
#     "children":[["$","span",null,{...label...}],["$","span",null,{...VALUE...}]]}]
# The VALUE is the first span whose className contains "font-semibold" after the
# label; help tooltips (svg + invisible span) never carry font-semibold.
# RSC element markers are ["$","span",null,{...}] — bracket quote-dollar quote.
_KV_RE_TMPL = (
    r'"{label}",\{"className":"flex items-center justify-between px-5 py-(?:2\.5|3)","children":'
    r'\[.*?\["\$","span",null,\{"className":"[^"]*font-semibold[^"]*","children":"([^"]*)"\}\]'
)

# Identity block (account name, broker, start date, ...) uses p-blocks:
#   ["$","div","LABEL",{"className":"px-5 py-4 min-w-0 border-border ",
#     "children":[["$","p",...,{"children":"LABEL"}],["$","p",...,{"children":"VALUE"}]]}]
_PBLOCK_RE_TMPL = (
    r'"{label}",\{"className":"px-5 py-4[^"]*","children":'
    r'\[\["\$","p",null,\{"className":"[^"]*","children":"{label}"\}\],'
    r'\["\$","p",null,\{"className":"[^"]*"(?:,"title":"[^"]*")?,"children":"([^"]*)"\}\]\]\}'
)

# AI score bars: value is a NUMBER span at the end of the bar row:
#   ["$","div","ความแม่นยำ",{"className":"flex items-center gap-3",...["$","span",...,"children":9.7}]}]
# closing = `"children":9.7` + `}]` (span) + `]` (children) + `}` (div)
_AI_RE_TMPL = r'"{label}",\{"className":"flex items-center gap-3".*?"children":(\d+(?:\.\d+)?)\}\]\]\}'


def _build(tmpl: str, label: str) -> re.Pattern[str]:
    # re.S: decoded payload chunks are joined with "\n"; a card can span chunks.
    return re.compile(tmpl.replace("{label}", re.escape(label)), re.S)


def _kv_all(text: str, label: str) -> list[str]:
    """Return values of every label-value card matching ``label`` (in order)."""
    return _build(_KV_RE_TMPL, label).findall(text)


def _kv(text: str, label: str) -> str | None:
    vals = _kv_all(text, label)
    return vals[0] if vals else None


def _pblock(text: str, label: str) -> str | None:
    m = _build(_PBLOCK_RE_TMPL, label).search(text)
    return m.group(1) if m else None


def _ai(text: str, label: str) -> float | None:
    m = _build(_AI_RE_TMPL, label).search(text, re.S)
    return float(m.group(1)) if m else None


def _verified(text: str) -> bool | None:
    """verified badge: 'ยืนยันแล้ว' (verified) / 'ยังไม่ยืนยันบัญชี' (not)."""
    if "ยืนยันแล้ว" in text:
        return True
    if "ยังไม่ยืนยัน" in text:
        return False
    return None


def _ea_split(text: str) -> tuple[float | None, float | None]:
    """EA/manual % from the bar widths in the 'ประเภทการเทรด' block."""
    i = text.find("EA + เทรดมือ")
    if i < 0:
        return None, None
    widths = re.findall(r'"width":"(\d+(?:\.\d+)?)%"', text[i : i + 800])
    if len(widths) >= 2:
        return float(widths[0]), float(widths[1])
    if widths:
        return float(widths[0]), None
    return None, None


# ---------------------------------------------------------------------------
# outlook
# ---------------------------------------------------------------------------

_ROW_SPLIT = re.compile(r'"href":"/tools/outlook/')
_ASSET_DISPLAY_RE = re.compile(r'"children":"([A-Z0-9]+/[A-Z0-9]+)"')
_PCT_RE = re.compile(r'"children":\[(\d+),"%"\]')
_TRADERS_RE = re.compile(r'"w-16 text-right[^"]*","children":(\d+)')
_LOTS_RE = re.compile(r'"w-20 text-right[^"]*","children":"([\d.]+)"')
_PL_RE = re.compile(r'text-(?:red|green)-400[^"]*","children":"([^"]+)"')


def parse_outlook(html: str, ts: datetime | None = None) -> list[SentimentSnapshot]:
    """Parse /tools/outlook rows from RSC HTML into SentimentSnapshot list."""
    ts = ts or datetime.now()
    decoded = decode_flight_payload(html)
    rows: list[SentimentSnapshot] = []
    for seg in _ROW_SPLIT.split(decoded)[1:]:
        pair_key = seg.split('"', 1)[0]
        m = _ASSET_DISPLAY_RE.search(seg)
        display = m.group(1) if m else pair_key.upper()
        pcts = _PCT_RE.findall(seg)
        traders = _TRADERS_RE.search(seg)
        lots = _LOTS_RE.search(seg)
        pl = _PL_RE.search(seg)
        rows.append(
            SentimentSnapshot(
                ts=ts,
                asset=pair_key.upper(),
                asset_display=display,
                long_pct_by_trader=float(pcts[0]) if len(pcts) > 0 else None,
                short_pct_by_trader=float(pcts[1]) if len(pcts) > 1 else None,
                traders=int(traders.group(1)) if traders else None,
                lots=float(lots.group(1)) if lots else None,
                floating_pl_usd=parse_money(pl.group(1)) if pl else None,
            )
        )
    return rows


# ---------------------------------------------------------------------------
# trades
# ---------------------------------------------------------------------------

# The profile page embeds full trade objects as JSON inside the RSC payload:
#   {"id":"<uuid>","ticket":123,"symbol":"XAUUSDm","trade_type":"buy",
#    "volume":0.01,"profit":0.82,"close_time":"...","open_time":"...",
#    "open_price":4263.5,"close_price":4264.319,"pips":81.9,"sl":0,"tp":0,
#    "comment":""}
_TRADE_OBJ_RE = re.compile(r'\{"id":"[0-9a-f-]{36}","ticket":\d+.*?\}')


def parse_trades(html: str, account_uuid: str, ts: datetime | None = None) -> list[TradeRecord]:
    """Parse embedded trade objects, deduped by ticket, newest first.

    Caveat (verified 2026-08-06): the payload contains BOTH closed trades and
    open positions. For accounts that hide their closed history (masked, e.g.
    Gremax) only open positions are present; for public-history accounts (e.g.
    PutDejudom) the objects are the closed trades. Callers must not assume all
    returned records are closed trades — check close_time.
    """
    ts = ts or datetime.now()
    decoded = decode_flight_payload(html)
    seen: set[int] = set()
    records: list[TradeRecord] = []
    seq = 0
    for raw in _TRADE_OBJ_RE.findall(decoded):
        try:
            obj = json.loads(raw)
        except json.JSONDecodeError:  # pragma: no cover - defensive
            continue
        ticket = int(obj.get("ticket"))
        if ticket in seen:
            continue
        seen.add(ticket)
        side = str(obj.get("trade_type", "")).lower()
        records.append(
            TradeRecord(
                account_uuid=account_uuid,
                ts=ts,
                seq=seq,
                ticket=ticket,
                symbol=str(obj.get("symbol", "")),
                side=side,
                lots=float(obj["volume"]) if obj.get("volume") is not None else 0.0,
                pnl_usd=float(obj["profit"]) if obj.get("profit") is not None else 0.0,
                close_time=str(obj.get("close_time", "")),
                open_time=str(obj.get("open_time")) or None,
                open_price=float(obj["open_price"]) if obj.get("open_price") is not None else None,
                close_price=float(obj["close_price"]) if obj.get("close_price") is not None else None,
                pips=float(obj["pips"]) if obj.get("pips") is not None else None,
                sl=float(obj["sl"]) if obj.get("sl") is not None else None,
                tp=float(obj["tp"]) if obj.get("tp") is not None else None,
                comment=str(obj.get("comment")) or None,
            )
        )
        seq += 1
    return records


# ---------------------------------------------------------------------------
# profile
# ---------------------------------------------------------------------------

_IDENTITY_FIELDS = [
    "ชื่อบัญชี",
    "โบรคเกอร์",
    "สกุลเงิน / Leverage",
    "สถานะบัญชี",
    "เริ่มต้น",
    "สไตล์การเทรด",
    "รูปแบบกลยุทธ์",
    "ซิงค์ล่าสุด",
]
_STAT_FIELDS = [
    "กำไร",
    "กำไรสัมบูรณ์",
    "รายวัน",
    "รายเดือน",
    "Drawdown",
    "ยอดเงิน",
    "Equity",
    "สูงสุด",
    "ฝากเงิน",
    "ถอนเงิน",
    "Profit Factor",
    "Expected Payoff",
    "Expectancy (pips)",
    "Sharpe Ratio",
    "อัตราชนะ",
    "กำไรเฉลี่ย",
    "ขาดทุนเฉลี่ย",
    "เทรดที่ดีที่สุด",
    "เทรดที่แย่ที่สุด",
    "เวลาถือเฉลี่ย",
    "Lots รวม",
]
_AI_FIELDS = ["ความแม่นยำ", "การทำกำไร", "คุมความเสี่ยง", "ความสม่ำเสมอ", "การฟื้นตัว"]


def parse_profile(html: str, account_uuid: str, ts: datetime | None = None) -> ProfileSnapshot:
    ts = ts or datetime.now()
    decoded = decode_flight_payload(html)

    def s(label: str) -> str | None:
        return _kv(decoded, label)

    def p(label: str) -> str | None:
        return _pblock(decoded, label)

    # JSON-LD ProfilePage -> Person (trader identity, most reliable source).
    trader = None
    for raw in re.findall(r'"__html":"((?:[^"\\]|\\.)*)"', decoded):
        try:
            once = json.loads('"' + raw + '"')
            obj = json.loads(once)
        except (json.JSONDecodeError, ValueError):
            continue
        if obj.get("@type") == "ProfilePage":
            ent = obj.get("mainEntity", {})
            if ent.get("@type") == "Person":
                trader = ent.get("name")

    rank_m = re.search(r'"children":"อันดับ #(\d+)"', decoded)
    ea_pct, manual_pct = _ea_split(decoded)

    # "กำไร" appears twice: gain % card and net-profit $ card.
    profit_cards = _kv_all(decoded, "กำไร")
    gain_pct = None
    profit_usd = None
    for card in profit_cards:
        if "%" in card:
            gain_pct = parse_pct(card)
        elif "$" in card or "¢" in card:
            profit_usd = parse_money(card)

    balance = parse_money(s("ยอดเงิน") or "")
    equity_raw = s("Equity") or ""
    equity = parse_money(equity_raw)
    if equity is None and equity_raw and "(" in equity_raw:
        m = re.search(r"([$¢][\d.,]+[KMB]?)", equity_raw)
        if m:
            equity = parse_money(m.group(1))
    max_bal_raw = s("สูงสุด") or ""
    max_balance = parse_money(max_bal_raw)
    if max_balance is None and max_bal_raw:
        m = re.search(r"([$¢][\d.,]+[KMB]?)", max_bal_raw)
        if m:
            max_balance = parse_money(m.group(1))

    masked = any(x in (s("ยอดเงิน") or s("Equity") or (profit_cards[0] if profit_cards else "")) for x in ("***",))

    return ProfileSnapshot(
        account_uuid=account_uuid,
        ts=ts,
        rank=int(rank_m.group(1)) if rank_m else None,
        trader=trader or p("เทรดเดอร์") or s("เทรดเดอร์"),
        account_name=p("ชื่อบัญชี") or s("ชื่อบัญชี"),
        broker=p("โบรคเกอร์") or s("โบรคเกอร์"),
        verified=_verified(decoded),
        leverage=p("สกุลเงิน / Leverage") or s("สกุลเงิน / Leverage"),
        start_date=p("เริ่มต้น") or s("เริ่มต้น"),
        last_sync=p("ซิงค์ล่าสุด") or s("ซิงค์ล่าสุด"),
        balance_usd=balance,
        equity_usd=equity,
        deposits_usd=parse_money(s("ฝากเงิน") or ""),
        withdrawals_usd=parse_money(s("ถอนเงิน") or ""),
        profit_usd=profit_usd,
        max_balance_usd=max_balance,
        gain_pct=gain_pct,
        abs_gain_pct=parse_pct(s("กำไรสัมบูรณ์") or ""),
        daily_pct=parse_pct(s("รายวัน") or ""),
        monthly_pct=parse_pct(s("รายเดือน") or ""),
        max_drawdown_pct=parse_pct(s("Drawdown") or ""),
        profit_factor=parse_pct(s("Profit Factor") or ""),
        expected_payoff=parse_money(s("Expected Payoff") or ""),
        sharpe=parse_pct(s("Sharpe Ratio") or ""),
        win_rate_pct=parse_pct(s("อัตราชนะ") or ""),
        total_trades=parse_int(s("จำนวนการเทรดทั้งหมด") or ""),
        ea_pct=ea_pct,
        manual_pct=manual_pct,
        avg_hold_minutes=None,
        ai_accuracy=_ai(decoded, "ความแม่นยำ"),
        ai_profitability=_ai(decoded, "การทำกำไร"),
        ai_risk=_ai(decoded, "คุมความเสี่ยง"),
        ai_consistency=_ai(decoded, "ความสม่ำเสมอ"),
        ai_recovery=_ai(decoded, "การฟื้นตัว"),
        masked=masked,
    )
