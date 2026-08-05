"""Composable collection pipeline — one account = parse -> equity -> filter -> martingale -> store."""

import traceback

from market_data.myfxbook import equity, filters, martingale, parser, store
from market_data.myfxbook.models import AccountSummary


def prepare_db(db_path: str) -> None:
    """Create/verify the schema ONCE per run — never inside the per-account loop."""
    conn = store.connect(db_path)
    store.init_schema(conn)
    conn.close()


def _result_from_exc(account: tuple[str, str, int], exc: Exception) -> dict:
    member, system, account_id = account
    return {
        "account_id": account_id,
        "system": system,
        "member": member,
        "gain_pct": None,
        "max_drawdown_pct": None,
        "monthly_pct": None,
        "filter_pass": False,
        "filter_reasons": [],
        "martingale_risky": False,
        "martingale_signals": [],
        "error": f"{type(exc).__name__}: {exc}",
    }


def collect_one(
    html: str,
    account: tuple[str, str, int],
    *,
    db_path: str | None,
    thresholds: filters.QualityThresholds | None = None,
) -> dict:
    """Pipeline for one account. When db_path is given the schema MUST already
    exist — call prepare_db(db_path) once in the runner before the loop."""
    member, system, account_id = account
    url = f"https://www.myfxbook.com/members/{member}/{system}/{account_id}"
    try:
        summary: AccountSummary = parser.parse_account_summary(
            html, account_id=account_id, member=member, system=system, url=url
        )
        if summary.gain_pct is None and summary.total_trades is None:
            raise ValueError(f"no stats parsed for account {account_id}")
        points = equity.parse_monthly_equity_points(html, account_id)
        verdict = filters.evaluate_quality(summary, thresholds=thresholds)
        risk = martingale.detect_martingale(points)
        if db_path:
            conn = store.connect(db_path)
            store.upsert_account(conn, summary)
            store.insert_equity_points(conn, points)
            conn.close()
        return {
            "account_id": account_id,
            "system": system,
            "member": member,
            "gain_pct": summary.gain_pct,
            "max_drawdown_pct": summary.max_drawdown_pct,
            "monthly_pct": summary.monthly_pct,
            "filter_pass": verdict.passed,
            "filter_reasons": list(verdict.reasons),
            "martingale_risky": risk.risky,
            "martingale_signals": list(risk.signals),
            "error": None,
        }
    except Exception as exc:  # never crash the nightly run on one account
        traceback.print_exc()
        return _result_from_exc(account, exc)
