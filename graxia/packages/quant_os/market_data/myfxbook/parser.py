"""Parse Myfxbook account page HTML into AccountSummary.

Strategy: strip script/style blocks, then flatten tags to a text stream and
match line-anchored labels. Tolerant by design: a missing stat becomes None,
never a crash.
"""

import html
import re

from market_data.myfxbook.models import AccountSummary

_LABELS: dict[str, str] = {
    "Gain": "gain_pct",
    "Abs. Gain": "abs_gain_pct",
    "Daily": "daily_pct",
    "Monthly": "monthly_pct",
    "Drawdown": "max_drawdown_pct",
    "Balance": "balance",
    "Profit Factor": "profit_factor",
    "Sharpe Ratio": "sharpe",
    "Profitability": "win_rate_pct",
}


def _strip_tags(html_text: str) -> str:
    """Remove <script>/<style> blocks first (their JS/CSS is full of junk
    numbers), then flatten every remaining tag to a newline. Also strips
    markdown bold markers (**/__) — saved fetches may arrive markdown-converted."""
    cleaned = re.sub(r"<(script|style)[^>]*>.*?</\1>", "", html_text, flags=re.DOTALL | re.IGNORECASE)
    cleaned = re.sub(r"\*\*|__", "", cleaned)
    return html.unescape(re.sub(r"<[^>]+>", "\n", cleaned))


def _stat_value(text: str, label: str) -> float | None:
    """Find 'label ... +N.NN%' in flattened text.

    (?m)^\\s* anchors labels to line starts: 'Gain' can never match inside
    'Abs. Gain' (\\b would NOT prevent that — a space before 'Gain' is still
    a word boundary).
    """
    pattern = re.compile(rf"(?m)^\s*{re.escape(label)}\s*:?\s*\n?\s*([A-Za-z\s]*[+-]?[\d][\d,]*(?:\.\d+)?)%?")
    match = pattern.search(text)
    if not match:
        return None
    raw = match.group(1).replace(",", "").strip()
    if not re.search(r"\d", raw):
        return None
    return float(re.sub(r"[^0-9+\-.]", "", raw))


def _int_value(text: str, label: str) -> int | None:
    match = re.search(rf"(?m)^\s*{re.escape(label)}\s*:?\s*\n?\s*([\d,]+)", text)
    if not match:
        return None
    return int(match.group(1).replace(",", ""))


def parse_account_summary(html_text: str, *, account_id: int, member: str, system: str, url: str) -> AccountSummary:
    """Parse the stats block. Missing values stay None. Never raises on bad input."""
    text = _strip_tags(html_text)
    values: dict[str, object] = {"account_id": account_id, "member": member, "system": system, "url": url}
    for label, field in _LABELS.items():
        values[field] = _stat_value(text, label)
    values["total_trades"] = _int_value(text, "Trades")
    values["tracked_months"] = _int_value(text, "Tracking")
    return AccountSummary(**values)
