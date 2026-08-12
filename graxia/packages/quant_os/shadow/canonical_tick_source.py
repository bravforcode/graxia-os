"""Canonical tick source — single entry point for all tick data.

Uses copy_ticks_range with UTC-aware input only.
No symbol_info_tick.time, no MT5 bar timestamps, no copy_ticks_from.
"""

import hashlib
import json
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime, timedelta

from graxia.packages.quant_os.shadow.canonical_bar_builder import CanonicalBarBuilder
from graxia.packages.quant_os.shadow.canonical_time_authority import CanonicalTimeAuthority
from graxia.packages.quant_os.shadow.tick_deduplicator import TickDeduplicator
from graxia.packages.quant_os.shadow.tick_watermark import TickWatermark
from graxia.packages.quant_os.shadow.tick_window_fetcher import TickWindowFetcher


@dataclass
class CanonicalTickPolicy:
    """Configuration for canonical tick source."""

    query_interval_seconds: int = 60
    trailing_overlap_seconds: int = 300
    safety_lag_seconds: int = 2
    bar_finalization_delay_seconds: int = 120
    max_data_age_seconds: int = 15
    reject_if_no_canonical_tick: bool = True
    reject_if_tick_outside_requested_window: bool = True
    reject_if_timestamp_in_future: bool = True
    fail_closed: bool = True


@dataclass
class CanonicalTickBatch:
    """Result of one canonical tick fetch cycle."""

    trusted_system_utc: str = ""
    request_from_utc: str = ""
    request_to_utc: str = ""
    request_window_hash: str = ""
    response_received_at_utc: str = ""
    batch_hash: str = ""
    first_tick_utc: str = ""
    last_tick_utc: str = ""
    canonical_data_age_ms: float = 0.0
    raw_tick_count: int = 0
    deduplicated_tick_count: int = 0
    late_tick_count: int = 0
    outside_window_tick_count: int = 0
    bar_builder_version: str = ""
    time_authority: str = "CANONICAL_TICK_UTC"
    symbol_info_tick_time_used: bool = False
    mt5_bar_time_used: bool = False
    # Ticks
    canonical_ticks: list[dict] = field(default_factory=list)
    rejected_reason: str = ""
    verdict: str = "PENDING"

    def to_dict(self) -> dict:
        d = asdict(self)
        d.pop("canonical_ticks", None)  # too large for metadata
        return d


class CanonicalTickSource:
    """Single entry point for all tick data in shadow system.

    Architecture:
    - trusted_system_utc for event/session/health
    - copy_ticks_range UTC-aware for market ticks
    - canonical bars built from ticks
    - No symbol_info_tick.time or MT5 bar time in signal path
    """

    def __init__(
        self,
        mt5_connection,
        symbol: str,
        policy: CanonicalTickPolicy | None = None,
    ):
        self._symbol = symbol
        self._policy = policy or CanonicalTickPolicy()
        self._time_auth = CanonicalTimeAuthority()
        self._fetcher = TickWindowFetcher(mt5_connection)
        self._dedup = TickDeduplicator()
        self._watermark = TickWatermark(overlap_seconds=self._policy.trailing_overlap_seconds)
        self._bar_builder = CanonicalBarBuilder(
            symbol=symbol,
            bar_finalization_delay_seconds=self._policy.bar_finalization_delay_seconds,
        )
        self._cycle_count: int = 0

    def fetch_cycle(self) -> CanonicalTickBatch:
        """Execute one canonical tick fetch cycle."""
        self._cycle_count += 1
        system_utc = self._time_auth.trusted_system_utc()
        received_at = datetime.now(UTC)

        batch = CanonicalTickBatch(
            trusted_system_utc=system_utc.isoformat(),
            response_received_at_utc=received_at.isoformat(),
            bar_builder_version=self._bar_builder.version(),
        )

        # Calculate query window
        q_from = self._watermark.query_start(system_utc, self._policy.safety_lag_seconds)
        q_to = self._watermark.query_end(system_utc, self._policy.safety_lag_seconds)
        batch.request_from_utc = q_from.isoformat()
        batch.request_to_utc = q_to.isoformat()

        # Fetch ticks (UTC-aware only)
        fetch_result = self._fetcher.fetch_ticks(self._symbol, q_from, q_to)
        batch.request_window_hash = fetch_result["request_window_hash"]

        if fetch_result["error"]:
            batch.rejected_reason = fetch_result["error"]
            batch.verdict = "REJECTED_FETCH_ERROR"
            return batch

        raw_ticks = fetch_result["ticks"]
        batch.raw_tick_count = len(raw_ticks)

        if not raw_ticks and self._policy.reject_if_no_canonical_tick:
            batch.rejected_reason = "NO_CANONICAL_TICKS"
            batch.verdict = "REJECTED_NO_TICKS"
            return batch

        # Validate window
        if self._policy.reject_if_tick_outside_requested_window:
            if fetch_result["outside_count"] > 0:
                batch.outside_window_tick_count = fetch_result["outside_count"]
                batch.rejected_reason = f"TICK_OUTSIDE_WINDOW: {fetch_result['outside_count']} ticks"
                batch.verdict = "REJECTED_OUTSIDE_WINDOW"
                return batch

        # Validate no future timestamps
        if self._policy.reject_if_timestamp_in_future:
            for t in raw_ticks:
                tick_dt = datetime.fromtimestamp(t["time"], tz=UTC)
                if tick_dt > system_utc + timedelta(seconds=5):
                    batch.rejected_reason = f"FUTURE_TIMESTAMP: {tick_dt.isoformat()}"
                    batch.verdict = "REJECTED_FUTURE_TICK"
                    return batch

        # Deduplicate
        unique_ticks, dupe_count = self._dedup.deduplicate(raw_ticks)
        batch.deduplicated_tick_count = len(unique_ticks)
        batch.late_tick_count = dupe_count

        # Update watermark
        for t in unique_ticks:
            tick_dt = datetime.fromtimestamp(t["time"], tz=UTC)
            self._watermark.update(tick_dt)

        # Build bars
        for t in unique_ticks:
            self._bar_builder.add_tick(t)
        self._bar_builder.finalize_bars(system_utc)

        # Compute batch hash
        tick_times = [t["time"] for t in unique_ticks]
        batch.batch_hash = hashlib.sha256(json.dumps(tick_times, sort_keys=True).encode()).hexdigest()[:16]

        # Set metadata
        if unique_ticks:
            first = unique_ticks[0]
            last = unique_ticks[-1]
            batch.first_tick_utc = datetime.fromtimestamp(first["time"], tz=UTC).isoformat()
            batch.last_tick_utc = datetime.fromtimestamp(last["time"], tz=UTC).isoformat()

        batch.canonical_data_age_ms = self._watermark.data_age_ms(system_utc)
        batch.canonical_ticks = unique_ticks
        batch.verdict = "PASS"

        return batch

    def get_finalized_m1_bars(self, count: int = 3) -> list[dict]:
        """Get finalized M1 bars from canonical builder."""
        return [b.to_dict() for b in self._bar_builder.get_finalized_m1_bars(count)]

    def get_finalized_h1_bars(self, count: int = 3) -> list[dict]:
        """Get finalized H1 bars from canonical builder."""
        return [b.to_dict() for b in self._bar_builder.get_finalized_h1_bars(count)]

    @property
    def watermark(self) -> datetime | None:
        return self._watermark.watermark

    @property
    def time_authority(self) -> CanonicalTimeAuthority:
        return self._time_auth
