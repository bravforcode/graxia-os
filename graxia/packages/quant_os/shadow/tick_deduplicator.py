"""Tick deduplicator — prevents same tick from being processed twice.

Uses tick time_msc as unique key. Handles overlapping query windows.
"""
from typing import Optional


class TickDeduplicator:
    """Deduplicates ticks across overlapping query windows.

    Uses time_msc as unique key since it has millisecond resolution.
    """

    def __init__(self):
        self._seen: set[int] = set()
        self._max_size: int = 100000

    def is_duplicate(self, tick: dict) -> bool:
        """Check if tick was already processed."""
        key = tick.get("time_msc", tick.get("time", 0) * 1000)
        return key in self._seen

    def record(self, tick: dict) -> None:
        """Record tick as seen."""
        key = tick.get("time_msc", tick.get("time", 0) * 1000)
        self._seen.add(key)
        # Prevent unbounded growth
        if len(self._seen) > self._max_size:
            # Keep most recent half
            sorted_keys = sorted(self._seen)
            self._seen = set(sorted_keys[len(sorted_keys) // 2:])

    def deduplicate(self, ticks: list[dict]) -> tuple[list[dict], int]:
        """Deduplicate a batch of ticks. Returns (unique_ticks, duplicate_count)."""
        unique = []
        dupes = 0
        for t in ticks:
            if self.is_duplicate(t):
                dupes += 1
            else:
                self.record(t)
                unique.append(t)
        return unique, dupes

    def reset(self) -> None:
        """Clear deduplication state."""
        self._seen.clear()
