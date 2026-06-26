# ADR-003: Event-Driven Backtest Engine

## Status
Accepted — Phase A (Week 1-2)

## Context
The backtest engine (`backtest/engine.py`) iterates bars sequentially and calls strategy methods directly. This works but prevents attaching external observers (audit logging, multi-agent pipelines, telemetry) without modifying the engine. ADR-001 introduced an event bus; this ADR connects the backtest engine to it.

## Decision
Add optional `EventBus` parameter to `BacktestEngine.run()`. When provided:
1. Engine publishes a `BarEvent` for every bar in the loop
2. Strategy still receives direct `generate_signal()` call (backward compatible)
3. External subscribers receive the same bar data for observation

Key code path:
```python
# backtest/engine.py:372
def run(self, event_bus=None) -> Dict[str, Any]:
    ...
    for i in range(1, total_bars):
        if event_bus is not None:
            bar_event = BarEvent(
                symbol="BACKTEST",
                timeframe="M15",
                open=float(bar_open),
                high=float(bar_high),
                low=float(bar_low),
                close=float(bar_close),
                volume=float(volume[i]),
                bar_index=i,
                source="backtest_engine",
            )
            event_bus.publish(bar_event)
        # ... strategy.generate_signal() still called directly
```

## Consequences
+ External agents can observe backtest bars without engine modification
+ Zero overhead when `event_bus=None` (default path unchanged)
+ Agent pipeline tested in backtest exactly as it runs in live
- ~1µs per `publish()` call (negligible for M15 bars)
- Event bus handler exceptions are logged, don't crash the engine

## Usage Example
```python
from core.event_bus import EventBus
from core.agents import TechnicalAnalystAgent, BullBearResearcherAgent

bus = EventBus()
analyst = TechnicalAnalystAgent()
researcher = BullBearResearcherAgent()

bus.subscribe(BarEvent, analyst.observe)
bus.subscribe(SignalEvent, researcher.observe)

engine = BacktestEngine(config)
engine.set_strategy(my_strategy)
engine.load_data(ohlcv_data, timestamps)
results = engine.run(event_bus=bus)
```

## Alternatives Considered
1. **Strategy hook callbacks** — rejected: couples observer to strategy class
2. **Separate observer class** — rejected: duplicates bar iteration logic
3. **Always-on event bus** — rejected: unnecessary overhead for simple backtests

## References
- `backtest/engine.py:372-436` — event_bus integration in main loop
- `core/events.py:41-52` — BarEvent definition
- `core/event_bus.py:48-77` — publish() with handler isolation
