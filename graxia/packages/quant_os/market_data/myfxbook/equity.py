"""Extract monthly equity points from Myfxbook HTML or widget JSON.

The HTML parser is SCOPED to <tr> rows: a naive YYYY-MM sweep over the whole
page picks up meta dates, GA timestamps and JS strings.
"""

import json
import re

from market_data.myfxbook.models import EquityPoint


def parse_monthly_equity_points(html: str, account_id: int) -> list[EquityPoint]:
    """Parse monthly equity rows from <tr>...</tr> table rows. Returns [] when absent."""
    points: list[EquityPoint] = []
    table_rows = re.findall(r"<tr[^>]*>.*?</tr>", html, flags=re.DOTALL | re.IGNORECASE)
    for row in table_rows:
        match = re.search(
            r"(\d{4}-\d{2})\s*</td>\s*<td[^>]*>\s*([\d][\d,]*\.?\d*)",
            row,
            flags=re.DOTALL | re.IGNORECASE,
        )
        if not match:
            continue
        month, raw = match.group(1), match.group(2).replace(",", "")
        try:
            points.append(EquityPoint(account_id=account_id, month=month, equity=float(raw)))
        except ValueError:
            continue
    return points


def parse_widget_equity_json(payload: str, account_id: int) -> list[EquityPoint]:
    """Fallback: widget JSON of shape {'data': [{'month': 'YYYY-MM', 'equity': float}]}."""
    try:
        blob = json.loads(payload)
    except (json.JSONDecodeError, TypeError):
        return []
    rows = blob.get("data", []) if isinstance(blob, dict) else []
    points: list[EquityPoint] = []
    for row in rows:
        try:
            points.append(EquityPoint(account_id=account_id, month=str(row["month"]), equity=float(row["equity"])))
        except (KeyError, TypeError, ValueError):
            continue
    return points
