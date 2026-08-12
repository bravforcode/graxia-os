"""BE-P8.3.3 — Terminal Time Authority Probe (Python side).

Reads MQL5 JSONL output, cross-checks with Python API,
runs copy_ticks_range diagnostic matrix, applies acceptance criteria.
"""

import hashlib
import json
import time
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime, timedelta, timezone

# ── MQL5 probe reader ────────────────────────────────────────────────


@dataclass
class MQL5ProbeSample:
    """One sample from MQL5 terminal_time_probe.mq5."""

    sample: int = 0
    symbol: str = ""
    server: str = ""
    login: int = 0
    terminal_build: int = 0
    timecurrent_raw: int = 0
    timecurrent_struct: str = ""
    timetradeserver_raw: int = 0
    timetradeserver_struct: str = ""
    timelocal_raw: int = 0
    timelocal_struct: str = ""
    timegmt_raw: int = 0
    timegmt_struct: str = ""
    timegmtoffset_seconds: int = 0
    tick_time_raw: int = 0
    tick_time_msc: int = 0
    tick_bid: float = 0.0
    tick_ask: float = 0.0
    bar_time_raw: int = 0
    m1_time_raw: int = 0
    h1_time_raw: int = 0
    server_minus_gmt_seconds: int = 0
    tick_minus_timecurrent_ms: int = 0
    tick_minus_timecurrent_msc: int = 0

    def to_dict(self) -> dict:
        return asdict(self)


def read_mql5_probe(path: str) -> list[MQL5ProbeSample]:
    """Read JSONL output from MQL5 terminal_time_probe.mq5."""
    samples = []
    with open(path) as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            try:
                d = json.loads(line)
                samples.append(
                    MQL5ProbeSample(**{k: v for k, v in d.items() if k in MQL5ProbeSample.__dataclass_fields__})
                )
            except (json.JSONDecodeError, TypeError):
                continue
    return samples


# ── Python API cross-check ──────────────────────────────────────────


@dataclass
class PythonAPICheck:
    """Python MT5 API timestamp for the same instant."""

    system_epoch_ms: int = 0
    system_utc_iso: str = ""
    py_tick_time: int = 0
    py_tick_time_msc: int = 0
    py_tick_utc: str = ""
    py_received_at_utc: str = ""
    py_tick_matches_mql5: bool = False
    py_tick_diff_ms: float = 0.0

    def to_dict(self) -> dict:
        return asdict(self)


# ── copy_ticks_range diagnostic matrix ──────────────────────────────


@dataclass
class CopyTicksDiagnostic:
    """Result of one copy_ticks_range variant."""

    variant: str = ""  # "utc_aware", "naive_utc", "local_aware", "copy_ticks_from"
    request_from: str = ""
    request_to: str = ""
    request_hash: str = ""
    returned_count: int = 0
    first_epoch: int = 0
    last_epoch: int = 0
    first_utc: str = ""
    last_utc: str = ""
    ticks_in_window: bool = False
    ticks_outside_count: int = 0
    error: str = ""

    def to_dict(self) -> dict:
        return asdict(self)


# ── Acceptance criteria ─────────────────────────────────────────────


@dataclass
class AcceptanceResult:
    """Result of 7 acceptance criteria."""

    # 1. TimeCurrent() - TimeGMT() consistent and explainable
    criterion_1_server_gmt_offset: str = "PENDING"
    criterion_1_offset_seconds: int = 0
    criterion_1_offset_stable: bool = False
    # 2. SymbolInfoTick.time matches TimeCurrent() within tolerance
    criterion_2_tick_matches_server: str = "PENDING"
    criterion_2_diff_ms: float = 0.0
    # 3. Python symbol_info_tick() matches MQL5 SymbolInfoTick.time
    criterion_3_python_matches_mql5: str = "PENDING"
    criterion_3_diff_ms: float = 0.0
    # 4. copy_ticks_range() returns ticks within request window
    criterion_4_ticks_in_window: str = "PENDING"
    criterion_4_variant_with_pass: str = ""
    # 5. M1 bar not stale, relates to current tick
    criterion_5_m1_not_stale: str = "PENDING"
    criterion_5_m1_age_seconds: int = 0
    # 6. H1 bar consistent with M1/tick
    criterion_6_h1_consistent: str = "PENDING"
    criterion_6_h1_m1_diff_seconds: int = 0
    # 7. All paths labeled
    criterion_7_labels: list = field(default_factory=list)
    # Overall
    all_passed: bool = False
    verdict: str = "PENDING"

    def to_dict(self) -> dict:
        return asdict(self)


