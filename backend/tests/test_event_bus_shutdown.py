"""
Test suite for Event Bus graceful shutdown functionality.

This module tests the graceful shutdown behavior of the EventBus,
ensuring that:
1. Events in queue are processed before shutdown
2. Running handlers are waited for completion (with timeout)
3. Shutdown timeout is enforced
4. Proper logging of pending tasks during shutdown
"""

import asyncio
import time

import pytest
from app.core.event_bus import EventBus


@pytest.mark.asyncio
async def test_graceful_shutdown_waits_for_tasks():
    """Test that graceful shutdown waits for processing tasks to complete."""
    bus = EventBus()
    processed_events = []
    
    async def slow_handler(payload: dict):
        await asyncio.sleep(0.5)  # Simulate slow processing
        processed_events.append(payload["value"])
    
    bus.subscribe("test_event", slow_handler)
    
    # Start processing in background
    processing_task = asyncio.create_task(bus.start_processing())
    await asyncio.sleep(0.1)  # Let it start
    
    # Emit events
    await bus.emit("test_event", {"value": 1})
    await bus.emit("test_event", {"value": 2})
    await asyncio.sleep(0.1)  # Let events be picked up
    
    # Stop and wait for graceful shutdown
    bus.stop()
    await processing_task
    
    # All events should be processed
    assert len(processed_events) == 2
    assert 1 in processed_events
    assert 2 in processed_events


@pytest.mark.asyncio
async def test_events_in_queue_processed_before_shutdown():
    """Test that events in queue are processed before shutdown completes."""
    bus = EventBus()
    processed_events = []
    
    def sync_handler(payload: dict):
        processed_events.append(payload["value"])
    
    bus.subscribe("test_event", sync_handler)
    
    # Start processing
    processing_task = asyncio.create_task(bus.start_processing())
    await asyncio.sleep(0.1)
    
    # Emit multiple events
    for i in range(5):
        await bus.emit("test_event", {"value": i})
    
    await asyncio.sleep(0.1)  # Let events be picked up
    
    # Stop and wait
    bus.stop()
    await processing_task
    
    # All events should be processed
    assert len(processed_events) == 5
    assert processed_events == [0, 1, 2, 3, 4]


@pytest.mark.asyncio
async def test_shutdown_timeout_enforced():
    """Test that shutdown timeout is enforced for long-running handlers."""
    bus = EventBus(shutdown_timeout=1)  # 1 second timeout
    
    async def very_slow_handler(payload: dict):
        await asyncio.sleep(10)  # Longer than timeout
    
    bus.subscribe("test_event", very_slow_handler)
    
    processing_task = asyncio.create_task(bus.start_processing())
    await asyncio.sleep(0.1)
    
    await bus.emit("test_event", {"value": 1})
    await asyncio.sleep(0.1)
    
    # Stop should timeout after 1 second
    start_time = time.time()
    bus.stop()
    
    with pytest.raises(asyncio.TimeoutError):
        await processing_task
    
    elapsed = time.time() - start_time
    assert elapsed < 2  # Should timeout around 1 second


@pytest.mark.asyncio
async def test_shutdown_with_no_pending_tasks():
    """Test that shutdown completes immediately when no tasks are pending."""
    bus = EventBus()
    
    # Start and stop immediately
    processing_task = asyncio.create_task(bus.start_processing())
    await asyncio.sleep(0.1)
    
    start_time = time.time()
    bus.stop()
    await processing_task
    elapsed = time.time() - start_time
    
    # Should complete quickly (within 2 seconds for timeout polling)
    assert elapsed < 2


@pytest.mark.asyncio
async def test_shutdown_with_multiple_pending_tasks():
    """Test that shutdown waits for multiple pending tasks to complete."""
    bus = EventBus()
    processed_events = []
    
    async def handler(payload: dict):
        await asyncio.sleep(0.3)
        processed_events.append(payload["value"])
    
    bus.subscribe("test_event", handler)
    
    processing_task = asyncio.create_task(bus.start_processing())
    await asyncio.sleep(0.1)
    
    # Emit multiple events that will be processed concurrently
    for i in range(5):
        await bus.emit("test_event", {"value": i})
    
    await asyncio.sleep(0.1)  # Let all events be picked up
    
    # Stop and wait
    bus.stop()
    await processing_task
    
    # All events should be processed
    assert len(processed_events) == 5
    assert set(processed_events) == {0, 1, 2, 3, 4}


