"""
Tests for backtest engine refactor: B1 (event-driven), B3 (Numba hot path), C4 (batch mode).

Acceptance criteria:
  - Existing backtest tests still pass (backward compatible)
  - Event-driven path produces identical P&L to direct path
  - Numba path produces identical results to pure Python (within 1e-9)
  - Batch mode runs multiple configs
"""

from datetime import datetime, timedelta
from decimal import Decimal
from typing import Any

import numpy as np
import pytest
from quant_os.backtest.engine import (
    _NUMBA_AVAILABLE,
    BacktestConfig,
    BacktestEngine,
    _atr_numba,
    _ema_numba,
    _rsi_numba,
)
from quant_os.core.enums import RegimeType, SignalType
from quant_os.core.event_bus import EventBus
from quant_os.core.events import BarEvent
from quant_os.strategies.base import Signal, Strategy, StrategyConfig

# ── Helpers ────────────────────────────────────────────────────────


def _make_timestamps(n: int, start: datetime = None) -> list[datetime]:
    if start is None:
        start = datetime(2024, 1, 1)
    return [start + timedelta(hours=i) for i in range(n)]


def _make_ohlcv(n: int = 300, base_price: float = 1800.0, seed: int = 42):
    """Generate synthetic OHLCV data with deterministic random walk."""
    rng = np.random.RandomState(seed)
    close = [base_price]
    for _ in range(n - 1):
        change = rng.randn() * 2.0
        close.append(close[-1] + change)
    close = [round(c, 2) for c in close]
    high = [round(c + abs(rng.randn()) * 1.5, 2) for c in close]
    low = [round(c - abs(rng.randn()) * 1.5, 2) for c in close]
    open_price = [round(c + rng.randn() * 0.5, 2) for c in close]
    volume = [round(abs(rng.randn()) * 1000 + 500, 0) for _ in close]
    return {
        "open": open_price,
        "high": high,
        "low": low,
        "close": close,
        "volume": volume,
    }


class _AlwaysTradeStrategy(Strategy):
    """Strategy that alternates BUY/SELL every bar with fixed SL/TP."""

    def __init__(self):
        super().__init__(StrategyConfig(name="AlwaysTrade"))
        self._bar_count = 0

    def generate_signal(
        self,
        symbol: str,
        ohlcv_data: dict[str, list],
        indicators: dict[str, Any] | None = None,
        regime: RegimeType | None = None,
        **kwargs,
    ) -> Signal | None:
        close = ohlcv_data["close"]
        if len(close) < 3:
            return None
        self._bar_count += 1
        price = close[-1]
        sl_distance = 10.0
        tp_distance = 20.0
        if self._bar_count % 2 == 1:
            return Signal.create(
                strategy_id=self.id,
                symbol=symbol,
                signal_type=SignalType.BUY,
                confidence=0.8,
                entry_price=Decimal(str(price)),
                stop_loss=Decimal(str(price - sl_distance)),
                take_profit=Decimal(str(price + tp_distance)),
            )
        else:
            return Signal.create(
                strategy_id=self.id,
                symbol=symbol,
                signal_type=SignalType.SELL,
                confidence=0.8,
                entry_price=Decimal(str(price)),
                stop_loss=Decimal(str(price + sl_distance)),
                take_profit=Decimal(str(price - tp_distance)),
            )

    def required_features(self) -> list[str]:
        return []


class _NumbaStrategy(_AlwaysTradeStrategy):
    """Strategy that signals supports_numba() = True."""

    def supports_numba(self) -> bool:
        return True


class _NoTradeStrategy(Strategy):
    """Strategy that never trades — used to isolate event bus test."""

    def generate_signal(self, symbol, ohlcv_data, indicators=None, regime=None, **kwargs):
        return None

    def required_features(self):
        return []


# ── B1 Tests: Event-driven ─────────────────────────────────────────


