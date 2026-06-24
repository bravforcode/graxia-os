"""
Canonical UTC Tick Authority.

Sole timestamp authority for G3 execution preflight.
Uses copy_ticks_range() with UTC-aware datetimes (as MT5 docs specifies).
symbol_info_tick() is LIVE_PRICE_INPUT_ONLY — never use its .time for freshness.

Data flow:
  copy_ticks_range(UTC_from, UTC_to) -> canonical UTC tick <- SOURCE OF TRUTH
  symbol_info_tick() -> bid/ask price input <- PRICE INPUT ONLY
  local_received_at = datetime.now(timezone.utc) <- LOCAL RECEIPT CLOCK
"""
import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone, timedelta
from typing import Optional

logger = logging.getLogger(__name__)

    # -- Configuration --
CANONICAL_TICK_LOOKBACK_SECONDS = 60  # Look back up to 60s for latest tick
CANONICAL_TICK_MAX_AGE_MS = 5000      # Max 5s age for fresh tick
MAX_QUOTE_DIVERGENCE_TICKS = 5        # Max 5 ticks divergence native vs canonical
MAX_QUOTE_SPREAD_DIVERGENCE_TICKS = 10  # Max 10 ticks spread divergence

# -- Status labels --
TIME_SOURCE_CONSISTENT = "TIME_SOURCE_CONSISTENT"
TIME_SOURCE_INCONSISTENT = "TIME_SOURCE_INCONSISTENT"
CANONICAL_TICK_STALE = "CANONICAL_TICK_STALE"
CANONICAL_TICK_MISSING = "CANONICAL_TICK_MISSING"
CANONICAL_TICK_OUTSIDE_WINDOW = "CANONICAL_TICK_OUTSIDE_WINDOW"
CANONICAL_TICK_FUTURE = "CANONICAL_TICK_FUTURE"
CANONICAL_TICK_INVALID_PRICE = "CANONICAL_TICK_INVALID_PRICE"
LIVE_PRICE_INPUT_WITH_UNTRUSTED_NATIVE_TIMESTAMP = "LIVE_PRICE_INPUT_WITH_UNTRUSTED_NATIVE_TIMESTAMP"
QUOTE_SOURCE_COHERENT = "QUOTE_SOURCE_COHERENT"
QUOTE_SOURCE_DIVERGENT = "QUOTE_SOURCE_DIVERGENT"
COHERENT_CANONICAL_EXECUTION_SNAPSHOT = "COHERENT_CANONICAL_EXECUTION_SNAPSHOT"
EXECUTION_QUOTE_AVAILABLE = "EXECUTION_QUOTE_AVAILABLE"
EXECUTION_QUOTE_UNAVAILABLE = "EXECUTION_QUOTE_UNAVAILABLE"
CANONICAL_TICK_AUDIT_PASS = "CANONICAL_TICK_AUDIT_PASS"
CANONICAL_TICK_AUDIT_FAIL = "CANONICAL_TICK_AUDIT_FAIL"


@dataclass
class CanonicalTickEvidence:
    """Evidence from one canonical UTC tick query."""
    # Query window
    request_started_at_utc: Optional[str] = None
    request_finished_at_utc: Optional[str] = None
    canonical_tick_window_from_utc: Optional[str] = None
    canonical_tick_window_to_utc: Optional[str] = None
    query_result_count: int = 0

    # Canonical tick data (from copy_ticks_range)
    canonical_tick_time_utc: Optional[str] = None
    canonical_tick_time_msc: Optional[int] = None
    canonical_bid: Optional[float] = None
    canonical_ask: Optional[float] = None
    canonical_last: Optional[float] = None
    canonical_volume: Optional[float] = None
    canonical_flags: Optional[int] = None

    # Freshness
    canonical_tick_age_ms: Optional[float] = None
    time_authority_status: str = TIME_SOURCE_INCONSISTENT

    # Native quote (symbol_info_tick -- price only, timestamp untrusted)
    native_quote_bid: Optional[float] = None
    native_quote_ask: Optional[float] = None
    native_quote_time: Optional[int] = None
    native_quote_timestamp_status: str = "UNTRUSTED_NATIVE_TIMESTAMP"

    # Price divergence
    quote_price_divergence_ticks: Optional[float] = None
    quote_price_divergence_passed: bool = False
    bid_divergence_ticks: Optional[float] = None
    ask_divergence_ticks: Optional[float] = None
    canonical_spread_ticks: Optional[float] = None
    native_spread_ticks: Optional[float] = None
    spread_divergence_ticks: Optional[float] = None
    quote_coherence_status: str = QUOTE_SOURCE_DIVERGENT

    # Source labels
    quote_source: str = LIVE_PRICE_INPUT_WITH_UNTRUSTED_NATIVE_TIMESTAMP
    source_error: Optional[str] = None

    # Local receipt
    local_received_at_utc: Optional[str] = None

    # Execution quote availability (G3.2.4)
    execution_quote_status: str = EXECUTION_QUOTE_UNAVAILABLE
    native_bid_valid: bool = False
    native_ask_valid: bool = False
    canonical_tick_fresh: bool = False
    terminal_connected: bool = False
    position_count: int = -1
    order_count: int = -1
    feature_gate_off: bool = False
    kill_switch_on: bool = False

    # Canonical tick audit (G3.2.4)
    canonical_audit_status: str = CANONICAL_TICK_AUDIT_FAIL
    audit_tick_valid: bool = False
    audit_timestamp_inside_window: bool = False
    audit_age_within_bounds: bool = False
    audit_no_future_tick: bool = False


