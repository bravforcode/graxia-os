"""Phase BE-P8 — Shadow telemetry for campaign metrics."""

import time
from dataclasses import dataclass


@dataclass
class ShadowMetrics:
    signal_count: int = 0
    rejection_count: int = 0
    event_blocked_count: int = 0
    health_blocked_count: int = 0
    stale_feed_count: int = 0
    spread_p50: float = 0.0
    spread_p90: float = 0.0
    max_spread: float = 0.0
    decision_latency_ms: float = 0.0
    hypothetical_pnl: float = 0.0
    session_uptime_s: float = 0.0
    incident_count: int = 0
    contract_change_count: int = 0
    heartbeat_count: int = 0


class ShadowTelemetry:
    """Collect shadow campaign telemetry."""

    def __init__(self):
        self._metrics = ShadowMetrics()
        self._spreads: list[float] = []
        self._latencies_ms: list[float] = []
        self._start_time: float = 0

    def start(self) -> None:
        self._start_time = time.monotonic_ns()

    def record_signal(self) -> None:
        self._metrics.signal_count += 1

    def record_rejection(self, reason: str) -> None:
        self._metrics.rejection_count += 1

    def record_event_blocked(self) -> None:
        self._metrics.event_blocked_count += 1

    def record_health_blocked(self) -> None:
        self._metrics.health_blocked_count += 1

    def record_stale_feed(self) -> None:
        self._metrics.stale_feed_count += 1

    def record_spread(self, spread: float) -> None:
        self._spreads.append(spread)

    def record_latency(self, latency_ms: float) -> None:
        self._latencies_ms.append(latency_ms)

    def record_hypothetical_pnl(self, pnl: float) -> None:
        self._metrics.hypothetical_pnl += pnl

    def record_incident(self) -> None:
        self._metrics.incident_count += 1

    def record_contract_change(self) -> None:
        self._metrics.contract_change_count += 1

    def record_heartbeat(self) -> None:
        self._metrics.heartbeat_count += 1

    def get_metrics(self) -> ShadowMetrics:
        if self._start_time > 0:
            self._metrics.session_uptime_s = (time.monotonic_ns() - self._start_time) / 1e9

        if self._spreads:
            s = sorted(self._spreads)
            n = len(s)
            self._metrics.spread_p50 = s[n // 2]
            self._metrics.spread_p90 = s[int(n * 0.9)]
            self._metrics.max_spread = s[-1]

        if self._latencies_ms:
            self._metrics.decision_latency_ms = sum(self._latencies_ms) / len(self._latencies_ms)

        return self._metrics