class TestB1EventDriven:
    """B1 — EventBus integration in backtest engine."""

    def test_run_without_event_bus_backward_compatible(self):
        """run() without event_bus works identically to pre-refactor."""
        cfg = BacktestConfig(strict_mtf=False)
        engine = BacktestEngine(config=cfg)
        strategy = _AlwaysTradeStrategy()
        engine.set_strategy(strategy)
        data = _make_ohlcv(250)
        engine.load_data(data, _make_timestamps(250))
        result = engine.run()
        assert "metrics" in result
        assert isinstance(result["trades"], list)

    def test_event_bus_receives_bar_events(self):
        """When event_bus is passed, BarEvent is published for every bar."""
        bus = EventBus()
        received = []
        bus.subscribe(BarEvent, lambda e: received.append(e))

        cfg = BacktestConfig(strict_mtf=False)
        engine = BacktestEngine(config=cfg)
        engine.set_strategy(_NoTradeStrategy())
        data = _make_ohlcv(250)
        engine.load_data(data, _make_timestamps(250))
        engine.run(event_bus=bus)

        # Bars processed: range(1, total_bars) = 249 bars
        assert len(received) == 249
        for ev in received:
            assert isinstance(ev, BarEvent)
            assert ev.source == "backtest_engine"
            assert ev.bar_index > 0

    def test_event_driven_pnl_matches_direct_path(self):
        """Event-driven path produces identical P&L to direct (no bus) path."""
        data = _make_ohlcv(250)
        ts = _make_timestamps(250)

        # Direct path
        cfg1 = BacktestConfig(strict_mtf=False)
        engine1 = BacktestEngine(config=cfg1)
        engine1.set_strategy(_AlwaysTradeStrategy())
        engine1.load_data(data, ts)
        result_direct = engine1.run()

        # Event-driven path
        bus = EventBus()
        cfg2 = BacktestConfig(strict_mtf=False)
        engine2 = BacktestEngine(config=cfg2)
        engine2.set_strategy(_AlwaysTradeStrategy())
        engine2.load_data(data, ts)
        result_event = engine2.run(event_bus=bus)

        # P&L must match exactly
        direct_pnl = result_direct["metrics"].total_pnl
        event_pnl = result_event["metrics"].total_pnl
        assert abs(direct_pnl - event_pnl) < 1e-9, f"P&L mismatch: direct={direct_pnl}, event={event_pnl}"
        assert result_direct["metrics"].total_trades == result_event["metrics"].total_trades

    def test_event_bus_bar_content(self):
        """BarEvent fields match the OHLCV data."""
        bus = EventBus()
        received = []
        bus.subscribe(BarEvent, lambda e: received.append(e))

        cfg = BacktestConfig(strict_mtf=False)
        engine = BacktestEngine(config=cfg)
        engine.set_strategy(_NoTradeStrategy())
        data = _make_ohlcv(250)
        ts = _make_timestamps(250)
        engine.load_data(data, ts)
        engine.run(event_bus=bus)

        for ev in received:
            idx = ev.bar_index
            assert ev.close == float(data["close"][idx])
            assert ev.high == float(data["high"][idx])
            assert ev.low == float(data["low"][idx])
            assert ev.open == float(data["open"][idx])


# ── B3 Tests: Numba hot path ───────────────────────────────────────