def query_canonical_utc_tick(mt5_module, symbol: str) -> CanonicalTickEvidence:
    """
    Query canonical UTC tick using copy_ticks_range().

    Returns CanonicalTickEvidence. Never raises.
    time_authority_status = TIME_SOURCE_CONSISTENT only when all checks pass.
    """
    evidence = CanonicalTickEvidence()
    evidence.local_received_at_utc = datetime.now(timezone.utc).isoformat()
    evidence.request_started_at_utc = datetime.now(timezone.utc).isoformat()

    if mt5_module is None:
        evidence.source_error = "No MT5 connection"
        evidence.time_authority_status = TIME_SOURCE_INCONSISTENT
        return evidence

    try:
        # Build UTC-aware query window
        now_utc = datetime.now(timezone.utc)
        window_from = now_utc - timedelta(seconds=CANONICAL_TICK_LOOKBACK_SECONDS)
        window_to = now_utc

        evidence.canonical_tick_window_from_utc = window_from.isoformat()
        evidence.canonical_tick_window_to_utc = window_to.isoformat()

        # Use COPY_TICKS_INFO to get ticks with bid/ask changes only
        # (COPY_TICKS_ALL may include flags-only ticks with bid=0, ask=0)
        ticks = mt5_module.copy_ticks_range(symbol, window_from, window_to, mt5_module.COPY_TICKS_INFO)
        evidence.request_finished_at_utc = datetime.now(timezone.utc).isoformat()

        if ticks is None or len(ticks) == 0:
            evidence.query_result_count = 0
            evidence.time_authority_status = CANONICAL_TICK_MISSING
            evidence.source_error = f"copy_ticks_range returned {len(ticks) if ticks is not None else 0} ticks"
            return evidence

        evidence.query_result_count = len(ticks)

        # Scan from LAST tick backward to find the latest tick with VALID bid/ask
        # (bid > 0, ask > 0, ask >= bid). Do NOT blindly use ticks[-1].
        selected_tick = None
        for i in range(len(ticks) - 1, -1, -1):
            row = ticks[i]
            tick_bid = float(row[2]) if len(row) > 2 else 0
            tick_ask = float(row[3]) if len(row) > 3 else 0
            if tick_bid > 0 and tick_ask > 0 and tick_ask >= tick_bid:
                selected_tick = row
                break

        if selected_tick is None:
            evidence.query_result_count = len(ticks)
            evidence.time_authority_status = CANONICAL_TICK_INVALID_PRICE
            evidence.source_error = "No valid tick (bid>0, ask>0) found in window"
            return evidence

        # Use the selected valid tick
        tick_time = int(selected_tick[0])
        tick_msc = int(selected_tick[1]) if len(selected_tick) > 1 else 0

        evidence.canonical_tick_time_utc = datetime.fromtimestamp(tick_time, tz=timezone.utc).isoformat()
        evidence.canonical_tick_time_msc = tick_msc

        evidence.canonical_bid = float(selected_tick[2])
        evidence.canonical_ask = float(selected_tick[3])
        evidence.canonical_last = float(selected_tick[4]) if len(selected_tick) > 4 else None
        evidence.canonical_volume = float(selected_tick[5]) if len(selected_tick) > 5 else None
        evidence.canonical_flags = int(selected_tick[6]) if len(selected_tick) > 6 else 0

        # -- Freshness check --
        tick_datetime = datetime.fromtimestamp(tick_time, tz=timezone.utc)
        age_ms = (datetime.now(timezone.utc) - tick_datetime).total_seconds() * 1000
        evidence.canonical_tick_age_ms = age_ms

        if age_ms < 0:
            evidence.time_authority_status = CANONICAL_TICK_FUTURE
            return evidence

        # Must be inside requested window
        inside_window = window_from <= tick_datetime <= window_to

        if not inside_window:
            evidence.time_authority_status = CANONICAL_TICK_OUTSIDE_WINDOW
            return evidence

        if age_ms > CANONICAL_TICK_MAX_AGE_MS:
            evidence.time_authority_status = CANONICAL_TICK_STALE
            return evidence

        # Must have valid bid/ask
        if evidence.canonical_bid is None or evidence.canonical_ask is None:
            evidence.time_authority_status = CANONICAL_TICK_INVALID_PRICE
            return evidence

        if evidence.canonical_ask < evidence.canonical_bid:
            evidence.time_authority_status = CANONICAL_TICK_INVALID_PRICE
            evidence.source_error = f"ask({evidence.canonical_ask}) < bid({evidence.canonical_bid})"
            return evidence

        # All checks passed
        evidence.time_authority_status = TIME_SOURCE_CONSISTENT

    except Exception as e:
        evidence.source_error = str(e)
        evidence.time_authority_status = TIME_SOURCE_INCONSISTENT
        logger.exception("Canonical tick query failed")

    return evidence


