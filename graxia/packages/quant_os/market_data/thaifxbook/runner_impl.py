"""Composable collection pipeline for Thaifxbook public data.

One run = fetch outlook + fetch N profile pages -> parse -> store (atomic
per-batch) -> report. Mirrors market_data/myfxbook/runner_impl.py structure
and never crashes on a single account (errors are recorded per-source).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime

from . import config
from .fetcher import FetchError, fetch_page, make_client, sleep_between_requests
from .parser import parse_outlook, parse_profile, parse_trades
from .store import ThaifxbookStore


@dataclass
class RunResult:
    ts: datetime = field(default_factory=datetime.now)
    outlook_rows: int = 0
    profiles: int = 0
    trades: int = 0
    errors: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.errors


def prepare_db(db_path: str) -> ThaifxbookStore:
    """Create/connect the DuckDB store once per run."""
    return ThaifxbookStore(db_path)


def collect_outlook(store: ThaifxbookStore, client, ts: datetime) -> int:
    html = fetch_page(client, config.OUTLOOK_URL)
    rows = parse_outlook(html, ts)
    store.upsert_sentiment_snapshots(rows)
    return len(rows)


def collect_profile(
    store: ThaifxbookStore,
    client,
    account_uuid: str,
    ts: datetime,
) -> tuple[int, int]:
    """Fetch + store one /p/{uuid}; returns (profile_count, trade_count)."""
    url = config.PROFILE_URL.format(uuid=account_uuid)
    html = fetch_page(client, url)
    profile = parse_profile(html, account_uuid, ts)
    store.upsert_profile_snapshots([profile])
    trades = parse_trades(html, account_uuid, ts)
    store.upsert_profile_trades(trades)
    return 1, len(trades)


def run(
    db_path: str,
    account_uuids: list[str],
    dry_run: bool = False,
    with_outlook: bool = True,
) -> RunResult:
    """Run one collection pass.

    ``dry_run`` still fetches (proves the pipeline) but does NOT write to the
    DB — mirroring scripts/collect_myfxbook.py --dry-run semantics.
    """
    result = RunResult()
    ts = result.ts
    store = None if dry_run else prepare_db(db_path)
    with make_client() as client:
        try:
            if with_outlook:
                if store is not None:
                    result.outlook_rows = collect_outlook(store, client, ts)
                else:
                    html = fetch_page(client, config.OUTLOOK_URL)
                    result.outlook_rows = len(parse_outlook(html, ts))
                sleep_between_requests()

            for uuid in account_uuids:
                try:
                    if store is not None:
                        p, t = collect_profile(store, client, uuid, ts)
                        result.profiles += p
                        result.trades += t
                    else:
                        html = fetch_page(client, config.PROFILE_URL.format(uuid=uuid))
                        result.profiles += 1
                        result.trades += len(parse_trades(html, uuid, ts))
                    sleep_between_requests()
                except FetchError as exc:
                    result.errors.append(f"{uuid}: {exc}")
        finally:
            if store is not None:
                store.close()
    return result
