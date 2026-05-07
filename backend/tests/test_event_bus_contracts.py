import asyncio

import pytest
from app.core.event_bus import EventBus


@pytest.mark.asyncio
async def test_event_bus_drains_unhandled_events():
    bus = EventBus()
    processor = asyncio.create_task(bus.start_processing())
    try:
        await bus.emit("unhandled.event", {"id": "evt-1"})
        await asyncio.wait_for(bus._queue.join(), timeout=1)
    finally:
        bus.stop()
        processor.cancel()
        with pytest.raises(asyncio.CancelledError):
            await processor

    assert bus.get_event_stats()["unhandled.event"] == 1
    assert bus.get_failed_events() == []
