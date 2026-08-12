"""Phase BE-P5 — Differential comparator for oracle outputs."""
from dataclasses import dataclass


@dataclass
class ComparisonResult:
    match: bool
    signal_count_a: int
    signal_count_b: int
    direction_mismatches: int
    entry_mismatches: int
    sl_mismatches: int
    tp_mismatches: int
    timing_mismatches: int
    issues: list[str]


class DifferentialComparator:
    """Compare two oracle outputs for consistency."""

    def __init__(self, tolerance_pct: float = 0.1):
        self._tolerance_pct = tolerance_pct

    def compare_signals(self, signals_a: list[dict], signals_b: list[dict]) -> ComparisonResult:
        """Compare two sets of normalized signals."""
        issues = []
        direction_mismatches = 0
        entry_mismatches = 0
        sl_mismatches = 0
        tp_mismatches = 0
        timing_mismatches = 0

        max_len = max(len(signals_a), len(signals_b))

        for i in range(max_len):
            if i >= len(signals_a):
                issues.append(f"signal_b[{i}] has no match in a")
                continue
            if i >= len(signals_b):
                issues.append(f"signal_a[{i}] has no match in b")
                continue

            a = signals_a[i]
            b = signals_b[i]

            if a.get("direction") != b.get("direction"):
                direction_mismatches += 1
                issues.append(f"direction mismatch at {i}: {a.get('direction')} vs {b.get('direction')}")

            if not self._close_enough(a.get("entry_price", 0), b.get("entry_price", 0)):
                entry_mismatches += 1
                issues.append(f"entry mismatch at {i}")

            if not self._close_enough(a.get("stop_loss", 0), b.get("stop_loss", 0)):
                sl_mismatches += 1
                issues.append(f"SL mismatch at {i}")

            if not self._close_enough(a.get("take_profit", 0), b.get("take_profit", 0)):
                tp_mismatches += 1
                issues.append(f"TP mismatch at {i}")

            if a.get("timestamp_utc") != b.get("timestamp_utc"):
                timing_mismatches += 1
                issues.append(f"timing mismatch at {i}")

        match = (direction_mismatches == 0 and entry_mismatches == 0 and
                sl_mismatches == 0 and tp_mismatches == 0 and
                len(signals_a) == len(signals_b))

        return ComparisonResult(
            match=match,
            signal_count_a=len(signals_a),
            signal_count_b=len(signals_b),
            direction_mismatches=direction_mismatches,
            entry_mismatches=entry_mismatches,
            sl_mismatches=sl_mismatches,
            tp_mismatches=tp_mismatches,
            timing_mismatches=timing_mismatches,
            issues=issues,
        )

    def _close_enough(self, a: float, b: float) -> bool:
        if a == 0 and b == 0:
            return True
        if a == 0 or b == 0:
            return False
        return abs(a - b) / max(abs(a), abs(b)) <= self._tolerance_pct / 100
