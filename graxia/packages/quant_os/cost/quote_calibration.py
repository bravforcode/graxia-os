"""Phase BE-P4 — Quote-based calibration from tick data."""
from dataclasses import dataclass


@dataclass
class QuoteCalibration:
    """Calibrated from real broker quotes."""
    spread_p50: float = 0.0
    spread_p90: float = 0.0
    spread_p99: float = 0.0
    max_spread: float = 0.0
    quote_move_p50: float = 0.0
    quote_move_p90: float = 0.0
    pipeline_latency_ms: float = 0.0
    staleness_threshold_ms: float = 5000.0
    sample_count: int = 0
    evidence_level: str = "QUOTE_OBSERVED"

    def is_sufficient(self, min_samples: int = 100) -> bool:
        return self.sample_count >= min_samples


class QuoteCalibrator:
    """Calibrate cost model from quote observations."""

    def __init__(self):
        self._spreads: list[float] = []
        self._quote_moves: list[float] = []
        self._latencies_ms: list[float] = []
        self._last_quote_time_ms: int = 0

    def observe_spread(self, spread: float) -> None:
        self._spreads.append(spread)

    def observe_quote_move(self, move: float) -> None:
        self._quote_moves.append(move)

    def observe_latency(self, latency_ms: float) -> None:
        self._latencies_ms.append(latency_ms)

    def calibrate(self) -> QuoteCalibration:
        """Compute calibration from observations."""
        def percentile(data: list[float], p: float) -> float:
            if not data:
                return 0.0
            s = sorted(data)
            return s[int(len(s) * p)]

        return QuoteCalibration(
            spread_p50=percentile(self._spreads, 0.5),
            spread_p90=percentile(self._spreads, 0.9),
            spread_p99=percentile(self._spreads, 0.99),
            max_spread=max(self._spreads) if self._spreads else 0.0,
            quote_move_p50=percentile(self._quote_moves, 0.5),
            quote_move_p90=percentile(self._quote_moves, 0.9),
            pipeline_latency_ms=sum(self._latencies_ms) / max(len(self._latencies_ms), 1),
            sample_count=len(self._spreads),
            evidence_level="QUOTE_OBSERVED",
        )
