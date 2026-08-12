# ADR-001: Event-Driven Architecture

## Status
Accepted — Phase A (Week 1-2)

## Context
Graxia quant_os components (strategy, risk engine, execution manager) currently call each other directly. This creates tight coupling and makes it hard to add new subscribers (e.g., audit logging, multi-agent pipeline) without modifying existing code.

## Decision
Introduce an in-process event bus with typed events:
- `core/events.py` — frozen dataclass event types
- `core/event_bus.py` — synchronous pub/sub bus with handler isolation

## Consequences
+ Components decouple — strategy doesn't know about risk engine
+ New subscribers (logging, agents, audit) can be added without modifying publishers
+ Event types serve as a documented contract between components
- Slight overhead from event dispatch (~1µs per event)
- Handler exceptions are isolated (logged, don't crash the bus)

## Alternatives Considered
1. **Direct method calls** (status quo) — rejected: tight coupling
2. **asyncio event loop** — rejected: overkill for in-process, adds complexity
3. **External message broker** — rejected: no need for cross-process communication

## References
- quanttrader/letianzj event-driven pattern
- ADR template from Michael Nygard
