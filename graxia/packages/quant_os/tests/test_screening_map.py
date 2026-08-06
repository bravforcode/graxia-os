# tests/test_screening_map.py
from research.screening_map import DEFAULT_TF_BY_FAMILY, FAMILY_TO_STRATEGY, resolve_candidate


def _entry(family, symbol="XAUUSD", timeframe="D1", params=None):
    return {"name": "x", "mechanism_family": family, "symbol": symbol, "timeframe": timeframe, "params": params or {}}


def test_required_families_mapped():
    # the families present in the wave-1/2 shortlist must all be handled
    for family in [
        "trend_following",
        "breakout",
        "scalper",
        "mean_reversion",
        "momentum",
        "session",
        "orderflow",
        "carry",
        "vol_targeting",
        "regime",
        "other",
    ]:
        assert family in FAMILY_TO_STRATEGY or family in ("other", "microstructure", "seasonality")


def test_default_tf_all_families_defined():
    for family in FAMILY_TO_STRATEGY:
        assert DEFAULT_TF_BY_FAMILY[family] in {"M1", "M5", "M15", "M30", "H1", "H4", "D1", "W1", "MN1"}


def test_resolve_trend_following():
    r = resolve_candidate(_entry("trend_following"))
    assert r["status"] == "ok"
    assert r["strategy_class"].__name__ == "DonchianBreakout"
    assert r["timeframe"] == "D1"


def test_resolve_all_timeframe_uses_family_default():
    r = resolve_candidate(_entry("scalper", timeframe="ALL"))
    assert r["timeframe"] == DEFAULT_TF_BY_FAMILY["scalper"]


def test_resolve_unmapped_family_no_strategy():
    r = resolve_candidate(_entry("other"))
    assert r["status"] == "no_strategy"


def test_params_default_merge():
    r = resolve_candidate(_entry("trend_following", params={"period": 30}))
    assert r["params"]["period"] == 30  # entry param wins
    assert "atr_period" in r["params"]  # defaults present
