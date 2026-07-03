"""In-memory business event repository for local/runtime-safe emission."""
from __future__ import annotations

from app.runtime.contracts import BusinessEvent


class InMemoryBusinessEventRepository:
    def __init__(self) -> None:
        self._events: list[BusinessEvent] = []
        self._idempotency_index: dict[str, BusinessEvent] = {}

    async def add(self, event: BusinessEvent) -> BusinessEvent:
        if event.idempotency_key:
            existing = self._idempotency_index.get(event.idempotency_key)
            if existing is not None:
                return existing
            self._idempotency_index[event.idempotency_key] = event
        self._events.append(event)
        return event

    async def list(
        self,
        *,
        organization_id: str | None = None,
        event_type: str | None = None,
    ) -> list[BusinessEvent]:
        events = self._events
        if organization_id:
            events = [event for event in events if str(event.organization_id) == organization_id]
        if event_type:
            events = [event for event in events if event.event_type == event_type]
        return list(events)

    async def clear(self) -> None:
        self._events.clear()
        self._idempotency_index.clear()