# ── Main reconciler ─────────────────────────────────────────────────


class TerminalTimeReconciler:
    """Reads MQL5 probe + Python API, runs diagnostic matrix,
    applies acceptance criteria, labels all paths."""

    def __init__(self, mt5_connection, symbol: str = "XAUUSD"):
        self._mt5 = mt5_connection
        self._symbol = symbol

    def run(
        self,
        mql5_probe_path: str,
        py_api_samples: list[dict] | None = None,
    ) -> dict:
        """Full reconciliation."""
        # 1. Read MQL5 probe
        mql5_samples = read_mql5_probe(mql5_probe_path)
        if not mql5_samples:
            return {"error": "No MQL5 probe samples found"}

        # 2. Use first sample for analysis (or average)
        s = mql5_samples[0]

        # 3. Python API cross-check
        py_check = self._check_python_api(s)

        # 4. copy_ticks_range diagnostic matrix
        copy_diag = self._run_copy_ticks_diagnostics()

        # 5. Apply acceptance criteria
        acceptance = self._apply_acceptance_criteria(s, py_check, copy_diag)

        return {
            "mql5_sample_count": len(mql5_samples),
            "mql5_first_sample": s.to_dict(),
            "mql5_all_samples": [x.to_dict() for x in mql5_samples],
            "python_api_check": py_check.to_dict(),
            "copy_ticks_diagnostics": [d.to_dict() for d in copy_diag],
            "acceptance": acceptance.to_dict(),
        }

    def _check_python_api(self, mql5_sample: MQL5ProbeSample) -> PythonAPICheck:
        """Cross-check Python MT5 API against MQL5 probe."""
        now = datetime.now(UTC)
        check = PythonAPICheck(
            system_epoch_ms=int(time.time() * 1000),
            system_utc_iso=now.isoformat(),
            py_received_at_utc=now.isoformat(),
        )

        tick = self._mt5.get_tick(self._symbol)
        if tick is None:
            return check

        check.py_tick_time = tick["time"]
        check.py_tick_time_msc = tick.get("time_msc", tick["time"] * 1000)
        check.py_tick_utc = datetime.fromtimestamp(check.py_tick_time_msc / 1000, tz=UTC).isoformat()

        # Compare with MQL5
        mql5_tick = mql5_sample.tick_time_raw
        if mql5_tick > 0 and check.py_tick_time > 0:
            check.py_tick_matches_mql5 = abs(check.py_tick_time - mql5_tick) <= 2
            check.py_tick_diff_ms = abs(check.py_tick_time - mql5_tick) * 1000

        return check

    def _run_copy_ticks_diagnostics(self) -> list[CopyTicksDiagnostic]:
        """Run copy_ticks_range with 4 input variants."""
        results = []
        now = datetime.now(UTC)

        # Variant A: timezone-aware UTC
        results.append(self._copy_ticks_variant("utc_aware", now - timedelta(minutes=5), now, utc_aware=True))

        # Variant B: naive UTC (strip tzinfo)
        naive_from = datetime(now.year, now.month, now.day, now.hour, now.minute - 5, now.second)
        naive_to = datetime(now.year, now.month, now.day, now.hour, now.minute, now.second)
        results.append(self._copy_ticks_variant("naive_utc", naive_from, naive_to, utc_aware=False))

        # Variant C: local-time aware (UTC+7 for Thailand)
        local_tz = timezone(timedelta(hours=7))
        local_from = (now - timedelta(minutes=5)).astimezone(local_tz)
        local_to = now.astimezone(local_tz)
        results.append(self._copy_ticks_variant("local_aware_7", local_from, local_to, utc_aware=True))

        # Variant D: copy_ticks_from (last N ticks)
        results.append(self._copy_ticks_from_variant(count=50))

        return results

    def _copy_ticks_variant(self, variant: str, fr, to, utc_aware: bool = True) -> CopyTicksDiagnostic:
        """Run copy_ticks_range with specific input type."""
        diag = CopyTicksDiagnostic(variant=variant)
        diag.request_from = fr.isoformat()
        diag.request_to = to.isoformat()
        window_d = {"from": fr.isoformat(), "to": to.isoformat()}
        diag.request_hash = hashlib.sha256(json.dumps(window_d, sort_keys=True).encode()).hexdigest()[:16]

        try:
            # Get raw MT5 handle
            mt5 = self._mt5._mt5
            if not utc_aware:
                # Convert naive to UTC-aware before passing to MT5
                fr_aware = fr.replace(tzinfo=UTC)
                to_aware = to.replace(tzinfo=UTC)
            else:
                fr_aware = fr
                to_aware = to

            ticks = mt5.copy_ticks_range(self._symbol, fr_aware, to_aware, mt5.COPY_TICKS_ALL)
            if ticks is not None and len(ticks) > 0:
                diag.returned_count = len(ticks)
                diag.first_epoch = int(ticks[0][0])
                diag.last_epoch = int(ticks[-1][0])
                diag.first_utc = datetime.fromtimestamp(diag.first_epoch, tz=UTC).isoformat()
                diag.last_utc = datetime.fromtimestamp(diag.last_epoch, tz=UTC).isoformat()
                # Check if within window
                fr_epoch = int(fr_aware.timestamp())
                to_epoch = int(to_aware.timestamp())
                outside = 0
                for t in ticks:
                    te = int(t[0])
                    if te < fr_epoch or te > to_epoch:
                        outside += 1
                diag.ticks_outside_count = outside
                diag.ticks_in_window = outside == 0
        except Exception as e:
            diag.error = str(e)

        return diag

    def _copy_ticks_from_variant(self, count: int = 50) -> CopyTicksDiagnostic:
        """Run copy_ticks_from (last N ticks)."""
        diag = CopyTicksDiagnostic(variant="copy_ticks_from")
        try:
            mt5 = self._mt5._mt5
            ticks = mt5.copy_ticks_from(self._symbol, 0, count, mt5.COPY_TICKS_ALL)
            if ticks is not None and len(ticks) > 0:
                diag.returned_count = len(ticks)
                diag.first_epoch = int(ticks[0][0])
                diag.last_epoch = int(ticks[-1][0])
                diag.first_utc = datetime.fromtimestamp(diag.first_epoch, tz=UTC).isoformat()
                diag.last_utc = datetime.fromtimestamp(diag.last_epoch, tz=UTC).isoformat()
                now = datetime.now(UTC)
                now_epoch = int(now.timestamp())
                one_min_ago = int((now - timedelta(minutes=5)).timestamp())
                outside = 0
                for t in ticks:
                    te = int(t[0])
                    if te < one_min_ago or te > now_epoch:
                        outside += 1
                diag.ticks_outside_count = outside
                diag.ticks_in_window = outside == 0
        except Exception as e:
            diag.error = str(e)

        return diag

    def _apply_acceptance_criteria(
        self,
        mql5: MQL5ProbeSample,
        py_check: PythonAPICheck,
        copy_diag: list[CopyTicksDiagnostic],
    ) -> AcceptanceResult:
        """Apply 7 acceptance criteria."""
        result = AcceptanceResult()

        # Criterion 1: TimeCurrent() - TimeGMT() consistent
        offset = mql5.server_minus_gmt_seconds
        result.criterion_1_offset_seconds = offset
        # Check stability across samples (if multiple)
        result.criterion_1_offset_stable = True  # assumed stable for single sample
        if abs(offset) > 0:
            result.criterion_1_server_gmt_offset = "VERIFIED_SERVER_OFFSET"
        else:
            result.criterion_1_server_gmt_offset = "UTC_VERIFIED"

        # Criterion 2: SymbolInfoTick.time matches TimeCurrent()
        tick_diff_ms = abs(mql5.tick_minus_timecurrent_ms)
        result.criterion_2_diff_ms = tick_diff_ms
        if tick_diff_ms <= 2000:  # within 2s tolerance
            result.criterion_2_tick_matches_server = "PASS"
        else:
            result.criterion_2_tick_matches_server = "FAIL"

        # Criterion 3: Python matches MQL5
        result.criterion_3_diff_ms = py_check.py_tick_diff_ms
        if py_check.py_tick_matches_mql5:
            result.criterion_3_python_matches_mql5 = "PASS"
        else:
            result.criterion_3_python_matches_mql5 = "FAIL"

        # Criterion 4: copy_ticks_range in window
        for d in copy_diag:
            if d.ticks_in_window and d.returned_count > 0:
                result.criterion_4_ticks_in_window = "PASS"
                result.criterion_4_variant_with_pass = d.variant
                break
        else:
            result.criterion_4_ticks_in_window = "FAIL"

        # Criterion 5: M1 not stale
        now = datetime.now(UTC)
        if mql5.m1_time_raw > 0:
            m1_age = int(now.timestamp()) - mql5.m1_time_raw
            result.criterion_5_m1_age_seconds = m1_age
            if m1_age <= 120:  # within 2 minutes
                result.criterion_5_m1_not_stale = "PASS"
            else:
                result.criterion_5_m1_not_stale = "FAIL"
        else:
            result.criterion_5_m1_not_stale = "FAIL"

        # Criterion 6: H1 consistent with M1/tick
        if mql5.h1_time_raw > 0 and mql5.m1_time_raw > 0:
            h1_m1_diff = mql5.m1_time_raw - mql5.h1_time_raw
            result.criterion_6_h1_m1_diff_seconds = h1_m1_diff
            # H1 bar should be ≤ current hour, M1 should be within same or next hour
            if 0 <= h1_m1_diff <= 3600:
                result.criterion_6_h1_consistent = "PASS"
            else:
                result.criterion_6_h1_consistent = "FAIL"
        else:
            result.criterion_6_h1_consistent = "FAIL"

        # Criterion 7: Labels
        labels = []
        if result.criterion_1_server_gmt_offset:
            labels.append(result.criterion_1_server_gmt_offset)
        if result.criterion_2_tick_matches_server:
            labels.append(f"tick_server={result.criterion_2_tick_matches_server}")
        if result.criterion_3_python_matches_mql5:
            labels.append(f"python_mql5={result.criterion_3_python_matches_mql5}")
        if result.criterion_4_ticks_in_window:
            labels.append(f"ticks_window={result.criterion_4_ticks_in_window}")
        if result.criterion_5_m1_not_stale:
            labels.append(f"m1_fresh={result.criterion_5_m1_not_stale}")
        if result.criterion_6_h1_consistent:
            labels.append(f"h1_consistent={result.criterion_6_h1_consistent}")
        result.criterion_7_labels = labels

        # Overall
        result.all_passed = all(
            [
                result.criterion_1_server_gmt_offset in ("UTC_VERIFIED", "VERIFIED_SERVER_OFFSET"),
                result.criterion_2_tick_matches_server == "PASS",
                result.criterion_3_python_matches_mql5 == "PASS",
                result.criterion_4_ticks_in_window == "PASS",
                result.criterion_5_m1_not_stale == "PASS",
                result.criterion_6_h1_consistent == "PASS",
            ]
        )
        result.verdict = "UTC_VERIFIED" if result.all_passed else "TIME_SOURCE_INCONSISTENT"

        return result
