"""Tests for tools/sentiment_backtest.py — Trial #1031 T+1 matching semantics.

Locks in the pre-registered behavior so a future edit cannot silently regress it:
- baseline = close of T   (last row on/before the sentiment date)
- outcome  = close of T+1 (first row strictly after the sentiment date)
- both anchors stay within MAX_PAIR_GAP_DAYS of the sentiment event / each other
- compute_hit_rate reports error dicts on insufficient data (never crashes)
- build_deviations emits text only for genuine pre-registration breaks
"""

from __future__ import annotations

import importlib.util
from pathlib import Path

import pandas as pd
import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
SCRIPT_PATH = REPO_ROOT / "tools" / "sentiment_backtest.py"

_spec = importlib.util.spec_from_file_location("sentiment_backtest", SCRIPT_PATH)
assert _spec is not None and _spec.loader is not None
sbt = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(sbt)

MIN_PAIRS = sbt.MIN_PAIRS
MAX_GAP = sbt.MAX_PAIR_GAP_DAYS


class FakeResult:
    def __init__(self, df: pd.DataFrame) -> None:
        self._df = df

    def fetchdf(self) -> pd.DataFrame:
        return self._df


class FakeConn:
    def __init__(self, prices: dict[str, pd.DataFrame]) -> None:
        self._prices = prices

    def execute(self, _sql: str, params: list) -> FakeResult:
        return FakeResult(self._prices.get(params[0], pd.DataFrame(columns=["close", "timestamp"])))


class FakeDuck:
    """Two-surface double for DuckDBStore: sentiment fetch + conn.execute().fetchdf()."""

    def __init__(self, sentiment: pd.DataFrame, prices: dict[str, pd.DataFrame]) -> None:
        self._sentiment = sentiment
        self.conn = FakeConn(prices)

    def get_llm_sentiment_data(self, days: int = 30) -> pd.DataFrame:
        return self._sentiment


def _sentiment(tickers: str, analyzed_at: str, sentiment: str = "positive") -> pd.DataFrame:
    return pd.DataFrame([{"tickers": tickers, "analyzed_at": analyzed_at, "sentiment": sentiment}])


def _prices(rows: list[tuple[str, float]]) -> pd.DataFrame:
    return pd.DataFrame([{"timestamp": ts, "close": close} for ts, close in rows])


# ------------------------------------------------------------- pair matching
def test_baseline_close_of_t_outcome_close_of_t1():
    """Fri sentiment -> baseline = Fri close (T), outcome = Mon close (T+1)."""
    duck = FakeDuck(
        _sentiment("AAA", "2026-07-31 10:00:00"),
        {"AAA": _prices([("2026-07-30", 100.0), ("2026-07-31", 102.0), ("2026-08-03", 104.0)])},
    )
    pairs = sbt.get_sentiment_price_pairs(duck)
    assert len(pairs) == 1
    row = pairs.iloc[0]
    assert row["sentiment_dir"] == 1
    # Baseline is 07-31 close (102), not 07-30 close (100) — the old T+0 behavior
    assert row["price_return"] == pytest.approx((104.0 - 102.0) / 102.0)
    assert row["price_dir"] == 1
    assert bool(row["match"]) is True


def test_same_day_excluded_when_no_t1_bar():
    """Sentiment on the last available day -> no T+1 outcome -> no pair."""
    duck = FakeDuck(
        _sentiment("AAA", "2026-07-31 10:00:00"),
        {"AAA": _prices([("2026-07-30", 100.0), ("2026-07-31", 102.0)])},
    )
    assert len(sbt.get_sentiment_price_pairs(duck)) == 0


def test_negative_sentiment_price_drop_matches():
    duck = FakeDuck(
        _sentiment("BBB", "2026-07-31 10:00:00", sentiment="negative"),
        {"BBB": _prices([("2026-07-31", 102.0), ("2026-08-03", 100.0)])},
    )
    pairs = sbt.get_sentiment_price_pairs(duck)
    assert len(pairs) == 1
    row = pairs.iloc[0]
    assert row["sentiment_dir"] == -1
    assert row["price_return"] < 0
    assert bool(row["match"]) is True


def test_neutral_sentiment_row_kept_with_dir_zero():
    duck = FakeDuck(
        _sentiment("AAA", "2026-07-31 10:00:00", sentiment="neutral"),
        {"AAA": _prices([("2026-07-31", 100.0), ("2026-08-03", 110.0)])},
    )
    pairs = sbt.get_sentiment_price_pairs(duck)
    assert len(pairs) == 1
    assert pairs.iloc[0]["sentiment_dir"] == 0
    assert bool(pairs.iloc[0]["match"]) is False


def test_stale_baseline_rejected_when_bars_far_apart():
    """Outcome > MAX_PAIR_GAP_DAYS after baseline -> pair dropped (line 111)."""
    duck = FakeDuck(
        _sentiment("AAA", "2026-07-31 10:00:00"),
        {"AAA": _prices([("2026-07-20", 100.0), ("2026-07-21", 101.0), ("2026-08-01", 105.0)])},
    )
    assert len(sbt.get_sentiment_price_pairs(duck)) == 0


