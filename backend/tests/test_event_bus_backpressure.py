"""
Test suite for Event Bus backpressure and queue size limit functionality.

This module tests the backpressure behavior when the event queue reaches
its maximum size, ensuring that:
1. Queue size is limited to configured maximum
2. Emit operations handle full queue gracefully
3. Events are dropped when queue is full (with timeout)
4. Queue metrics are tracked correctly
5. Backpressure prevents memory exhaustion
"""

import asyncio

import pytest
from app.core.event_bus import EventBus


@pytest.mark.asyncio
async def test_queue_size_limit_enforced():
    """Test that queue size is limited to configured maximum."""
    bus = EventBus(max_queue_size=10)
    
    # Fill the queue
    for i in range(10):
        result = await bus.emit("test_event", {"value": i}, timeout=0.1)
        assert result is True
    
    # Queue should be full now
    metrics = bus.get_queue_metrics()
    assert metrics["queue_size"] == 10
    assert metrics["max_queue_size"] == 10
    assert metrics["queue_utilization_percent"] == 100


@pytest.mark.asyncio
async def test_emit_blocks_when_queue_full_with_none_timeout():
    """Test that emit blocks when queue is full and timeout is None."""
    bus = EventBus(max_queue_size=5)
    
    # Fill the queue without starting processing
    for i in range(5):
        await bus.emit("test_event", {"value": i}, timeout=0.1)
    
    # Try to emit with None timeout (should block)
    emit_task = asyncio.create_task(bus.emit("test_event", {"value": 999}, timeout=None))
    
    # Give it a moment to try
    await asyncio.sleep(0.1)
    
    # Task should still be pending (blocked)
    assert not emit_task.done()
    
    # Cancel the task to clean up
    emit_task.cancel()
    try:
        await emit_task
    except asyncio.CancelledError:
        pass


@pytest.mark.asyncio
async def test_emit_returns_false_when_queue_full_with_timeout():
    """Test that emit returns False when queue is full and timeout expires."""
    bus = EventBus(max_queue_size=5)
    
    # Fill the queue
    for i in range(5):
        result = await bus.emit("test_event", {"value": i}, timeout=0.1)
        assert result is True
    
    # Try to emit with short timeout
    result = await bus.emit("test_event", {"value": 999}, timeout=0.1)
    assert result is False
    
    # Check metrics
    metrics = bus.get_queue_metrics()
    assert metrics["dropped_events"] == 1
    assert metrics["queue_full_count"] == 1


@pytest.mark.asyncio
async def test_backpressure_prevents_memory_exhaustion():
    """Test that backpressure prevents unbounded memory growth."""
    bus = EventBus(max_queue_size=100)
    
    # Try to emit many events without processing
    successful = 0
    dropped = 0
    
    for i in range(150):
        result = await bus.emit("test_event", {"value": i}, timeout=0.01)
        if result:
            successful += 1
        else:
            dropped += 1
    
    # Should have dropped some events
    assert dropped > 0
    assert successful == 100  # Queue size
    
    metrics = bus.get_queue_metrics()
    assert metrics["dropped_events"] == dropped
    assert metrics["queue_size"] == 100


@pytest.mark.asyncio
async def test_queue_metrics_accuracy():
    """Test that queue metrics are accurate."""
    bus = EventBus(max_queue_size=20)
    
    # Emit some events
    for i in range(15):
        await bus.emit("test_event", {"value": i}, timeout=0.1)
    
    metrics = bus.get_queue_metrics()
    assert metrics["queue_size"] == 15
    assert metrics["max_queue_size"] == 20
    assert metrics["queue_utilization_percent"] == 75  # 15/20 * 100
    assert metrics["dropped_events"] == 0
    assert metrics["queue_full_count"] == 0


@pytest.mark.asyncio
async def test_queue_metrics_after_drops():
    """Test that queue metrics track drops correctly."""
    bus = EventBus(max_queue_size=5)
    
    # Fill queue
    for i in range(5):
        await bus.emit("test_event", {"value": i}, timeout=0.1)
    
    # Try to emit more (should drop)
    for i in range(3):
        await bus.emit("test_event", {"value": i + 100}, timeout=0.01)
    
    metrics = bus.get_queue_metrics()
    assert metrics["dropped_events"] == 3
    assert metrics["queue_full_count"] == 3
    assert metrics["queue_size"] == 5


