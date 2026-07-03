"""Phase 3.1A — Deterministic E2E fixture with 12 scenarios.

Each scenario returns (BacktestConfig, list[bar_dicts], list[timestamps], expected).
No MT5, no external deps, no CSV files.
"""

from dataclasses import dataclass
from datetime import datetime, timedelta
from decimal import Decimal

from ..core.enums import SignalType
from ..strategies.base import Signal
from .engine import BacktestConfig


@dataclass
class ScenarioExpected:
    trade_count: int
    entry_bar_index: int  # signal at t, entry at t+1
    side: str  # "LONG" or "SHORT"
    sl_triggered: bool
    tp_triggered: bool
    ambiguous: bool
    overnight_hold: bool
    critical_incident: bool
    rejected: bool
    cost_scenario: str
    state_terminal: str  # "AUDITED" or "CRITICAL_INCIDENT"


def _make_bars(prices: list[float], spread: float = 0.02):
    """Generate bars from a price list."""
    bars = []
    for p in prices:
        bars.append(
            {
                "open": Decimal(str(p)),
                "high": Decimal(str(p + spread * 2)),
                "low": Decimal(str(p - spread * 2)),
                "close": Decimal(str(p + spread * 0.3)),
                "volume": [1000],
            }
        )
    return bars


def _make_timestamps(n: int, start: datetime = None) -> list[datetime]:
    """Generate hourly timestamps starting from 2025-01-06 00:00 UTC."""
    if start is None:
        start = datetime(2025, 1, 6, 0, 0, 0)
    return [start + timedelta(hours=i) for i in range(n)]


class DeterministicStrategy:
    """Strategy that returns signals from a queue."""

    def __init__(self, signals):
        self.id = "deterministic"
        self._signals = list(signals)
        self._idx = 0

    def generate_signal(self, symbol, ohlcv_data, indicators, regime, current_time, **kwargs):
        if self._idx < len(self._signals):
            sig = self._signals[self._idx]
            self._idx += 1
            return sig
        return None


def _base_config(**overrides) -> BacktestConfig:
    defaults = dict(
        initial_capital=Decimal("10000"),
        slippage_pips=0.5,
        commission_per_lot=Decimal("3.5"),
        max_positions=5,
        risk_per_trade_bps=10,
        strict_mtf=False,
        enable_swap=False,
    )
    defaults.update(overrides)
    return BacktestConfig(**defaults)


def _sig(signal_type, stop_loss=None, take_profit=None, entry_price=None, symbol="EURUSD", timestamp=None):
    return Signal(
        id="test_signal",
        strategy_id="deterministic",
        symbol=symbol,
        signal_type=signal_type,
        timestamp=timestamp or datetime(2025, 1, 6, 5, 0, 0),
        entry_price=Decimal(str(entry_price)) if entry_price else None,
        stop_loss=Decimal(str(stop_loss)) if stop_loss else None,
        take_profit=Decimal(str(take_profit)) if take_profit else None,
    )


# ── Scenario 1 ────────────────────────────────────────────────────────
def scenario_long_entry_sl_only():
    """Signal at bar 5, long entry at bar 6 open, SL hit on bar 8."""
    # 12 bars: bars 0-4 = warmup, signal at bar 5, entry bar 6, SL bar 8
    prices = [
        1.1000,
        1.1010,
        1.1020,
        1.1030,
        1.1040,
        1.1050,  # bar 5: signal here
        1.1060,  # bar 6: entry at open
        1.1070,  # bar 7: hold
        1.0980,  # bar 8: drops → SL hit
        1.1000,
        1.1010,
        1.1020,
    ]
    bars = _make_bars(prices)
    ts = _make_timestamps(len(bars))

    signal = _sig(SignalType.BUY, stop_loss=1.0990, take_profit=1.1100, entry_price=1.1060, timestamp=ts[5])
    config = _base_config()
    expected = ScenarioExpected(
        trade_count=1,
        entry_bar_index=6,
        side="LONG",
        sl_triggered=True,
        tp_triggered=False,
        ambiguous=False,
        overnight_hold=False,
        critical_incident=False,
        rejected=False,
        cost_scenario="base",
        state_terminal="AUDITED",
    )
    return config, bars, ts, [signal], expected


