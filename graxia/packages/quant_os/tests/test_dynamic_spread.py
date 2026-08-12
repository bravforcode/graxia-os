"""Test dynamic spread model."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from backtest.dynamic_spread_model import SpreadConfig


def test_spread_by_session():
    """Spread should vary by trading session."""
    config = SpreadConfig()

    # Asian session (0-6 UTC) — widest
    asian = config.get_spread(3)
    assert asian >= config.london_spread, f"Asian spread {asian} should be >= London {config.london_spread}"

    # London/NY overlap (13-16 UTC) — tightest
    overlap = config.get_spread(14)
    assert overlap <= config.london_spread, f"Overlap spread {overlap} should be <= London {config.london_spread}"

    # Closed hours (21-23 UTC) — widest
    closed = config.get_spread(22)
    assert closed >= config.ny_spread, f"Closed spread {closed} should be >= NY {config.ny_spread}"


def test_slippage_by_volatility():
    """Slippage should increase with volatility."""
    config = SpreadConfig()

    low_vol = config.get_slippage(12, atr=0.3)
    normal_vol = config.get_slippage(12, atr=1.0)
    high_vol = config.get_slippage(12, atr=3.0)

    assert low_vol <= normal_vol <= high_vol, \
        f"Slippage ordering wrong: low={low_vol}, normal={normal_vol}, high={high_vol}"


def test_all_sessions_covered():
    """Every hour should have a defined spread."""
    config = SpreadConfig()
    for hour in range(24):
        spread = config.get_spread(hour)
        assert spread > 0, f"Hour {hour} has non-positive spread: {spread}"


if __name__ == "__main__":
    test_spread_by_session()
    print("PASS: spread by session")
    test_slippage_by_volatility()
    print("PASS: slippage by volatility")
    test_all_sessions_covered()
    print("PASS: all sessions covered")
    print("All dynamic spread tests passed!")