@pytest.mark.asyncio
async def test_processing_reduces_queue_size():
    """Test that processing events reduces queue size."""
    bus = EventBus(max_queue_size=20)
    processed = []
    
    def handler(payload: dict):
        processed.append(payload["value"])
    
    bus.subscribe("test_event", handler)
    
    # Start processing
    processing_task = asyncio.create_task(bus.start_processing())
    await asyncio.sleep(0.1)
    
    # Emit events
    for i in range(10):
        await bus.emit("test_event", {"value": i}, timeout=0.1)
    
    # Wait for processing
    await asyncio.sleep(0.3)
    
    # Queue should be empty or nearly empty
    metrics = bus.get_queue_metrics()
    assert metrics["queue_size"] < 10
    assert len(processed) == 10
    
    # Cleanup
    bus.stop()
    await processing_task


@pytest.mark.asyncio
async def test_backpressure_with_slow_processing():
    """Test backpressure behavior with slow event processing."""
    bus = EventBus(max_queue_size=10)
    processed = []
    
    async def slow_handler(payload: dict):
        await asyncio.sleep(0.1)  # Slow processing
        processed.append(payload["value"])
    
    bus.subscribe("test_event", slow_handler)
    
    # Start processing
    processing_task = asyncio.create_task(bus.start_processing())
    await asyncio.sleep(0.05)
    
    # Emit events rapidly
    successful = 0
    dropped = 0
    
    for i in range(20):
        result = await bus.emit("test_event", {"value": i}, timeout=0.01)
        if result:
            successful += 1
        else:
            dropped += 1
    
    # Should have dropped some due to slow processing
    assert dropped > 0
    assert successful >= 10  # At least the initial queue capacity
    
    # Wait for processing to complete
    # Since each event takes 0.1s and we have up to 20 events, 2s is plenty
    await asyncio.sleep(2)
    
    # Cleanup
    bus.stop()
    await processing_task
    
    # All successful events should be processed
    assert len(processed) == successful


@pytest.mark.asyncio
async def test_queue_utilization_percentage():
    """Test queue utilization percentage calculation."""
    bus = EventBus(max_queue_size=100)
    
    # Test various utilization levels
    test_cases = [
        (0, 0),    # Empty
        (25, 25),  # 25%
        (50, 50),  # 50%
        (75, 75),  # 75%
        (100, 100),  # Full
    ]
    
    for count, expected_percent in test_cases:
        # Reset queue
        bus.reset()
        
        # Fill to desired level
        for i in range(count):
            await bus.emit("test_event", {"value": i}, timeout=0.1)
        
        metrics = bus.get_queue_metrics()
        assert metrics["queue_utilization_percent"] == expected_percent


@pytest.mark.asyncio
async def test_dropped_events_counter_increments():
    """Test that dropped events counter increments correctly."""
    bus = EventBus(max_queue_size=3)
    
    # Fill queue
    for i in range(3):
        await bus.emit("test_event", {"value": i}, timeout=0.1)
    
    # Drop events one by one
    for i in range(5):
        await bus.emit("test_event", {"value": i + 100}, timeout=0.01)
        metrics = bus.get_queue_metrics()
        assert metrics["dropped_events"] == i + 1


@pytest.mark.asyncio
async def test_queue_full_count_increments():
    """Test that queue full count increments correctly."""
    bus = EventBus(max_queue_size=3)
    
    # Fill queue
    for i in range(3):
        await bus.emit("test_event", {"value": i}, timeout=0.1)
    
    # Try to emit more
    for i in range(5):
        await bus.emit("test_event", {"value": i + 100}, timeout=0.01)
    
    metrics = bus.get_queue_metrics()
    assert metrics["queue_full_count"] == 5


@pytest.mark.asyncio
async def test_reset_clears_metrics():
    """Test that reset() clears queue metrics."""
    bus = EventBus(max_queue_size=10)
    
    # Fill queue and drop some
    for i in range(10):
        await bus.emit("test_event", {"value": i}, timeout=0.1)
    
    for i in range(3):
        await bus.emit("test_event", {"value": i + 100}, timeout=0.01)
    
    # Reset
    bus.reset()
    
    # Metrics should be cleared
    metrics = bus.get_queue_metrics()
    assert metrics["queue_size"] == 0
    assert metrics["dropped_events"] == 0
    assert metrics["queue_full_count"] == 0
    assert metrics["queue_utilization_percent"] == 0


@pytest.mark.asyncio
async def test_configurable_queue_size():
    """Test that queue size is configurable via constructor."""
    # Small queue
    bus_small = EventBus(max_queue_size=5)
    assert bus_small._max_queue_size == 5
    
    # Large queue
    bus_large = EventBus(max_queue_size=50000)
    assert bus_large._max_queue_size == 50000
    
    # Default queue
    bus_default = EventBus()
    assert bus_default._max_queue_size == 10000


