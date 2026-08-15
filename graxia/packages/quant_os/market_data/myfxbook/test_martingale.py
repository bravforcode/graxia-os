"""Martingale/blow-up detector tests — synthetic curves only."""

import pytest

from market_data.myfxbook import martingale
from market_data.myfxbook.models import EquityPoint, TradeRecord


def _equity(values: list[float], account_id: int = 1) -> list[EquityPoint]:
    return [EquityPoint(account_id=account_id, month=f"2026-{i + 1:02d}", equity=v) for i, v in enumerate(values)]


def test_organic_growth_not_flagged() -> None:
    curve = _equity([100 + i * 3 for i in range(24)])  # steady linear growth
    verdict = martingale.detect_martingale(curve)
    assert verdict.risky is False


def test_tail_crash_flagged() -> None:
    curve = _equity(
        [100, 110, 130, 150, 170, 190, 210, 230, 250, 260, 265, 268, 270, 265, 250, 230, 210, 190, 170, 150]
    )
    verdict = martingale.detect_martingale(curve)
    assert verdict.risky is True
    assert any("tail drawdown" in s for s in verdict.signals)


def test_empty_equity_is_not_risky() -> None:
    verdict = martingale.detect_martingale([])
    assert verdict.risky is False
    assert verdict.signals == ["insufficient equity data"]


def test_lot_doubling_detected() -> None:
    trades = [
        TradeRecord(
            account_id=1,
            trade_id="a",
            open_time="t",
            close_time="t",
            symbol="XAUUSD",
            direction="long",
            lots=0.1,
            entry=1.0,
            exit=1.1,
            pnl=1.0,
        ),
        TradeRecord(
            account_id=1,
            trade_id="b",
            open_time="t",
            close_time="t",
            symbol="XAUUSD",
            direction="long",
            lots=0.2,
            entry=1.0,
            exit=0.9,
            pnl=-1.0,
        ),
        TradeRecord(
            account_id=1,
            trade_id="c",
            open_time="t",
            close_time="t",
            symbol="XAUUSD",
            direction="long",
            lots=0.4,
            entry=1.0,
            exit=1.1,
            pnl=2.0,
        ),
    ]
    signals = martingale.lot_doubling_signals(trades)
    assert len(signals) == 2
    assert all("lot doubling XAUUSD" in s for s in signals)


def test_quadratic_fit_exact_parabola() -> None:
    n = 20
    values = [0.5 * (i - 9.5) ** 2 + 100.0 for i in range(n)]
    fit = martingale._quadratic_fit(values)
    assert fit is not None
    a, b, c, r2 = fit
    assert a == pytest.approx(0.5, abs=1e-9)
    assert b == pytest.approx(0.0, abs=1e-9)
    assert c == pytest.approx(100.0, abs=1e-9)
    assert r2 == pytest.approx(1.0, abs=1e-9)


def test_quadratic_fit_shifted_parabola() -> None:
    # (x-3)^2 = z^2 + 13z + 42.25 — requires the linear term for R2 = 1
    values = [(i - 3) ** 2 + 100.0 for i in range(20)]
    fit = martingale._quadratic_fit(values)
    assert fit is not None
    a, b, _c, r2 = fit
    assert a == pytest.approx(1.0, abs=1e-9)
    assert b == pytest.approx(13.0, abs=1e-9)
    assert r2 == pytest.approx(1.0, abs=1e-9)


def test_quadratic_fit_linear_has_zero_curvature() -> None:
    values = [100.0 + 3.0 * i for i in range(20)]
    fit = martingale._quadratic_fit(values)
    assert fit is not None
    assert fit[0] == pytest.approx(0.0, abs=1e-9)  # a == 0 -> not parabolic
    assert fit[3] == pytest.approx(1.0, abs=1e-9)  # perfect linear fit


def test_parabolic_signal_fires_on_x2_curve_with_tail() -> None:
    # x^2-shaped (not z^2-centered) + tail crash — FAILS with a z^2-only model
    n = 20
    values = [0.5 * (i - 9.5) ** 2 + 100.0 for i in range(n)]
    values[16:] = [110.0, 100.0, 90.0, 80.0]  # tail crash: 115.1 peak -> 80 = 30.5% DD
    verdict = martingale.detect_martingale(_equity(values))
    assert any("parabolic" in s for s in verdict.signals)