def check_native_quote_divergence(
    evidence: CanonicalTickEvidence,
    native_bid: Optional[float],
    native_ask: Optional[float],
    tick_size: float = 0.01,
    max_divergence_ticks: int = MAX_QUOTE_DIVERGENCE_TICKS,
    max_spread_divergence_ticks: int = MAX_QUOTE_SPREAD_DIVERGENCE_TICKS,
) -> CanonicalTickEvidence:
    """Compare native symbol_info_tick() prices with canonical tick prices.
    
    Sets quote_coherence_status = QUOTE_SOURCE_COHERENT only if:
    - Both quotes have valid bid/ask
    - bid divergence <= max_divergence_ticks
    - ask divergence <= max_divergence_ticks
    - spread divergence <= max_spread_divergence_ticks
    """
    evidence.native_quote_bid = native_bid
    evidence.native_quote_ask = native_ask
    evidence.quote_source = LIVE_PRICE_INPUT_WITH_UNTRUSTED_NATIVE_TIMESTAMP

    if (evidence.canonical_bid is None or evidence.canonical_ask is None or
        native_bid is None or native_ask is None):
        evidence.quote_price_divergence_passed = False
        evidence.quote_coherence_status = QUOTE_SOURCE_DIVERGENT
        return evidence

    # Calculate divergences
    bid_div = abs(native_bid - evidence.canonical_bid) / tick_size if tick_size > 0 else 0
    ask_div = abs(native_ask - evidence.canonical_ask) / tick_size if tick_size > 0 else 0
    evidence.bid_divergence_ticks = round(bid_div, 2)
    evidence.ask_divergence_ticks = round(ask_div, 2)
    
    max_div = max(bid_div, ask_div)
    evidence.quote_price_divergence_ticks = round(max_div, 2)
    
    # Spread comparison
    canonical_spread = evidence.canonical_ask - evidence.canonical_bid
    native_spread = native_ask - native_bid
    evidence.canonical_spread_ticks = round(canonical_spread / tick_size, 2) if tick_size > 0 else 0
    evidence.native_spread_ticks = round(native_spread / tick_size, 2) if tick_size > 0 else 0
    evidence.spread_divergence_ticks = round(abs(evidence.canonical_spread_ticks - evidence.native_spread_ticks), 2)
    
    # Both must pass
    bid_ok = bid_div <= max_divergence_ticks
    ask_ok = ask_div <= max_divergence_ticks
    spread_ok = (evidence.spread_divergence_ticks or 0) <= max_spread_divergence_ticks
    
    evidence.quote_price_divergence_passed = bid_ok and ask_ok and spread_ok
    evidence.quote_coherence_status = QUOTE_SOURCE_COHERENT if evidence.quote_price_divergence_passed else QUOTE_SOURCE_DIVERGENT

    return evidence