@pytest.mark.asyncio
async def test_emit_timeout_parameter():
    """Test that emit timeout parameter works correctly."""
    bus = EventBus(max_queue_size=2)
    
    # Fill queue
    await bus.emit("test_event", {"value": 1}, timeout=0.1)
    await bus.emit("test_event", {"value": 2}, timeout=0.1)
    
    # Test different timeout values
    # Short timeout (should fail fast)
    import time
    start = time.time()
    result = await bus.emit("test_event", {"value": 3}, timeout=0.05)
    elapsed = time.time() - start
    assert result is False
    assert elapsed < 0.2  # Should timeout quickly
    
    # Longer timeout (should still fail but take longer)
    start = time.time()
    result = await bus.emit("test_event", {"value": 4}, timeout=0.5)
    elapsed = time.time() - start
    assert result is False
    assert 0.4 < elapsed < 0.7  # Should timeout around 0.5s


@pytest.mark.asyncio
async def test_backpressure_with_multiple_event_types():
    """Test that backpressure works correctly with multiple event types."""
    bus = EventBus(max_queue_size=10)
    
    # Fill queue with mixed event types
    for i in range(5):
        await bus.emit("event_a", {"value": i}, timeout=0.1)
        await bus.emit("event_b", {"value": i}, timeout=0.1)
    
    # Queue should be full
    metrics = bus.get_queue_metrics()
    assert metrics["queue_size"] == 10
    
    # Try to emit more of each type
    result_a = await bus.emit("event_a", {"value": 999}, timeout=0.01)
    result_b = await bus.emit("event_b", {"value": 999}, timeout=0.01)
    
    assert result_a is False
    assert result_b is False
    
    metrics = bus.get_queue_metrics()
    assert metrics["dropped_events"] == 2


@pytest.mark.asyncio
async def test_queue_metrics_during_processing():
    """Test that queue metrics are accurate during active processing."""
    bus = EventBus(max_queue_size=20)
    processed = []
    
    async def handler(payload: dict):
        await asyncio.sleep(0.05)
        processed.append(payload["value"])
    
    bus.subscribe("test_event", handler)
    
    # Start processing
    processing_task = asyncio.create_task(bus.start_processing())
    await asyncio.sleep(0.05)
    
    # Emit events while processing
    for i in range(15):
        await bus.emit("test_event", {"value": i}, timeout=0.1)
    
    # Check metrics during processing
    await asyncio.sleep(0.1)
    metrics = bus.get_queue_metrics()
    
    # Queue size should be less than emitted (some processed)
    assert metrics["queue_size"] < 15
    assert metrics["dropped_events"] == 0
    
    # Wait for all to process
    await asyncio.sleep(1)
    
    # Cleanup
    bus.stop()
    await processing_task
    
    assert len(processed) == 15


@pytest.mark.asyncio
async def test_emit_return_value_indicates_success():
    """Test that emit return value correctly indicates success/failure."""
    bus = EventBus(max_queue_size=3)
    
    # Successful emits
    assert await bus.emit("test_event", {"value": 1}, timeout=0.1) is True
    assert await bus.emit("test_event", {"value": 2}, timeout=0.1) is True
    assert await bus.emit("test_event", {"value": 3}, timeout=0.1) is True
    
    # Failed emit (queue full)
    assert await bus.emit("test_event", {"value": 4}, timeout=0.01) is False


@pytest.mark.asyncio
async def test_logging_on_queue_full(caplog):
    """Test that queue full events are logged with appropriate warnings."""
    bus = EventBus(max_queue_size=2)
    
    # Fill queue
    await bus.emit("test_event", {"value": 1}, timeout=0.1)
    await bus.emit("test_event", {"value": 2}, timeout=0.1)
    
    # Try to emit more (should log warning)
    with caplog.at_level("WARNING"):
        await bus.emit("test_event", {"value": 3}, timeout=0.01)
    
    # Check that warning was logged
    log_messages = [record.message for record in caplog.records]
    assert any("queue full" in msg.lower() and "dropped event" in msg.lower() for msg in log_messages)


@pytest.mark.asyncio
async def test_queue_size_in_debug_logs(caplog):
    """Test that queue size is included in debug logs."""
    bus = EventBus(max_queue_size=10)
    
    with caplog.at_level("DEBUG"):
        await bus.emit("test_event", {"value": 1}, timeout=0.1)
    
    # Check that queue size is logged
    log_messages = [record.message for record in caplog.records]
    assert any("queue_size=" in msg for msg in log_messages)
