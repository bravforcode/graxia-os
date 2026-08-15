# tests/test_taxonomy.py
from research.taxonomy import (
    MECHANISM_FAMILIES,
    classify_mechanism,
    dedup_to_canonical,
    fingerprint,
)


def _e(mechanism, symbol="XAUUSD", timeframe="H1", params=None):
    return {
        "name": "x",
        "source": "mql5",
        "source_url": "https://example.com/x",
        "mechanism": mechanism,
        "symbol": symbol,
        "timeframe": timeframe,
        "params": params or {},
        "claimed_perf": "c",
        "evidence_tier": "practitioner",
        "partition": {"status": "FREE", "owner": None, "note": ""},
    }


def test_classify_known_family():
    assert classify_mechanism(_e("grid_martingale")) in MECHANISM_FAMILIES


def test_classify_normalizes_spelling():
    assert classify_mechanism(_e("Grid Martingale")) == classify_mechanism(_e("grid_martingale"))


def test_fingerprint_distinct_for_symbol_and_params():
    a = fingerprint(_e("trend_following", symbol="EURUSD", params={"ma": 200}))
    b = fingerprint(_e("trend_following", symbol="EURUSD", params={"ma": 100}))
    assert a != b


def test_dedup_excludes_partition_closed():
    entries = [
        _e("trend_continuity", symbol="USDCAD", timeframe="H1"),  # partition CLOSED (H 9001)
        _e("trend_following", symbol="XAUUSD"),
    ]
    canon = dedup_to_canonical(entries)
    assert all(e["name"] != "x" or e["symbol"] != "USDCAD" for e in canon)
    assert len(canon) == 1


def test_dedup_flags_martingale():
    entries = [_e("grid_martingale")]
    canon = dedup_to_canonical(entries)
    assert canon[0]["requires_martingale_gate"] is True


def test_dedup_collapses_duplicates():
    entries = [_e("breakout", symbol="EURUSD", timeframe="H4"), _e("breakout", symbol="EURUSD", timeframe="H4")]
    assert len(dedup_to_canonical(entries)) == 1