# ── Scenario 2 ────────────────────────────────────────────────────────
def scenario_long_entry_tp_only():
    """Signal at bar 5, long entry at bar 6 open, TP hit on bar 10."""
    prices = [
        1.1000,
        1.1010,
        1.1020,
        1.1030,
        1.1040,
        1.1050,  # bar 5: signal
        1.1060,  # bar 6: entry
        1.1080,
        1.1100,
        1.1120,
        1.1140,  # bar 10: TP hit (take_profit=1.1130)
        1.1000,
    ]
    bars = _make_bars(prices)
    ts = _make_timestamps(len(bars))

    signal = _sig(SignalType.BUY, stop_loss=1.0990, take_profit=1.1130, entry_price=1.1060, timestamp=ts[5])
    config = _base_config()
    expected = ScenarioExpected(
        trade_count=1,
        entry_bar_index=6,
        side="LONG",
        sl_triggered=False,
        tp_triggered=True,
        ambiguous=False,
        overnight_hold=False,
        critical_incident=False,
        rejected=False,
        cost_scenario="base",
        state_terminal="AUDITED",
    )
    return config, bars, ts, [signal], expected


# ── Scenario 3 ────────────────────────────────────────────────────────
def scenario_short_entry_sl_only():
    """Signal at bar 5, short entry at bar 6 open, SL hit on bar 8."""
    prices = [
        1.1050,
        1.1040,
        1.1030,
        1.1020,
        1.1010,
        1.1000,  # bar 5: signal
        1.0990,  # bar 6: entry
        1.0980,  # bar 7: hold
        1.1020,  # bar 8: rises → SL hit
        1.1050,
        1.1040,
        1.1030,
    ]
    bars = _make_bars(prices)
    ts = _make_timestamps(len(bars))

    signal = _sig(SignalType.SELL, stop_loss=1.1010, take_profit=1.0950, entry_price=1.0990, timestamp=ts[5])
    config = _base_config()
    expected = ScenarioExpected(
        trade_count=1,
        entry_bar_index=6,
        side="SHORT",
        sl_triggered=True,
        tp_triggered=False,
        ambiguous=False,
        overnight_hold=False,
        critical_incident=False,
        rejected=False,
        cost_scenario="base",
        state_terminal="AUDITED",
    )
    return config, bars, ts, [signal], expected


# ── Scenario 4 ────────────────────────────────────────────────────────
def scenario_short_entry_tp_only():
    """Signal at bar 5, short entry at bar 6 open, TP hit on bar 10."""
    prices = [
        1.1050,
        1.1040,
        1.1030,
        1.1020,
        1.1010,
        1.1000,  # bar 5: signal
        1.0990,  # bar 6: entry
        1.0970,
        1.0950,
        1.0930,
        1.0910,  # bar 10: TP hit (take_profit=1.0920)
        1.1000,
    ]
    bars = _make_bars(prices)
    ts = _make_timestamps(len(bars))

    signal = _sig(SignalType.SELL, stop_loss=1.1010, take_profit=1.0920, entry_price=1.0990, timestamp=ts[5])
    config = _base_config()
    expected = ScenarioExpected(
        trade_count=1,
        entry_bar_index=6,
        side="SHORT",
        sl_triggered=False,
        tp_triggered=True,
        ambiguous=False,
        overnight_hold=False,
        critical_incident=False,
        rejected=False,
        cost_scenario="base",
        state_terminal="AUDITED",
    )
    return config, bars, ts, [signal], expected


# ── Scenario 5 ────────────────────────────────────────────────────────
def scenario_ambiguous_bar():
    """Both SL and TP reachable on same bar → adverse-first (SL resolves first)."""
    prices = [
        1.1000,
        1.1010,
        1.1020,
        1.1030,
        1.1040,
        1.1050,  # bar 5: signal
        1.1060,  # bar 6: entry
        1.1070,  # bar 7: hold
        1.1000,  # bar 8: bar covers both SL and TP range
        1.1000,
        1.1000,
        1.1000,
    ]
    bars = _make_bars(prices)
    ts = _make_timestamps(len(bars))

    # SL=1.0990, TP=1.1080 — bar 8 low=1.0996, high=1.1044
    # With spread=0.02, high becomes 1.1044 → below TP=1.1080
    # Need bar range to actually cross both. Use a wide bar.
    prices[8] = 1.1000
    bars[8] = {
        "open": Decimal("1.1000"),
        "high": Decimal("1.1085"),  # above TP
        "low": Decimal("1.0985"),  # below SL
        "close": Decimal("1.1000"),
        "volume": [1000],
    }

    signal = _sig(SignalType.BUY, stop_loss=1.0990, take_profit=1.1080, entry_price=1.1060, timestamp=ts[5])
    config = _base_config()
    expected = ScenarioExpected(
        trade_count=1,
        entry_bar_index=6,
        side="LONG",
        sl_triggered=True,
        tp_triggered=False,
        ambiguous=True,
        overnight_hold=False,
        critical_incident=False,
        rejected=False,
        cost_scenario="base",
        state_terminal="AUDITED",
    )
    return config, bars, ts, [signal], expected


