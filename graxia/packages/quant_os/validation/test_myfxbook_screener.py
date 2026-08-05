"""
Tests for the Myfxbook red-flag screener.

Run from the monorepo root (so ``graxia.packages.quant_os`` resolves) or run
this file directly as a script:

    python -m pytest graxia/packages/quant_os/validation/test_myfxbook_screener.py -q
    python graxia/packages/quant_os/validation/test_myfxbook_screener.py   # standalone
"""

from __future__ import annotations

import importlib.util
import os
import sys

# Import the sibling module either as a package member (under pytest) or by
# file path (standalone). Loading by path avoids pulling in the heavy
# validation/__init__.py dependency chain for a self-contained unit test.
try:
    from .myfxbook_screener import (  # type: ignore[attr-defined]
        MyfxbookStats,
        Verdict,
        _example_superbreakout,
        _parse_leverage_frac,
        _parse_trade_length_seconds,
        generate_batch_table,
        screen,
    )
except ImportError:
    _here = os.path.dirname(os.path.abspath(__file__))
    _spec = importlib.util.spec_from_file_location("myfxbook_screener", os.path.join(_here, "myfxbook_screener.py"))
    _mod = importlib.util.module_from_spec(_spec)  # type: ignore[union-attr,arg-type,misc]
    sys.modules["myfxbook_screener"] = _mod  # dataclasses needs the module registered
    _spec.loader.exec_module(_mod)  # type: ignore[union-attr,misc]
    MyfxbookStats = _mod.MyfxbookStats  # type: ignore[assignment,misc]
    Verdict = _mod.Verdict  # type: ignore[assignment,misc]
    _example_superbreakout = _mod._example_superbreakout  # type: ignore[assignment,misc]
    _parse_leverage_frac = _mod._parse_leverage_frac  # type: ignore[assignment,misc]
    _parse_trade_length_seconds = _mod._parse_trade_length_seconds  # type: ignore[assignment,misc]
    generate_batch_table = _mod.generate_batch_table  # type: ignore[assignment,misc]
    screen = _mod.screen  # type: ignore[assignment,misc]


def test_parse_leverage_frac() -> None:
    assert _parse_leverage_frac("1:2000") == 2000.0
    assert _parse_leverage_frac("1:500") == 500.0
    assert _parse_leverage_frac("") == 0.0
    assert _parse_leverage_frac("1:100") == 100.0


def test_parse_trade_length_seconds() -> None:
    assert _parse_trade_length_seconds("15s") == 15.0
    assert _parse_trade_length_seconds("16h") == 57600.0
    assert _parse_trade_length_seconds("2d") == 172800.0
    assert _parse_trade_length_seconds("") is None
    assert _parse_trade_length_seconds("30m") == 1800.0


def test_example_superbreakout_fails() -> None:
    """The verified Pisansri account must FAIL and surface the key red flags."""
    result = screen(_example_superbreakout())
    assert result.verdict == Verdict.FAIL
    codes = {f.code for f in result.flags}
    assert "TIMEFRAME_CONTRADICTION" in codes  # H1 name vs 15s trades
    assert "LEVERAGE_HIGH" in codes  # 1:2000
    assert "DD_HIGH" in codes  # 40.28%
    assert "AGE_SHORT" in codes  # 60 days
    assert "GAIN_ABS_DIVERGENCE" in codes  # 21.3x ratio


def test_clean_account_passes() -> None:
    """A sane, long-lived real account should not raise red flags."""
    stats = MyfxbookStats(
        account_name="Clean Trend",
        broker="Regulated Broker",
        account_type="Real (USD)",
        leverage="1:30",
        claimed_timeframe="H1",
        gain_pct=45.0,
        abs_gain_pct=42.0,
        drawdown_pct=12.0,
        trades=420,
        avg_win_pips=35.0,
        avg_loss_pips=-22.0,
        lots=0.5,
        longs_won=120,
        longs_total=200,
        shorts_won=130,
        shorts_total=220,
        avg_trade_length="4h",
        profit_factor=1.6,
        sharpe=1.4,
        age_days=540,
    )
    result = screen(stats)
    assert result.verdict == Verdict.PASS
    assert result.flags == []


def test_gain_abs_divergence_detected() -> None:
    stats = MyfxbookStats(gain_pct=900.0, abs_gain_pct=50.0, drawdown_pct=10.0, trades=200, age_days=400)
    result = screen(stats)
    assert any(f.code == "GAIN_ABS_DIVERGENCE" for f in result.flags)


def test_timeframe_contradiction_critical() -> None:
    stats = MyfxbookStats(claimed_timeframe="H1", avg_trade_length="15s", drawdown_pct=10.0, trades=200, age_days=400)
    result = screen(stats)
    flag = next(f for f in result.flags if f.code == "TIMEFRAME_CONTRADICTION")
    assert flag.severity.value == "CRITICAL"


def test_win_small_lose_big() -> None:
    stats = MyfxbookStats(
        longs_won=70,
        longs_total=100,
        shorts_won=70,
        shorts_total=100,
        avg_win_pips=10.0,
        avg_loss_pips=-40.0,
        drawdown_pct=10.0,
        trades=200,
        age_days=400,
    )
    result = screen(stats)
    assert any(f.code == "WIN_SMALL_LOSE_BIG" for f in result.flags)


def test_demo_account_flagged() -> None:
    stats = MyfxbookStats(account_type="Demo", drawdown_pct=10.0, trades=200, age_days=400)
    result = screen(stats)
    assert any(f.code == "DEMO_ACCOUNT" for f in result.flags)


def test_batch_table_runs() -> None:
    results = [screen(_example_superbreakout()), screen(MyfxbookStats(trades=200, age_days=400, drawdown_pct=10.0))]
    table = generate_batch_table(results)
    assert "SuperBreakout H1 5" in table
    assert "FAIL" in table
    assert "PASS" in table


def test_require_provenance_raises_without_attribution() -> None:
    """CLI path must refuse unattributed numbers (doc-13 lesson)."""
    stats = MyfxbookStats(trades=200, age_days=400, drawdown_pct=10.0)
    try:
        screen(stats, require_provenance=True)
        raise AssertionError("expected ValueError")
    except ValueError:
        pass


def test_stale_data_warns() -> None:
    """A fetch older than stale_hours should warn, not pass silently."""
    stats = MyfxbookStats(
        account_name="Old Snapshot",
        claimed_timeframe="H1",
        avg_trade_length="4h",
        trades=420,
        age_days=540,
        drawdown_pct=12.0,
        source_url="https://www.myfxbook.com/members/Someone/old/1",
        fetched_at="2000-01-01",  # far in the past -> stale
    )
    result = screen(stats)
    assert any("old" in w for w in result.warnings)


if __name__ == "__main__":
    # Minimal standalone runner (no pytest dependency required).
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    failed = 0
    for t in tests:
        try:
            t()
            print(f"PASS {t.__name__}")
        except Exception as exc:  # noqa: BLE001
            failed += 1
            print(f"FAIL {t.__name__}: {exc}")
    print(f"\n{failed} failed of {len(tests)}")
    raise SystemExit(1 if failed else 0)
