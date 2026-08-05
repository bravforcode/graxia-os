"""Tests for market_data/stream_collector.py — delta-stream core:
bounded dedup (same-ms ticks), catch-up loop (batch overflow), no-op on
quiet markets. Pure — fake fetch callables only, no MT5."""

from __future__ import annotations

from market_data.stream_collector import StreamCollector


def _t(msc, bid=1.0, ask=2.0, last=1.5, vol=1.0):
    return {"time_msc": msc, "bid": bid, "ask": ask, "last": last, "volume": vol, "flags": 0}


def test_bounded_dedup_same_ms_ticks():
    """Ticks sharing time_msc (volatility) must all pass once, none twice."""
    served = {"n": 0}

    def fetch(symbol, from_msc):
        served["n"] += 1
        if served["n"] == 1:
            return [_t(1000, bid=1.0), _t(1000, bid=1.1), _t(1001, bid=1.2)]  # two ticks same ms
        if served["n"] == 2:
            return [_t(1001, bid=1.2)]  # boundary repeat only — no new data yet
        return [_t(1001, bid=1.2), _t(1002, bid=1.3)]  # boundary + new tick

    c = StreamCollector(["XAUUSD"], fetch)
    first = c.poll("XAUUSD")
    second = c.poll("XAUUSD")
    assert len(first) == 3
    assert len(second) == 1  # only the new tick; boundary dup dropped
    assert second[0]["time_msc"] == 1002
    assert c.cursor("XAUUSD") == 1002


def test_catch_up_loop_until_caught_up():
    """fetch returns a full batch twice, then a short batch — must loop, not drop."""
    batches = iter([
        [_t(1000), _t(1001), _t(1002)],
        [_t(1002), _t(1003), _t(1004)],
        [_t(1004), _t(1005)],
    ])

    def fetch(symbol, from_msc):
        try:
            return next(batches)
        except StopIteration:
            return []  # caught up — no more data

    c = StreamCollector(["XAUUSD"], fetch)
    out = c.poll("XAUUSD")
    mscs = [t["time_msc"] for t in out]
    assert mscs == [1000, 1001, 1002, 1003, 1004, 1005]
    assert c.cursor("XAUUSD") == 1005


def test_no_ticks_is_noop():
    c = StreamCollector(["XAUUSD"], lambda s, f: [])
    assert c.poll("XAUUSD") == []
    assert c.cursor("XAUUSD") == 0


def test_catch_up_cap_stops_runaway():
    """Safety cap bounds the loop when the provider never catches up."""
    served = {"n": 0}

    def fetch(symbol, from_msc):
        served["n"] += 1
        return [_t(1000 + served["n"])]  # always one new tick — never catches up

    c = StreamCollector(["XAUUSD"], fetch, catch_up_cap=3)
    out = c.poll("XAUUSD")
    assert served["n"] == 3  # capped at 3 fetches
    assert len(out) == 3