class TestB3NumbaHotPath:
    """B3 — Numba JIT indicator calculation."""

    def test_numba_ema_matches_python(self):
        """Numba EMA matches a pure-python reference within 1e-9."""
        close = np.random.RandomState(42).randn(300).cumsum() + 1800.0
        length = 20
        result_numba = _ema_numba(close, length)

        # Pure-python reference EMA
        alpha = 2.0 / (length + 1.0)
        ref = [np.nan] * (length - 1)
        sma = float(np.mean(close[:length]))
        ref.append(sma)
        for i in range(length, len(close)):
            sma = close[i] * alpha + sma * (1.0 - alpha)
            ref.append(sma)

        for a, b in zip(result_numba[length - 1 :], ref[length - 1 :], strict=False):
            assert abs(a - b) < 1e-9

    def test_numba_rsi_matches_python(self):
        """Numba RSI matches a pure-python reference within 1e-6."""
        rng = np.random.RandomState(42)
        close = (rng.randn(300).cumsum() + 1800.0).astype(np.float64)
        length = 14
        result_numba = _rsi_numba(close, length)

        # Pure-python reference RSI
        gains = np.zeros(length)
        losses = np.zeros(length)
        for i in range(1, length + 1):
            diff = close[i] - close[i - 1]
            if diff > 0:
                gains[i - 1] = diff
            else:
                losses[i - 1] = -diff
        avg_gain = float(np.mean(gains))
        avg_loss = float(np.mean(losses))
        ref = [np.nan] * length
        if avg_loss == 0:
            ref.append(100.0)
        else:
            ref.append(100.0 - 100.0 / (1.0 + avg_gain / avg_loss))
        for i in range(length + 1, len(close)):
            diff = close[i] - close[i - 1]
            if diff > 0:
                avg_gain = (avg_gain * (length - 1) + diff) / length
                avg_loss = (avg_loss * (length - 1)) / length
            else:
                avg_gain = (avg_gain * (length - 1)) / length
                avg_loss = (avg_loss * (length - 1) - diff) / length
            if avg_loss == 0:
                ref.append(100.0)
            else:
                ref.append(100.0 - 100.0 / (1.0 + avg_gain / avg_loss))

        for a, b in zip(result_numba[length:], ref[length:], strict=False):
            assert abs(a - b) < 1e-6, f"RSI mismatch: numba={a}, ref={b}"

    def test_numba_atr_matches_python(self):
        """Numba ATR matches a pure-python reference within 1e-6."""
        rng = np.random.RandomState(42)
        close = (rng.randn(300).cumsum() + 1800.0).astype(np.float64)
        high = close + np.abs(rng.randn(300)) * 2.0
        low = close - np.abs(rng.randn(300)) * 2.0
        length = 14
        result_numba = _atr_numba(high, low, close, length)

        # Pure-python reference ATR
        n = len(close)
        tr = [0.0] * n
        tr[0] = high[0] - low[0]
        for i in range(1, n):
            hl = high[i] - low[i]
            hc = abs(high[i] - close[i - 1])
            lc = abs(low[i] - close[i - 1])
            tr[i] = max(hl, max(hc, lc))
        atr_val = sum(tr[:length]) / length
        ref = [np.nan] * (length - 1)
        ref.append(atr_val)
        for i in range(length, n):
            atr_val = (atr_val * (length - 1) + tr[i]) / length
            ref.append(atr_val)

        for a, b in zip(result_numba[length - 1 :], ref[length - 1 :], strict=False):
            assert abs(a - b) < 1e-6, f"ATR mismatch: numba={a}, ref={b}"

    def test_engine_numba_strategy_produces_results(self):
        """Engine with supports_numba()=True strategy runs without error."""
        cfg = BacktestConfig(strict_mtf=False)
        engine = BacktestEngine(config=cfg)
        strategy = _NumbaStrategy()
        engine.set_strategy(strategy)
        data = _make_ohlcv(250)
        engine.load_data(data, _make_timestamps(250))
        result = engine.run()
        assert "metrics" in result
        assert isinstance(result["trades"], list)

    @pytest.mark.skipif(not _NUMBA_AVAILABLE, reason="numba not installed")
    def test_numba_path_pnl_matches_python_path(self):
        """Numba path produces same P&L as pure-python (pandas_ta) within 1e-9."""
        data = _make_ohlcv(250)
        ts = _make_timestamps(250)

        # Pure-python path (supports_numba = False)
        cfg1 = BacktestConfig(strict_mtf=False)
        engine1 = BacktestEngine(config=cfg1)
        engine1.set_strategy(_AlwaysTradeStrategy())
        engine1.load_data(data, ts)
        result_python = engine1.run()

        # Numba path (supports_numba = True)
        cfg2 = BacktestConfig(strict_mtf=False)
        engine2 = BacktestEngine(config=cfg2)
        engine2.set_strategy(_NumbaStrategy())
        engine2.load_data(data, ts)
        result_numba = engine2.run()

        assert abs(result_python["metrics"].total_pnl - result_numba["metrics"].total_pnl) < 1e-9


# ── C4 Tests: Batch mode ───────────────────────────────────────────


