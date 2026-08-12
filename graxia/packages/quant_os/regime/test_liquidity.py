"""Tests for Liquidity Map."""
import sys, random
sys.path.insert(0, r'C:\Users\menum\graxia os')

from datetime import datetime, timedelta
from graxia.packages.quant_os.regime.liquidity_map import LiquidityMap, get_session, hour_ict


def make_bars(bars=300, start=datetime(2026, 6, 24, 0, 0), cycle_bars=60):
    """Generate OHLCV bars with daily cycle."""
    data = []
    price = 1.0850
    for i in range(bars):
        t = start + timedelta(hours=i * 0.25)  # M15 bars
        # Daily cycle: up in London, down in NY
        h = (t.hour + 7) % 24  # ICT
        if 8 <= h < 16:  # London session
            drift = 0.0001
        elif h >= 20 or h < 4:  # NY session
            drift = -0.0001
        else:
            drift = 0.0  # Asian session
        price += drift + random.gauss(0, 0.0005)
        high = price + abs(random.gauss(0, 0.0003))
        low = price - abs(random.gauss(0, 0.0003))
        data.append({"time": t, "open": price, "high": high, "low": low, "close": price})
    return data


def test_session_detection():
    """Verify session detection logic."""
    # 2026-06-24 12:00 UTC = 19:00 ICT = London session
    t = datetime(2026, 6, 24, 12, 0)
    assert hour_ict(t) == 19, f"Expected 19, got {hour_ict(t)}"
    assert get_session(t) == "LONDON", f"Expected LONDON, got {get_session(t)}"

    # 2026-06-24 01:00 UTC = 08:00 ICT = Asian session
    t = datetime(2026, 6, 24, 1, 0)
    assert hour_ict(t) == 8, f"Expected 8, got {hour_ict(t)}"
    assert get_session(t) == "ASIAN", f"Expected ASIAN, got {get_session(t)}"

    # 2026-06-24 18:00 UTC = 01:00 ICT = NY session
    t = datetime(2026, 6, 24, 18, 0)
    assert hour_ict(t) == 1, f"Expected 1, got {hour_ict(t)}"
    assert get_session(t) == "NY", f"Expected NY, got {get_session(t)}"
    print("  [OK] Session detection")


def test_build_has_levels():
    """Liquidity map should produce levels."""
    bars = make_bars(300)
    lm = LiquidityMap(bars)
    levels = lm.build()
    assert len(levels) > 0, "No levels generated"
    print(f"  [OK] Generated {len(levels)} levels")


def test_session_levels():
    """Should have Asian/London/NY session levels."""
    bars = make_bars(300)
    lm = LiquidityMap(bars)
    levels = lm.build()
    types = set(l.level_type for l in levels)
    assert "ASIAN_H" in types, "Missing ASIAN_H"
    assert "LONDON_H" in types, "Missing LONDON_H"
    assert "NY_H" in types, "Missing NY_H"
    print(f"  [OK] Session types: {sorted(types)[:6]}")


def test_swing_levels():
    """Should have swing highs/lows."""
    bars = make_bars(300)
    lm = LiquidityMap(bars)
    levels = lm.build()
    swing_types = {l.level_type for l in levels if "SWING" in l.level_type}
    assert "SWING_H" in swing_types, "Missing SWING_H"
    assert "SWING_L" in swing_types, "Missing SWING_L"
    print(f"  [OK] Swing levels: {len(swing_types)} types")


def test_round_numbers():
    """Should have round number levels."""
    bars = make_bars(300)
    lm = LiquidityMap(bars)
    levels = lm.build()
    round_levels = [l for l in levels if l.level_type == "ROUND"]
    assert len(round_levels) > 0, "No round number levels"
    print(f"  [OK] Round numbers: {len(round_levels)} levels")


def test_insufficient_data():
    """Fewer than 10 bars should return empty."""
    bars = make_bars(5)
    lm = LiquidityMap(bars)
    levels = lm.build()
    assert len(levels) == 0, "Should return empty for <10 bars"
    print("  [OK] Insufficient data -> empty")


def test_no_duplicate_type():
    """Each level type should appear at most a reasonable number of times."""
    bars = make_bars(300)
    lm = LiquidityMap(bars)
    levels = lm.build()
    type_counts = {}
    for l in levels:
        type_counts[l.level_type] = type_counts.get(l.level_type, 0) + 1
    # Session levels should appear once each
    for sess_type in ["ASIAN_H", "ASIAN_L", "LONDON_H", "LONDON_L", "NY_H", "NY_L"]:
        if sess_type in type_counts:
            assert type_counts[sess_type] == 1, f"{sess_type} appears {type_counts[sess_type]} times"
    print("  [OK] No duplicate session levels")


def test_scoring_range():
    """Strength scores should be in 0-1 range."""
    bars = make_bars(300)
    lm = LiquidityMap(bars)
    levels = lm.build()
    for l in levels:
        assert 0 <= l.strength_score <= 1, f"Score out of range: {l.strength_score}"
        assert 0 <= l.freshness_score <= 1, f"Freshness out of range: {l.freshness_score}"
    print("  [OK] All scores in 0-1 range")


def test_deterministic():
    """Same input should produce same output."""
    random.seed(42)
    bars1 = make_bars(100)
    lm1 = LiquidityMap(bars1)
    l1 = [(l.level_type, round(l.price, 5)) for l in lm1.build()]

    random.seed(42)
    bars2 = make_bars(100)
    lm2 = LiquidityMap(bars2)
    l2 = [(l.level_type, round(l.price, 5)) for l in lm2.build()]

    assert l1 == l2, "Not deterministic"
    print("  [OK] Deterministic output")


if __name__ == "__main__":
    print("=== Liquidity Map Tests ===\n")
    test_session_detection()
    test_build_has_levels()
    test_session_levels()
    test_swing_levels()
    test_round_numbers()
    test_insufficient_data()
    test_no_duplicate_type()
    test_scoring_range()
    test_deterministic()
    print("\n=== All tests passed ===")
