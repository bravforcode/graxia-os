"""Nightly Myfxbook collector.

Usage:
    python scripts/collect_myfxbook.py --dry-run          # live fetch, no DB/report writes
    python scripts/collect_myfxbook.py --limit 2          # first 2 pilot accounts, write DB + report
    python scripts/collect_myfxbook.py                    # full pilot run

Cadence: run nightly (scheduled). Respects config.REQUEST_DELAY_SECONDS.
"""

import argparse
import datetime
import sys
from pathlib import Path

from market_data.myfxbook import config, fetcher, report, runner_impl


def run_collection(
    accounts: list[tuple[str, str, int]],
    *,
    db_path: str | None,
    dry_run: bool = False,
    limit: int | None = None,
) -> list[dict]:
    if limit is not None:
        accounts = accounts[:limit]
    if db_path:
        runner_impl.prepare_db(db_path)  # once, not per-account
    results: list[dict] = []
    with fetcher.make_client() as client:
        for i, account in enumerate(accounts):
            member, system, account_id = account
            url = config.account_url(member, system, account_id)
            try:
                html = fetcher.fetch_account_page(client, url)
                result = runner_impl.collect_one(html, account, db_path=db_path)
            except fetcher.FetchError as exc:
                result = runner_impl._result_from_exc(account, exc)
            results.append(result)
            status = (
                "PASS" if result["filter_pass"] and not result["error"] else "FAIL" if not result["error"] else "ERROR"
            )
            print(f"[{i + 1}/{len(accounts)}] {system} ({account_id}): {status}")
            if not dry_run and i < len(accounts) - 1:
                fetcher.sleep_between_requests()

    run_date = datetime.date.today().isoformat()
    if not dry_run:
        report_dir = Path(config.REPORT_DIR)
        report_dir.mkdir(parents=True, exist_ok=True)
        (report_dir / f"{run_date}.md").write_text(report.render_markdown(results, run_date), encoding="utf-8")
    else:
        print(report.render_markdown(results, run_date))
    return results


def main() -> int:
    parser = argparse.ArgumentParser(description="Collect Myfxbook pilot accounts")
    parser.add_argument("--dry-run", action="store_true", help="fetch but do not write DB/report")
    parser.add_argument("--limit", type=int, default=None, help="only first N pilot accounts")
    parser.add_argument("--db", default=config.DB_PATH, help="sqlite path (default: data/myfxbook.db)")
    args = parser.parse_args()
    results = run_collection(
        config.PILOT_ACCOUNTS,
        db_path=None if args.dry_run else args.db,
        dry_run=args.dry_run,
        limit=args.limit,
    )
    print(f"\nDone: {len(results)} accounts collected.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