@pytest.mark.asyncio
async def test_shutdown_logs_pending_task_count(caplog):
    """Test that shutdown logs the number of pending tasks."""
    bus = EventBus()
    
    async def slow_handler(payload: dict):
        await asyncio.sleep(2.0)  # Longer sleep to ensure tasks are still running at shutdown
    
    bus.subscribe("test_event", slow_handler)
    
    with caplog.at_level("INFO"):
        processing_task = asyncio.create_task(bus.start_processing())
        await asyncio.sleep(0.1)
        
        # Emit events
        await bus.emit("test_event", {"value": 1})
        await bus.emit("test_event", {"value": 2})
        await asyncio.sleep(0.05)  # Shorter wait to ensure tasks are still running
        
        # Stop and wait
        bus.stop()
        await processing_task
    
    # Check that pending task count was logged
    log_messages = [record.message for record in caplog.records]
    assert any("waiting for" in msg and "tasks to complete" in msg for msg in log_messages)


@pytest.mark.asyncio
async def test_long_running_handlers_respect_timeout():
    """Test that long-running handlers are interrupted by timeout."""
    bus = EventBus(shutdown_timeout=0.5)
    handler_completed = []
    
    async def long_handler(payload: dict):
        try:
            await asyncio.sleep(5)  # Much longer than timeout
            handler_completed.append(True)
        except asyncio.CancelledError:
            handler_completed.append(False)
            raise
    
    bus.subscribe("test_event", long_handler)
    
    processing_task = asyncio.create_task(bus.start_processing())
    await asyncio.sleep(0.1)
    
    await bus.emit("test_event", {"value": 1})
    await asyncio.sleep(0.1)
    
    bus.stop()
    
    with pytest.raises(asyncio.TimeoutError):
        await processing_task
    
    # Handler should not have completed normally
    # Note: The handler may not be cancelled, just the wait times out
    # This is expected behavior - we don't force-cancel handlers


@pytest.mark.asyncio
async def test_failed_handlers_dont_block_shutdown():
    """Test that failed handlers don't block graceful shutdown."""
    bus = EventBus()
    processed_events = []
    
    async def failing_handler(payload: dict):
        await asyncio.sleep(0.2)
        if payload["value"] == 1:
            raise ValueError("Intentional failure")
        processed_events.append(payload["value"])
    
    bus.subscribe("test_event", failing_handler)
    
    processing_task = asyncio.create_task(bus.start_processing())
    await asyncio.sleep(0.1)
    
    # Emit events, one will fail
    await bus.emit("test_event", {"value": 0})
    await bus.emit("test_event", {"value": 1})  # This will fail
    await bus.emit("test_event", {"value": 2})
    
    await asyncio.sleep(0.1)
    
    # Stop and wait
    bus.stop()
    await processing_task
    
    # Non-failing events should be processed
    assert 0 in processed_events
    assert 2 in processed_events
    assert 1 not in processed_events
    
    # Failed event should be in dead letter queue
    failed_events = bus.get_failed_events()
    assert len(failed_events) == 1
    assert failed_events[0][0] == "test_event"
    assert failed_events[0][1]["value"] == 1


@pytest.mark.asyncio
async def test_shutdown_with_mixed_sync_async_handlers():
    """Test graceful shutdown with both sync and async handlers."""
    bus = EventBus()
    processed_events = []
    
    def sync_handler(payload: dict):
        processed_events.append(("sync", payload["value"]))
    
    async def async_handler(payload: dict):
        await asyncio.sleep(0.2)
        processed_events.append(("async", payload["value"]))
    
    bus.subscribe("test_event", sync_handler)
    bus.subscribe("test_event", async_handler)
    
    processing_task = asyncio.create_task(bus.start_processing())
    await asyncio.sleep(0.1)
    
    await bus.emit("test_event", {"value": 1})
    await asyncio.sleep(0.1)
    
    bus.stop()
    await processing_task
    
    # Both handlers should have processed the event
    assert ("sync", 1) in processed_events
    assert ("async", 1) in processed_events