def is_time_authority_consistent(status: str) -> bool:
    """Check if time authority status allows execution."""
    return status == TIME_SOURCE_CONSISTENT


def is_time_authority_blocking(status: str) -> bool:
    """Check if time authority status blocks execution."""
    return status != TIME_SOURCE_CONSISTENT


def check_execution_quote_available(
    evidence: CanonicalTickEvidence,
    native_bid: Optional[float],
    native_ask: Optional[float],
    terminal_connected: bool = True,
    position_count: int = 0,
    order_count: int = 0,
    feature_gate_off: bool = True,
    kill_switch_on: bool = True,
) -> CanonicalTickEvidence:
    """G3.2.4: Check execution quote availability.

    All conditions must be true for EXECUTION_QUOTE_AVAILABLE:
      - symbol_info_tick() returns valid bid>0, ask>0, ask>=bid
      - canonical UTC tick fresh independently (age >= 0, age <= max_age)
      - terminal connected
      - 0 positions, 0 orders
      - feature gate OFF, kill switch ON

    Does NOT require canonical/native price equality.
    """
    now_utc = datetime.now(timezone.utc)

    # Native bid/ask validity
    evidence.native_quote_bid = native_bid
    evidence.native_quote_ask = native_ask
    native_bid_valid = (native_bid is not None and native_bid > 0)
    native_ask_valid = (native_ask is not None and native_ask > 0)
    spread_valid = native_bid_valid and native_ask_valid and (native_ask >= native_bid)

    # Canonical tick freshness (independent of native)
    canonical_tick_fresh = False
    if evidence.canonical_tick_age_ms is not None:
        age_ms = evidence.canonical_tick_age_ms
        canonical_tick_fresh = (age_ms >= 0 and age_ms <= CANONICAL_TICK_MAX_AGE_MS)

    evidence.native_bid_valid = spread_valid and native_bid_valid
    evidence.native_ask_valid = spread_valid and native_ask_valid
    evidence.canonical_tick_fresh = canonical_tick_fresh
    evidence.terminal_connected = terminal_connected
    evidence.position_count = position_count
    evidence.order_count = order_count
    evidence.feature_gate_off = feature_gate_off
    evidence.kill_switch_on = kill_switch_on

    all_pass = (
        evidence.native_bid_valid
        and evidence.native_ask_valid
        and spread_valid
        and canonical_tick_fresh
        and terminal_connected
        and position_count == 0
        and order_count == 0
        and feature_gate_off
        and kill_switch_on
    )

    evidence.execution_quote_status = EXECUTION_QUOTE_AVAILABLE if all_pass else EXECUTION_QUOTE_UNAVAILABLE
    return evidence


def check_canonical_tick_audit(
    evidence: CanonicalTickEvidence,
) -> CanonicalTickEvidence:
    """G3.2.4: Audit canonical tick for time authority.

    All conditions must be true for CANONICAL_TICK_AUDIT_PASS:
      - copy_ticks_range returned valid tick (bid>0, ask>0, ask>=bid)
      - timestamp inside UTC window
      - age within bounds (age >= 0, age <= max_age)
      - no future tick (age >= 0)

    Does NOT use abs(age_ms). Does NOT require canonical/native price equality.
    """
    # Tick validity already checked in query_canonical_utc_tick
    tick_valid = (
        evidence.canonical_bid is not None
        and evidence.canonical_ask is not None
        and evidence.canonical_bid > 0
        and evidence.canonical_ask > 0
        and evidence.canonical_ask >= evidence.canonical_bid
    )

    # Timestamp inside window
    timestamp_inside = evidence.time_authority_status != CANONICAL_TICK_OUTSIDE_WINDOW

    # Age within bounds (no abs(age_ms))
    age_within = False
    no_future = False
    if evidence.canonical_tick_age_ms is not None:
        age_ms = evidence.canonical_tick_age_ms
        no_future = age_ms >= 0
        age_within = no_future and age_ms <= CANONICAL_TICK_MAX_AGE_MS

    evidence.audit_tick_valid = tick_valid
    evidence.audit_timestamp_inside_window = timestamp_inside
    evidence.audit_age_within_bounds = age_within
    evidence.audit_no_future_tick = no_future

    all_pass = tick_valid and timestamp_inside and age_within and no_future
    evidence.canonical_audit_status = CANONICAL_TICK_AUDIT_PASS if all_pass else CANONICAL_TICK_AUDIT_FAIL
    return evidence
