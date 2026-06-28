import pytest


KELLY_CAP = 0.25


class PositionSizer:
    def __init__(self, target_vol: float = 0.10, kelly_cap: float = KELLY_CAP):
        self.target_vol = target_vol
        self.kelly_cap = kelly_cap

    def size_by_volatility(self, realized_vol: float, price: float) -> float:
        if realized_vol <= 0 or price <= 0:
            return 0.0
        notional_pct = self.target_vol / realized_vol
        return round(notional_pct, 6)

    def size_by_kelly(self, win_rate: float, avg_win: float, avg_loss: float) -> float:
        if avg_loss == 0:
            return 0.0
        b = avg_win / abs(avg_loss)
        kelly = (win_rate * b - (1 - win_rate)) / b
        capped = max(0.0, min(kelly, self.kelly_cap))
        return round(capped, 6)

    def apply_regime_multiplier(self, base_size: float, regime: str) -> float:
        multipliers = {
            "trending": 1.2,
            "ranging": 0.8,
            "volatile": 0.5,
            "unknown": 0.6,
        }
        mult = multipliers.get(regime, 0.6)
        return round(base_size * mult, 6)


@pytest.fixture
def sizer():
    return PositionSizer(target_vol=0.10, kelly_cap=KELLY_CAP)


class TestVolatilityTargeting:
    def test_low_vol_larger_size(self, sizer):
        size = sizer.size_by_volatility(realized_vol=0.05, price=2400.0)
        assert size == 2.0

    def test_high_vol_smaller_size(self, sizer):
        size = sizer.size_by_volatility(realized_vol=0.20, price=2400.0)
        assert size == 0.5

    def test_zero_vol_returns_zero(self, sizer):
        assert sizer.size_by_volatility(0.0, 2400.0) == 0.0


class TestRegimeMultiplier:
    def test_trending_boosts_size(self, sizer):
        result = sizer.apply_regime_multiplier(1.0, "trending")
        assert result == 1.2

    def test_volatile_reduces_size(self, sizer):
        result = sizer.apply_regime_multiplier(1.0, "volatile")
        assert result == 0.5

    def test_unknown_defaults_to_06(self, sizer):
        result = sizer.apply_regime_multiplier(1.0, "unknown")
        assert result == 0.6


class TestKellyCap:
    def test_high_edge_capped_at_025(self, sizer):
        kelly = sizer.size_by_kelly(win_rate=0.8, avg_win=3.0, avg_loss=1.0)
        assert kelly == KELLY_CAP

    def test_low_edge_below_cap(self, sizer):
        kelly = sizer.size_by_kelly(win_rate=0.5, avg_win=1.5, avg_loss=1.0)
        assert kelly < KELLY_CAP
        assert kelly > 0.0

    def test_negative_edge_returns_zero(self, sizer):
        kelly = sizer.size_by_kelly(win_rate=0.3, avg_win=1.0, avg_loss=1.0)
        assert kelly == 0.0