# ── Scenario 6 ────────────────────────────────────────────────────────
def scenario_overnight_hold():
    """Position crosses rollover day (Wednesday) → swap applied."""
    # Start Monday, cross into Wednesday
    start = datetime(2025, 1, 6, 0, 0, 0)  # Monday
    ts = [start + timedelta(hours=i) for i in range(50)]

    prices = [1.1000] * 50
    prices[5] = 1.1050  # bar 5: signal
    prices[6] = 1.1060  # bar 6: entry
    # Flat through Wednesday
    for i in range(7, 50):
        prices[i] = 1.1060 + (0.001 if i % 2 == 0 else -0.0005)

    bars = _make_bars(prices)
    signal = _sig(SignalType.BUY, stop_loss=1.0990, take_profit=1.1150, entry_price=1.1060, timestamp=ts[5])
    config = _base_config(enable_swap=True)
    expected = ScenarioExpected(
        trade_count=1,
        entry_bar_index=6,
        side="LONG",
        sl_triggered=False,
        tp_triggered=False,
        ambiguous=False,
        overnight_hold=True,
        critical_incident=False,
        rejected=False,
        cost_scenario="base",
        state_terminal="AUDITED",
    )
    return config, bars, ts, [signal], expected


# ── Scenario 7 ────────────────────────────────────────────────────────
def scenario_missing_sl_rejected():
    """Signal without stop_loss → CRITICAL_INCIDENT, no position opened."""
    prices = [1.1000, 1.1010, 1.1020, 1.1030, 1.1040, 1.1050, 1.1060, 1.1070, 1.1080, 1.1090, 1.1100, 1.1110]
    bars = _make_bars(prices)
    ts = _make_timestamps(len(bars))

    signal = _sig(SignalType.BUY, stop_loss=None, take_profit=1.1150, entry_price=1.1060, timestamp=ts[5])
    config = _base_config()
    expected = ScenarioExpected(
        trade_count=0,
        entry_bar_index=-1,
        side="LONG",
        sl_triggered=False,
        tp_triggered=False,
        ambiguous=False,
        overnight_hold=False,
        critical_incident=True,
        rejected=False,
        cost_scenario="base",
        state_terminal="CRITICAL_INCIDENT",
    )
    return config, bars, ts, [signal], expected


# ── Scenario 8 ────────────────────────────────────────────────────────
def scenario_invalid_sl_rejected():
    """Signal with SL above entry for LONG → rejected."""
    prices = [1.1000, 1.1010, 1.1020, 1.1030, 1.1040, 1.1050, 1.1060, 1.1070, 1.1080, 1.1090, 1.1100, 1.1110]
    bars = _make_bars(prices)
    ts = _make_timestamps(len(bars))

    # LONG with SL above entry = invalid (SL=1.1100 > entry=1.1060)
    signal = _sig(SignalType.BUY, stop_loss=1.1100, take_profit=1.1150, entry_price=1.1060, timestamp=ts[5])
    config = _base_config()
    expected = ScenarioExpected(
        trade_count=0,
        entry_bar_index=-1,
        side="LONG",
        sl_triggered=False,
        tp_triggered=False,
        ambiguous=False,
        overnight_hold=False,
        critical_incident=False,
        rejected=True,
        cost_scenario="base",
        state_terminal="AUDITED",
    )
    return config, bars, ts, [signal], expected