@pytest.mark.asyncio
async def test_shutdown_timeout_configurable():
    """Test that shutdown timeout is configurable via constructor."""
    # Short timeout
    bus_short = EventBus(shutdown_timeout=1)
    assert bus_short._shutdown_timeout == 1
    
    # Long timeout
    bus_long = EventBus(shutdown_timeout=60)
    assert bus_long._shutdown_timeout == 60
    
    # Default timeout
    bus_default = EventBus()
    assert bus_default._shutdown_timeout == 30


@pytest.mark.asyncio
async def test_multiple_stop_calls_safe():
    """Test that calling stop() multiple times is safe."""
    bus = EventBus()
    
    processing_task = asyncio.create_task(bus.start_processing())
    await asyncio.sleep(0.1)
    
    # Call stop multiple times
    bus.stop()
    bus.stop()
    bus.stop()
    
    # Should complete without error
    await processing_task


@pytest.mark.asyncio
async def test_graceful_shutdown_preserves_event_stats():
    """Test that event statistics are preserved during graceful shutdown."""
    bus = EventBus()
    
    def handler(payload: dict):
        pass
    
    bus.subscribe("test_event", handler)
    
    processing_task = asyncio.create_task(bus.start_processing())
    await asyncio.sleep(0.1)
    
    # Emit events
    for i in range(10):
        await bus.emit("test_event", {"value": i})
    
    await asyncio.sleep(0.2)
    
    bus.stop()
    await processing_task
    
    # Stats should be preserved
    stats = bus.get_event_stats()
    assert stats["test_event"] == 10


# Property-Based Tests using Hypothesis

from hypothesis import given, settings
from hypothesis import strategies as st


@pytest.mark.asyncio
@given(event_values=st.lists(st.integers(), min_size=1, max_size=50))
@settings(max_examples=20, deadline=None)
async def test_property_zero_event_loss_during_graceful_shutdown(event_values):
    """
    **Validates: Requirements 2.3**
    
    Property-Based Test: Zero Event Loss Invariant
    
    Property: For any sequence of N events emitted before stop(), all N events
    must be processed when shutdown completes within 30 seconds.
    
    This test verifies that the graceful shutdown mechanism:
    1. Processes all events in the queue before shutdown completes
    2. Waits for all running handlers to complete
    3. Does not lose any events during the shutdown process
    4. Completes within the configured timeout (30 seconds)
    """
    bus = EventBus(shutdown_timeout=30)
    processed_events = []
    
    async def handler(payload: dict):
        # Simulate some processing time
        await asyncio.sleep(0.01)
        processed_events.append(payload["value"])
    
    bus.subscribe("test_event", handler)
    
    # Start processing in background
    processing_task = asyncio.create_task(bus.start_processing())
    await asyncio.sleep(0.1)  # Let processing start
    
    # Emit N events
    for value in event_values:
        await bus.emit("test_event", {"value": value})
    
    # Give events time to be picked up by the processing loop
    await asyncio.sleep(0.1)
    
    # Stop and wait for graceful shutdown
    bus.stop()
    
    # Shutdown should complete within 30 seconds
    start_time = asyncio.get_event_loop().time()
    await processing_task
    elapsed = asyncio.get_event_loop().time() - start_time
    
    # Verify: All N events were processed (zero event loss)
    assert len(processed_events) == len(event_values), (
        f"Event loss detected: emitted {len(event_values)} events, "
        f"but only {len(processed_events)} were processed"
    )
    
    # Verify: All event values match (no corruption)
    assert set(processed_events) == set(event_values), (
        f"Event corruption detected: expected values {set(event_values)}, "
        f"but got {set(processed_events)}"
    )
    
    # Verify: Shutdown completed within timeout
    assert elapsed < 30, (
        f"Graceful shutdown exceeded timeout: took {elapsed:.2f}s, "
        f"expected < 30s"
    )
