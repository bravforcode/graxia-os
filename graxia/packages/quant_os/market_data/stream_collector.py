"""Delta-stream tick collector core (pure, MT5-free).

Fetches ticks >= last_seen_msc per symbol, deduplicates with a bounded
composite-key window (never a full clear — that reintroduces duplicates at
the overlap boundary), and loops until caught up so no tick is dropped
during high-volatility bursts. Connection recovery is owned by the caller
(the daemon loop), not here.
"""

from __future__ import annotations

from collections.abc import Callable

TickDict = dict


class StreamCollector:
    def __init__(
        self,
        symbols: list[str],
        fetch: Callable[[str, int], list[TickDict]],
        *,
        catch_up_cap: int = 10,
    ):
        self._fetch = fetch
        self._catch_up_cap = catch_up_cap
        self._cursor: dict[str, int] = {s: 0 for s in symbols}
        # Bounded window: keys with time_msc >= the current cycle's from_msc.
        self._seen: set[tuple] = set()
        self._window_from: dict[str, int] = {s: 0 for s in symbols}

    def cursor(self, symbol: str) -> int:
        return self._cursor[symbol]

    def poll(self, symbol: str) -> list[TickDict]:
        from_msc = self._cursor[symbol]
        self._window_from[symbol] = from_msc
        new_ticks: list[TickDict] = []
        max_msc = from_msc
        for _ in range(self._catch_up_cap):
            batch = self._fetch(symbol, from_msc)
            if not batch:
                break
            batch_max = from_msc
            added = 0
            for t in batch:
                key = (symbol, t["time_msc"], t["bid"], t["ask"], t["last"], t["volume"])
                if key not in self._seen:
                    self._seen.add(key)
                    new_ticks.append(t)
                    added += 1
                if t["time_msc"] > batch_max:
                    batch_max = t["time_msc"]
            self._prune(symbol, from_msc)
            if added == 0 or batch_max <= from_msc:
                break  # nothing new (boundary repeats only) or no progress
            from_msc = batch_max
            max_msc = batch_max
        self._cursor[symbol] = max_msc
        return new_ticks

    def _prune(self, symbol: str, floor_msc: int) -> None:
        """Drop window keys strictly below floor_msc — they can never recur
        because the cursor is monotonic and fetch windows only overlap at the
        boundary point. Runs lazily to keep memory bounded."""
        if len(self._seen) < 100_000:
            return
        self._seen = {k for k in self._seen if k[0] != symbol or k[1] >= floor_msc}
