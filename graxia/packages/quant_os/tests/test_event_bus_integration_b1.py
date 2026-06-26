"""Tests for B1: Wire EventBus into BacktestEngine.run()"""

from datetime import UTC, datetime, timedelta
from decimal import Decimal

from graxia.packages.quant_os.backtest.engine import BacktestConfig, BacktestEngine
from graxia.packages.quant_os.core.enums import SignalType
from graxia.packages.quant_os.core.event_bus import EventBus
from graxia.packages.quant_os.core.events import BarEvent
from graxia.packages.quant_os.strategies.base import Signal, Strategy

# ── Helpers ────────────────────────────────────────────────────────


def _make_ohlcv(n: int = 300) -> tuple[dict[str, list], list[datetime]]:
    """Generate synthetic OHLCV data with timestamps."""
    base_time = datetime(2024, 1, 1)
    close = [100.0 + i * 0.1 for i in range(n)]
    high = [c + 0.5 for c in close]
    low = [c - 0.5 for c in close]
    open_p = [c - 0.05 for c in close]
    volume = [1000.0 + i for i in range(n)]
    timestamps = [base_time + timedelta(minutes=15 * i) for i in range(n)]
    return {
        "open": open_p,
        "high": high,
        "low": low,
        "close": close,
        "volume": volume,
    }, timestamps


class NoTradeStrategy(Strategy):
    """Strategy that never trades — isolates EventBus from signal logic."""

    def generate_signal(self, symbol, ohlcv_data, indicators=None, regime=None, **kwargs):
        return None

    def required_features(self):
        return []


class BuyOnceStrategy(Strategy):
    """Strategy that buys once on first valid bar, then stops."""

    def __init__(self):
        super().__init__()
        self._bought = False

    def generate_signal(self, symbol, ohlcv_data, indicators=None, regime=None, **kwargs):
        closes = ohlcv_data.get("close", [])
        if self._bought or len(closes) < 21:
            return None
        self._bought = True
        price = Decimal(str(closes[-1]))
        sl = price * Decimal("0.99")
        tp = price * Decimal("1.03")
        return Signal(
            id="buy_once",
            strategy_id=self.id,
            symbol=symbol,
            signal_type=SignalType.BUY,
            timestamp=datetime.utcnow(),
            entry_price=price,
            stop_loss=sl,
            take_profit=tp,
            confidence=1.0,
        )

    def required_features(self):
        return ["ema_9"]


def _make_engine(strategy=None, config=None):
    """Create a configured engine with data loaded."""
    data, ts = _make_ohlcv()
    engine = BacktestEngine(config=config or BacktestConfig(strict_mtf=False))
    engine.set_strategy(strategy or NoTradeStrategy())
    engine.load_data(data, ts)
    return engine, data, ts


def _run_engine(event_bus=None, strategy=None, config=None):
    """Run a backtest and return (result, data, timestamps)."""
    engine, data, ts = _make_engine(strategy=strategy, config=config)
    result = engine.run(event_bus=event_bus)
    return result, data, ts


# ── Tests ──────────────────────────────────────────────────────────


class TestEventBusReceivesBarEvents:
    def test_receives_bar_event_per_bar(self):
        bus = EventBus()
        received = []
        bus.subscribe(BarEvent, lambda e: received.append(e))

        _run_engine(event_bus=bus)

        # Loop runs from i=1 to total_bars-1 → total_bars - 1 events
        assert len(received) == 299

    def test_published_count_matches(self):
        bus = EventBus()
        bus.subscribe(BarEvent, lambda e: None)

        _run_engine(event_bus=bus)

        assert bus.published_count == 299


class TestBarEventContent:
    def test_ohlcv_data_correct(self):
        bus = EventBus()
        received = []
        bus.subscribe(BarEvent, lambda e: received.append(e))

        _, data, _ = _run_engine(event_bus=bus)

        for evt in received:
            bar_i = evt.bar_index
            assert evt.symbol == "BACKTEST"
            assert evt.timeframe == "M15"
            assert evt.open == data["open"][bar_i]
            assert evt.high == data["high"][bar_i]
            assert evt.low == data["low"][bar_i]
            assert evt.close == data["close"][bar_i]
            assert evt.volume == data["volume"][bar_i]

    def test_bar_index_sequential(self):
        bus = EventBus()
        received = []
        bus.subscribe(BarEvent, lambda e: received.append(e))

        _run_engine(event_bus=bus)

        for i, evt in enumerate(received):
            assert evt.bar_index == i + 1

    def test_source_is_backtest_engine(self):
        bus = EventBus()
        received = []
        bus.subscribe(BarEvent, lambda e: received.append(e))

        _run_engine(event_bus=bus)

        for evt in received:
            assert evt.source == "backtest_engine"


class TestPnLIdentity:
    def test_pnl_matches_without_bus(self):
        """P&L must be identical with and without event_bus."""
        data, ts = _make_ohlcv()

        engine_with = BacktestEngine(config=BacktestConfig(strict_mtf=False))
        engine_with.set_strategy(BuyOnceStrategy())
        engine_with.load_data(data, ts)
        bus = EventBus()
        bus.subscribe(BarEvent, lambda e: None)
        result_with = engine_with.run(event_bus=bus)

        engine_without = BacktestEngine(config=BacktestConfig(strict_mtf=False))
        engine_without.set_strategy(BuyOnceStrategy())
        engine_without.load_data(data, ts)
        result_without = engine_without.run()

        assert result_with["metrics"].total_pnl == result_without["metrics"].total_pnl
        assert result_with["metrics"].total_trades == result_without["metrics"].total_trades
        assert len(result_with["trades"]) == len(result_without["trades"])


class TestBackwardCompatibility:
    def test_none_bus_works(self):
        result, _, _ = _run_engine(event_bus=None)
        assert hasattr(result["metrics"], "total_pnl")
        assert "trades" in result

    def test_no_bus_keyword_works(self):
        result, _, _ = _run_engine()
        assert hasattr(result["metrics"], "total_pnl")


class TestLookaheadGuard:
    def test_bar_events_do_not_leak_future_data(self):
        """Each BarEvent must only contain data from its own bar index."""
        bus = EventBus()
        received = []
        bus.subscribe(BarEvent, lambda e: received.append(e))

        _, data, _ = _run_engine(event_bus=bus)

        for evt in received:
            assert evt.bar_index < len(data["close"])
            assert evt.close == data["close"][evt.bar_index]

    def test_bar_event_timestamp_not_in_future(self):
        bus = EventBus()
        received = []
        bus.subscribe(BarEvent, lambda e: received.append(e))

        _run_engine(event_bus=bus)

        now = datetime.now(UTC)
        for evt in received:
            assert evt.timestamp <= now + timedelta(seconds=5)


class TestEventBusNoneDefault:
    def test_default_parameter_is_none(self):
        import inspect

        sig = inspect.signature(BacktestEngine.run)
        assert sig.parameters["event_bus"].default is None
