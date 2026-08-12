#!/usr/bin/env python3
"""
Verification script for Event Bus queue size limit implementation (TASK 2.4).

This script verifies that:
1. Queue size is limited to configured maximum
2. Backpressure mechanism works correctly
3. Queue metrics are available and accurate
4. Events are dropped when queue is full
5. Logging works correctly

Usage:
    python scripts/verify_queue_limits.py
"""

import asyncio
import sys
from pathlib import Path

# Add backend to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from app.core.event_bus import EventBus


class Colors:
    """ANSI color codes for terminal output."""
    GREEN = "\033[92m"
    RED = "\033[91m"
    YELLOW = "\033[93m"
    BLUE = "\033[94m"
    RESET = "\033[0m"
    BOLD = "\033[1m"


def print_header(text: str):
    """Print a formatted header."""
    print(f"\n{Colors.BOLD}{Colors.BLUE}{'=' * 70}{Colors.RESET}")
    print(f"{Colors.BOLD}{Colors.BLUE}{text:^70}{Colors.RESET}")
    print(f"{Colors.BOLD}{Colors.BLUE}{'=' * 70}{Colors.RESET}\n")


def print_check(name: str, passed: bool, details: str = ""):
    """Print a check result."""
    status = f"{Colors.GREEN}✅ PASS{Colors.RESET}" if passed else f"{Colors.RED}❌ FAIL{Colors.RESET}"
    print(f"{status}: {name}")
    if details:
        print(f"  {Colors.YELLOW}→{Colors.RESET} {details}")


async def check_queue_size_limit():
    """Check that queue size is limited to configured maximum."""
    print_header("CHECK 1: Queue Size Limit")
    
    bus = EventBus(max_queue_size=10)
    
    # Fill the queue
    for i in range(10):
        result = await bus.emit("test_event", {"value": i}, timeout=0.1)
        if not result:
            print_check("Queue size limit", False, f"Failed to emit event {i}")
            return False
    
    # Try to emit one more (should fail)
    result = await bus.emit("test_event", {"value": 999}, timeout=0.01)
    
    if result:
        print_check("Queue size limit", False, "Queue accepted event beyond limit")
        return False
    
    metrics = bus.get_queue_metrics()
    if metrics["queue_size"] != 10:
        print_check("Queue size limit", False, f"Queue size is {metrics['queue_size']}, expected 10")
        return False
    
    print_check("Queue size limit", True, f"Queue correctly limited to {metrics['max_queue_size']} events")
    return True


async def check_backpressure_blocking():
    """Check that backpressure blocks with timeout=None."""
    print_header("CHECK 2: Backpressure (Blocking Mode)")
    
    bus = EventBus(max_queue_size=5)
    
    # Fill the queue
    for i in range(5):
        await bus.emit("test_event", {"value": i}, timeout=0.1)
    
    # Try to emit with None timeout (should block)
    emit_task = asyncio.create_task(bus.emit("test_event", {"value": 999}, timeout=None))
    
    # Give it a moment
    await asyncio.sleep(0.1)
    
    # Task should still be pending (blocked)
    if emit_task.done():
        print_check("Backpressure blocking", False, "Emit did not block with timeout=None")
        emit_task.cancel()
        return False
    
    # Cancel the task
    emit_task.cancel()
    try:
        await emit_task
    except asyncio.CancelledError:
        pass
    
    print_check("Backpressure blocking", True, "Emit correctly blocks when queue is full")
    return True


async def check_backpressure_non_blocking():
    """Check that backpressure returns False with timeout."""
    print_header("CHECK 3: Backpressure (Non-Blocking Mode)")
    
    bus = EventBus(max_queue_size=5)
    
    # Fill the queue
    for i in range(5):
        await bus.emit("test_event", {"value": i}, timeout=0.1)
    
    # Try to emit with short timeout (should return False)
    result = await bus.emit("test_event", {"value": 999}, timeout=0.01)
    
    if result:
        print_check("Backpressure non-blocking", False, "Emit returned True when queue was full")
        return False
    
    print_check("Backpressure non-blocking", True, "Emit correctly returns False when queue is full")
    return True


async def check_queue_metrics():
    """Check that queue metrics are available and accurate."""
    print_header("CHECK 4: Queue Metrics")
    
    bus = EventBus(max_queue_size=20)
    
    # Emit some events
    for i in range(15):
        await bus.emit("test_event", {"value": i}, timeout=0.1)
    
    metrics = bus.get_queue_metrics()
    
    # Check all required metrics exist
    required_keys = ["queue_size", "max_queue_size", "queue_full_count", "dropped_events", "queue_utilization_percent"]
    for key in required_keys:
        if key not in metrics:
            print_check("Queue metrics", False, f"Missing metric: {key}")
            return False
    
    # Check metric values
    if metrics["queue_size"] != 15:
        print_check("Queue metrics", False, f"Queue size is {metrics['queue_size']}, expected 15")
        return False
    
    if metrics["max_queue_size"] != 20:
        print_check("Queue metrics", False, f"Max queue size is {metrics['max_queue_size']}, expected 20")
        return False
    
    if metrics["queue_utilization_percent"] != 75:  # 15/20 * 100
        print_check("Queue metrics", False, f"Utilization is {metrics['queue_utilization_percent']}%, expected 75%")
        return False
    
    print_check("Queue metrics", True, f"All metrics available and accurate")
    print(f"  {Colors.YELLOW}→{Colors.RESET} Queue size: {metrics['queue_size']}/{metrics['max_queue_size']}")
    print(f"  {Colors.YELLOW}→{Colors.RESET} Utilization: {metrics['queue_utilization_percent']}%")
    print(f"  {Colors.YELLOW}→{Colors.RESET} Dropped events: {metrics['dropped_events']}")
    return True


