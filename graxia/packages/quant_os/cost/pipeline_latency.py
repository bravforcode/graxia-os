"""Phase BE-P4 — Pipeline latency measurement."""
import time
from dataclasses import dataclass


@dataclass
class LatencySample:
    tick_received_ns: int
    signal_finalized_ns: int
    order_intent_persisted_ns: int

    @property
    def tick_to_signal_ms(self) -> float:
        return (self.signal_finalized_ns - self.tick_received_ns) / 1_000_000

    @property
    def signal_to_persist_ms(self) -> float:
        return (self.order_intent_persisted_ns - self.signal_finalized_ns) / 1_000_000

    @property
    def total_pipeline_ms(self) -> float:
        return (self.order_intent_persisted_ns - self.tick_received_ns) / 1_000_000


class PipelineLatencyTracker:
    """Track pipeline latency: tick → signal → persist."""

    def __init__(self):
        self._samples: list[LatencySample] = []
        self._current_tick_ns: int = 0
        self._current_signal_ns: int = 0

    def on_tick_received(self) -> None:
        self._current_tick_ns = time.monotonic_ns()

    def on_signal_finalized(self) -> None:
        self._current_signal_ns = time.monotonic_ns()

    def on_order_persisted(self) -> None:
        if self._current_tick_ns > 0 and self._current_signal_ns > 0:
            sample = LatencySample(
                tick_received_ns=self._current_tick_ns,
                signal_finalized_ns=self._current_signal_ns,
                order_intent_persisted_ns=time.monotonic_ns(),
            )
            self._samples.append(sample)
        self._current_tick_ns = 0
        self._current_signal_ns = 0

    def get_stats(self) -> dict:
        if not self._samples:
            return {"count": 0, "avg_total_ms": 0, "p90_total_ms": 0}

        totals = [s.total_pipeline_ms for s in self._samples]
        sorted_totals = sorted(totals)
        n = len(sorted_totals)

        return {
            "count": n,
            "avg_total_ms": sum(totals) / n,
            "p90_total_ms": sorted_totals[int(n * 0.9)],
            "max_total_ms": sorted_totals[-1],
        }