def test_fallback_anchor_too_far_from_sentiment_rejected():
    """Price history starts weeks after sentiment -> fallback pair rejected (line 105)."""
    duck = FakeDuck(
        _sentiment("AAA", "2026-07-25 10:00:00"),
        {"AAA": _prices([("2026-08-05", 100.0), ("2026-08-06", 102.0)])},
    )
    assert len(sbt.get_sentiment_price_pairs(duck)) == 0


def test_fallback_first_two_prices_within_gap_accepted():
    """No price on/before sentiment date -> first two bars used when anchored inside gap."""
    duck = FakeDuck(
        _sentiment("AAA", "2026-07-25 10:00:00"),
        {"AAA": _prices([("2026-07-26", 100.0), ("2026-07-27", 102.0)])},
    )
    pairs = sbt.get_sentiment_price_pairs(duck)
    assert len(pairs) == 1
    assert pairs.iloc[0]["price_return"] == pytest.approx(0.02)
    assert bool(pairs.iloc[0]["match"]) is True


def test_multi_ticker_split_creates_pair_per_ticker():
    duck = FakeDuck(
        _sentiment("AAA,BBB", "2026-07-31 10:00:00"),
        {
            "AAA": _prices([("2026-07-31", 100.0), ("2026-08-03", 110.0)]),
            "BBB": _prices([("2026-07-31", 50.0), ("2026-08-03", 40.0)]),
        },
    )
    pairs = sbt.get_sentiment_price_pairs(duck)
    assert len(pairs) == 2
    assert sorted(pairs["price_return"].tolist()) == pytest.approx([-0.2, 0.1])


# ------------------------------------------------------------- compute_hit_rate
def test_compute_hit_rate_empty_returns_error():
    assert sbt.compute_hit_rate(pd.DataFrame()) == {"error": "No pairs"}


def test_compute_hit_rate_too_few_non_neutral_returns_error():
    rows = [{"sentiment_dir": 1, "match": True, "price_return": 0.01} for _ in range(9)]
    rows += [{"sentiment_dir": 0, "match": False, "price_return": 0.0} for _ in range(3)]
    stats = sbt.compute_hit_rate(pd.DataFrame(rows))
    assert "error" in stats
    assert "Too few non-neutral pairs: 9" in stats["error"]


def test_compute_hit_rate_perfect_direction():
    rows = [{"sentiment_dir": 1, "match": True, "price_return": 0.01} for _ in range(6)]
    rows += [{"sentiment_dir": -1, "match": True, "price_return": -0.01} for _ in range(6)]
    rows += [{"sentiment_dir": 0, "match": False, "price_return": 0.0} for _ in range(4)]
    stats = sbt.compute_hit_rate(pd.DataFrame(rows))
    assert "error" not in stats
    assert stats["total_pairs"] == 16
    assert stats["non_neutral_pairs"] == 12
    assert stats["hits"] == 12
    assert stats["hit_rate"] == 1.0
    assert stats["meets_hit_rate"] is True
    assert stats["significant_uncorrected"] is True
    assert stats["significant_bonferroni"] is False


def test_compute_hit_rate_coin_flip_not_significant():
    rows = [{"sentiment_dir": 1, "match": True, "price_return": 0.01} for _ in range(5)]
    rows += [{"sentiment_dir": 1, "match": False, "price_return": -0.01} for _ in range(5)]
    stats = sbt.compute_hit_rate(pd.DataFrame(rows))
    assert stats["hit_rate"] == 0.5
    assert stats["z_score"] == 0.0
    assert stats["p_value"] == 1.0
    assert stats["significant_uncorrected"] is False
    assert stats["meets_hit_rate"] is False


# ------------------------------------------------------------- build_deviations
def test_build_deviations_clean_compliant_run():
    assert sbt.build_deviations(MIN_PAIRS, {"total_pairs": MIN_PAIRS}) == []


def test_build_deviations_pair_deficit():
    devs = sbt.build_deviations(65, {"total_pairs": 65})
    assert len(devs) == 1
    assert "65" in devs[0]
    assert str(MIN_PAIRS) in devs[0]


def test_build_deviations_uses_pair_count_not_stats():
    # compute_hit_rate error dicts have no "total_pairs" key — must not crash
    # or misreport "0 pairs" when the actual count is 65.
    devs = sbt.build_deviations(65, {"error": "Too few non-neutral pairs: 8"})
    assert any("65" in d for d in devs)
    assert any("Too few non-neutral pairs: 8" in d for d in devs)


def test_build_deviations_empty_df_error_path():
    devs = sbt.build_deviations(0, {"error": "No pairs"})
    assert len(devs) == 2  # deficit + error


# ------------------------------------------------------------- report smoke
def test_generate_report_smoke_with_real_pair_shape():
    duck = FakeDuck(
        _sentiment("AAA,BBB", "2026-07-31 10:00:00"),
        {
            "AAA": _prices([("2026-07-31", 100.0), ("2026-08-03", 110.0)]),
            "BBB": _prices([("2026-07-31", 100.0), ("2026-08-03", 90.0)]),
        },
    )
    pairs = sbt.get_sentiment_price_pairs(duck)
    assert len(pairs) == 2
    stats = sbt.compute_hit_rate(pairs)
    report = sbt.generate_report(pairs, stats)
    assert "Trial #1031" in report
    assert len(report) > 100