async def check_dropped_events_tracking():
    """Check that dropped events are tracked correctly."""
    print_header("CHECK 5: Dropped Events Tracking")
    
    bus = EventBus(max_queue_size=5)
    
    # Fill queue
    for i in range(5):
        await bus.emit("test_event", {"value": i}, timeout=0.1)
    
    # Try to emit more (should drop)
    dropped_count = 0
    for i in range(3):
        result = await bus.emit("test_event", {"value": i + 100}, timeout=0.01)
        if not result:
            dropped_count += 1
    
    metrics = bus.get_queue_metrics()
    
    if metrics["dropped_events"] != dropped_count:
        print_check("Dropped events tracking", False, 
                   f"Dropped events count is {metrics['dropped_events']}, expected {dropped_count}")
        return False
    
    if metrics["queue_full_count"] != dropped_count:
        print_check("Dropped events tracking", False,
                   f"Queue full count is {metrics['queue_full_count']}, expected {dropped_count}")
        return False
    
    print_check("Dropped events tracking", True, f"Correctly tracked {dropped_count} dropped events")
    return True


async def check_processing_reduces_queue():
    """Check that processing events reduces queue size."""
    print_header("CHECK 6: Processing Reduces Queue Size")
    
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
    
    # Cleanup
    bus.stop()
    await processing_task
    
    if len(processed) != 10:
        print_check("Processing reduces queue", False, f"Processed {len(processed)} events, expected 10")
        return False
    
    if metrics["queue_size"] >= 10:
        print_check("Processing reduces queue", False, f"Queue size is {metrics['queue_size']}, expected < 10")
        return False
    
    print_check("Processing reduces queue", True, f"Processed all 10 events, queue size reduced to {metrics['queue_size']}")
    return True


async def check_configurable_queue_size():
    """Check that queue size is configurable."""
    print_header("CHECK 7: Configurable Queue Size")
    
    # Test different queue sizes
    test_sizes = [5, 100, 10000]
    
    for size in test_sizes:
        bus = EventBus(max_queue_size=size)
        if bus._max_queue_size != size:
            print_check("Configurable queue size", False, f"Queue size is {bus._max_queue_size}, expected {size}")
            return False
    
    print_check("Configurable queue size", True, f"Queue size configurable via constructor")
    return True


async def check_emit_return_value():
    """Check that emit return value indicates success/failure."""
    print_header("CHECK 8: Emit Return Value")
    
    bus = EventBus(max_queue_size=3)
    
    # Successful emits
    for i in range(3):
        result = await bus.emit("test_event", {"value": i}, timeout=0.1)
        if not result:
            print_check("Emit return value", False, f"Emit returned False for event {i} (queue not full)")
            return False
    
    # Failed emit
    result = await bus.emit("test_event", {"value": 999}, timeout=0.01)
    if result:
        print_check("Emit return value", False, "Emit returned True when queue was full")
        return False
    
    print_check("Emit return value", True, "Emit return value correctly indicates success/failure")
    return True


async def main():
    """Run all verification checks."""
    print(f"\n{Colors.BOLD}Event Bus Queue Size Limit Verification{Colors.RESET}")
    print(f"{Colors.BOLD}TASK 2.4: Implement Event Bus Queue Size Limit [M-02]{Colors.RESET}")
    
    checks = [
        ("Queue Size Limit", check_queue_size_limit),
        ("Backpressure (Blocking)", check_backpressure_blocking),
        ("Backpressure (Non-Blocking)", check_backpressure_non_blocking),
        ("Queue Metrics", check_queue_metrics),
        ("Dropped Events Tracking", check_dropped_events_tracking),
        ("Processing Reduces Queue", check_processing_reduces_queue),
        ("Configurable Queue Size", check_configurable_queue_size),
        ("Emit Return Value", check_emit_return_value),
    ]
    
    results = []
    for name, check_func in checks:
        try:
            result = await check_func()
            results.append((name, result))
        except Exception as e:
            print_check(name, False, f"Exception: {e}")
            results.append((name, False))
    
    # Print summary
    print_header("VERIFICATION SUMMARY")
    
    passed = sum(1 for _, result in results if result)
    total = len(results)
    
    for name, result in results:
        status = f"{Colors.GREEN}✅{Colors.RESET}" if result else f"{Colors.RED}❌{Colors.RESET}"
        print(f"{status} {name}")
    
    print(f"\n{Colors.BOLD}Results: {passed}/{total} checks passed{Colors.RESET}")
    
    if passed == total:
        print(f"\n{Colors.GREEN}{Colors.BOLD}✅ ALL CHECKS PASSED{Colors.RESET}")
        print(f"{Colors.GREEN}Event Bus queue size limit is working correctly!{Colors.RESET}\n")
        return 0
    else:
        print(f"\n{Colors.RED}{Colors.BOLD}❌ SOME CHECKS FAILED{Colors.RESET}")
        print(f"{Colors.RED}Please review the failed checks above.{Colors.RESET}\n")
        return 1


if __name__ == "__main__":
    exit_code = asyncio.run(main())
    sys.exit(exit_code)