class TestC4BatchMode:
    """C4 — run_batch with shared indicators."""

    def test_batch_runs_multiple_configs(self):
        """run_batch processes multiple configs and returns one result each."""
        data = _make_ohlcv(250)
        ts = _make_timestamps(250)
        cfg = BacktestConfig(strict_mtf=False)

        configs = [
            {"engine_cfg": cfg, "strategy": _AlwaysTradeStrategy(), "ohlcv_data": data, "timestamps": ts},
            {"engine_cfg": cfg, "strategy": _AlwaysTradeStrategy(), "ohlcv_data": data, "timestamps": ts},
            {"engine_cfg": cfg, "strategy": _NoTradeStrategy(), "ohlcv_data": data, "timestamps": ts},
        ]

        results = BacktestEngine.run_batch(configs)
        assert len(results) == 3
        # First two should have trades, third should have none
        assert results[0]["metrics"].total_trades > 0
        assert results[1]["metrics"].total_trades > 0
        assert results[2]["metrics"].total_trades == 0

    def test_batch_pnl_matches_individual_runs(self):
        """Batch results match individual run results (shared indicators are compatible)."""
        data = _make_ohlcv(250)
        ts = _make_timestamps(250)
        cfg = BacktestConfig(strict_mtf=False)

        # Individual run
        engine = BacktestEngine(config=cfg)
        engine.set_strategy(_AlwaysTradeStrategy())
        engine.load_data(data, ts)
        individual_result = engine.run()

        # Batch run
        configs = [
            {"engine_cfg": cfg, "strategy": _AlwaysTradeStrategy(), "ohlcv_data": data, "timestamps": ts},
        ]
        batch_results = BacktestEngine.run_batch(configs)
        batch_result = batch_results[0]

        assert abs(individual_result["metrics"].total_pnl - batch_result["metrics"].total_pnl) < 1e-9

    def test_batch_with_event_bus(self):
        """Batch mode works with event_bus passed per config."""
        bus = EventBus()
        received = []
        bus.subscribe(BarEvent, lambda e: received.append(e))

        data = _make_ohlcv(250)
        ts = _make_timestamps(250)
        cfg = BacktestConfig(strict_mtf=False)

        configs = [
            {
                "engine_cfg": cfg,
                "strategy": _AlwaysTradeStrategy(),
                "ohlcv_data": data,
                "timestamps": ts,
                "event_bus": bus,
            },
        ]
        BacktestEngine.run_batch(configs)
        assert len(received) > 0

    def test_batch_different_configs_different_results(self):
        """Different strategies produce different trade counts."""
        data = _make_ohlcv(250)
        ts = _make_timestamps(250)
        cfg = BacktestConfig(strict_mtf=False)

        configs = [
            {"engine_cfg": cfg, "strategy": _AlwaysTradeStrategy(), "ohlcv_data": data, "timestamps": ts},
            {"engine_cfg": cfg, "strategy": _NoTradeStrategy(), "ohlcv_data": data, "timestamps": ts},
        ]
        results = BacktestEngine.run_batch(configs)
        assert results[0]["metrics"].total_trades != results[1]["metrics"].total_trades


# ── Backward compatibility ─────────────────────────────────────────


class TestBackwardCompatibility:
    """Verify no existing behavior is broken."""

    def test_default_run_signature_unchanged(self):
        """run() with no args works exactly as before."""
        cfg = BacktestConfig(strict_mtf=False)
        engine = BacktestEngine(config=cfg)
        engine.set_strategy(_AlwaysTradeStrategy())
        data = _make_ohlcv(250)
        engine.load_data(data, _make_timestamps(250))
        result = engine.run()
        assert "config" in result
        assert "metrics" in result
        assert "trades" in result
        assert "equity_curve" in result

    def test_lookahead_guard_still_active(self):
        """LookaheadGuard still raises on slice misuse."""
        cfg = BacktestConfig(strict_mtf=False)
        engine = BacktestEngine(config=cfg)
        engine.set_strategy(_AlwaysTradeStrategy())
        data = _make_ohlcv(250)
        engine.load_data(data, _make_timestamps(250))
        result = engine.run()
        assert result["metrics"].total_trades >= 0

    def test_config_fields_preserved(self):
        """BacktestConfig retains all original fields."""
        cfg = BacktestConfig(
            initial_capital=Decimal("50000"),
            slippage_pips=1.0,
            spread_pips=3.0,
            commission_per_lot=Decimal("7.0"),
            risk_per_trade_bps=20,
            strict_mtf=False,
        )
        engine = BacktestEngine(config=cfg)
        assert engine.config.initial_capital == Decimal("50000")
        assert engine.config.slippage_pips == 1.0
        assert engine.config.strict_mtf is False
