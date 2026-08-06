# tests/test_triage.py
import json
from pathlib import Path

from research.triage import ROUND_TRIP_BPS, cost_viability, shortlist

CAL = json.loads((Path(__file__).resolve().parents[1] / "config" / "cost_calibration.json").read_text(encoding="utf-8"))


def _e(mechanism="trend_following", symbol="XAUUSD", timeframe="H1", tier="literature", martingale=False):
    return {
        "name": "x",
        "source_url": "https://example.com/x",
        "mechanism": mechanism,
        "symbol": symbol,
        "timeframe": timeframe,
        "params": {},
        "claimed_perf": "c",
        "evidence_tier": tier,
        "mechanism_family": mechanism,
        "requires_martingale_gate": martingale,
    }


def test_round_trip_calibrated_symbol():
    # XAUUSD is FROM_TICKS calibrated — value must be a positive float
    assert ROUND_TRIP_BPS("XAUUSD") > 0


def test_round_trip_proxy_for_uncalibrated():
    # NAS100 is UNVERIFIED_NO_DATA — proxy must be positive (worst calibrated ×1.5)
    assert ROUND_TRIP_BPS("NAS100") > 0


def test_cost_viability_rejects_fast_scalp_on_btc():
    r = cost_viability(_e("scalper", symbol="BTCUSD", timeframe="M1"), trades_per_day=100)
    assert r["viable"] is False
    assert "cost" in r["reason"].lower()


def test_cost_viability_accepts_slow_trend():
    r = cost_viability(_e("trend_following", symbol="XAUUSD", timeframe="D1"), trades_per_day=0.5)
    assert r["viable"] is True


def test_shortlist_sorts_literature_first_and_marks_triage():
    entries = [_e(tier="practitioner"), _e(tier="literature")]
    out = shortlist(entries)
    assert out[0]["evidence_tier"] == "literature"
    assert all("triage" in e for e in out)


def test_shortlist_excludes_martingale_without_gate_pass():
    entries = [_e(martingale=True)]
    out = shortlist(entries)
    assert out == []  # martingale requires hard gate; no gate pass recorded -> excluded
