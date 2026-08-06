"""Thaifxbook public-data collector package.

Collects public portfolio-transparency data from thaifxbook.com (Thai MT5
platform) into DuckDB + raw Parquet for analytics.

Scope (P0, approved 2026-08-06):
  - This is an ANALYTICS / SENTIMENT layer, NOT a full EA-sourcing layer for
    the Deep-Mine funnel. It captures behavioral-pattern signals (aggregate
    ea_pct, trade-level prices/pips/SL/TP/timestamps) but NOT trade-level magic
    numbers, so EA identity-level dedup is out of scope (Plan B: direct MT5
    connection).
  - Public layer only: /tools/outlook sentiment + /p/{uuid} profiles + trades.
    Login-gated surfaces (feed/leaderboard/systems/brokers) are NOT collected
    here (they need a session cookie; see Phase-1 follow-ups).
"""