# ── Scenario 9 ────────────────────────────────────────────────────────
def scenario_max_risk_rejection():
    """Very tight SL with tiny equity → volume below minimum → rejected."""
    prices = [1.1000, 1.1010, 1.1020, 1.1030, 1.1040, 1.1050, 1.1060, 1.1070, 1.1080, 1.1090, 1.1100, 1.1110]
    bars = _make_bars(prices)
    ts = _make_timestamps(len(bars))

    # Tiny equity + tiny SL distance → volume rounds to 0
    signal = _sig(SignalType.BUY, stop_loss=1.1059, take_profit=1.1200, entry_price=1.1060, timestamp=ts[5])
    config = _base_config(initial_capital=Decimal("100"))  # tiny equity
    expected = ScenarioExpected(
        trade_count=0,
        entry_bar_index=-1,
        side="LONG",
        sl_triggered=False,
        tp_triggered=False,
        ambiguous=False,
        overnight_hold=False,
        critical_incident=False,
        rejected=True,
        cost_scenario="base",
        state_terminal="AUDITED",
    )
    return config, bars, ts, [signal], expected


# ── Scenario 10 ───────────────────────────────────────────────────────
def scenario_zero_volume_rejection():
    """Entry price = 0 → rejected."""
    prices = [1.1000, 1.1010, 1.1020, 1.1030, 1.1040, 1.1050, 1.1060, 1.1070, 1.1080, 1.1090, 1.1100, 1.1110]
    bars = _make_bars(prices)
    ts = _make_timestamps(len(bars))

    # entry_price=0 causes volume=0 in _historical_size
    signal = _sig(SignalType.BUY, stop_loss=1.0990, take_profit=1.1150, entry_price=0, timestamp=ts[5])
    config = _base_config()
    expected = ScenarioExpected(
        trade_count=0,
        entry_bar_index=-1,
        side="LONG",
        sl_triggered=False,
        tp_triggered=False,
        ambiguous=False,
        overnight_hold=False,
        critical_incident=False,
        rejected=True,
        cost_scenario="base",
        state_terminal="AUDITED",
    )
    return config, bars, ts, [signal], expected


# ── Scenario 11 ───────────────────────────────────────────────────────
def scenario_multi_trade():
    """3 sequential signals, all fill and close normally."""
    # Need enough bars: 3 signals at bars 5,12,19 → entries at 6,13,20
    # Each closes via SL or TP a few bars later
    n = 40
    prices = [1.1000 + i * 0.001 for i in range(n)]

    bars = _make_bars(prices)
    ts = _make_timestamps(len(bars))

    signals = [
        _sig(SignalType.BUY, stop_loss=1.0990, take_profit=1.1150, entry_price=1.1060, timestamp=ts[5]),
        _sig(SignalType.BUY, stop_loss=1.1060, take_profit=1.1220, entry_price=1.1130, timestamp=ts[12]),
        _sig(SignalType.BUY, stop_loss=1.1130, take_profit=1.1290, entry_price=1.1200, timestamp=ts[19]),
    ]
    config = _base_config()
    expected = ScenarioExpected(
        trade_count=3,
        entry_bar_index=6,
        side="LONG",
        sl_triggered=False,
        tp_triggered=True,
        ambiguous=False,
        overnight_hold=False,
        critical_incident=False,
        rejected=False,
        cost_scenario="base",
        state_terminal="AUDITED",
    )
    return config, bars, ts, signals, expected


# ── Scenario 12 ───────────────────────────────────────────────────────
def scenario_deterministic_repeat():
    """Same data run twice → identical trade list."""
    # Reuses scenario 1 data
    config, bars, ts, signals, expected = scenario_long_entry_sl_only()
    return config, bars, ts, signals, expected


# ── Registry ──────────────────────────────────────────────────────────
def get_all_scenarios() -> list:
    """Return all 12 scenarios with names."""
    return [
        ("long_entry_sl_only", *scenario_long_entry_sl_only()),
        ("long_entry_tp_only", *scenario_long_entry_tp_only()),
        ("short_entry_sl_only", *scenario_short_entry_sl_only()),
        ("short_entry_tp_only", *scenario_short_entry_tp_only()),
        ("ambiguous_bar", *scenario_ambiguous_bar()),
        ("overnight_hold", *scenario_overnight_hold()),
        ("missing_sl_rejected", *scenario_missing_sl_rejected()),
        ("invalid_sl_rejected", *scenario_invalid_sl_rejected()),
        ("max_risk_rejection", *scenario_max_risk_rejection()),
        ("zero_volume_rejection", *scenario_zero_volume_rejection()),
        ("multi_trade", *scenario_multi_trade()),
        ("deterministic_repeat", *scenario_deterministic_repeat()),
    ]
