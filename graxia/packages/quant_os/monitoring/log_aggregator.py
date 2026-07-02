"""
Structured log aggregation pipeline.

Reads JSON log files from logs/ directory, parses structured JSON lines,
and aggregates counts by error, warning, trade events, and risk alerts.
Supports tailing for real-time monitoring.
"""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any, Iterator


def _parse_line(line: str) -> dict[str, Any] | None:
    """Parse a single JSON log line, return None on failure."""
    line = line.strip()
    if not line:
        return None
    try:
        return json.loads(line)
    except json.JSONDecodeError:
        return None


def _classify_entry(entry: dict[str, Any]) -> list[str]:
    """Return list of category tags for a log entry."""
    categories: list[str] = []
    level = entry.get("level", "").lower()
    event = entry.get("event", "").lower()
    msg = entry.get("message", "").lower() if "message" in entry else event

    if level in ("error", "critical", "fatal"):
        categories.append("error")
    elif level in ("warning", "warn"):
        categories.append("warning")

    trade_keywords = ("trade", "order", "position", "entry", "exit", "fill")
    if any(k in event for k in trade_keywords) or any(k in msg for k in trade_keywords):
        categories.append("trade")

    risk_keywords = ("risk", "drawdown", "limit", "breach", "exposure", "stop_loss")
    if any(k in event for k in risk_keywords) or any(k in msg for k in risk_keywords):
        categories.append("risk")

    return categories


class LogAggregator:
    """Aggregates structured JSON log lines into summary statistics."""

    def __init__(self, log_dir: str | Path = "logs"):
        self.log_dir = Path(log_dir)
        self.error_count = 0
        self.warning_count = 0
        self.trade_events = 0
        self.risk_alerts = 0
        self.total_lines = 0
        self._seen_offsets: dict[str, int] = {}

    def scan_files(self, pattern: str = "*.jsonl") -> dict[str, Any]:
        """Scan all matching log files and return aggregated summary."""
        self._reset()
        if not self.log_dir.exists():
            return self._summary()

        for log_file in sorted(self.log_dir.glob(pattern)):
            self._process_file(log_file)
        return self._summary()

    def _process_file(self, path: Path) -> None:
        """Read and classify all lines in a file."""
        try:
            with open(path, "r", encoding="utf-8") as f:
                for line in f:
                    entry = _parse_line(line)
                    if entry is None:
                        continue
                    self.total_lines += 1
                    cats = _classify_entry(entry)
                    if "error" in cats:
                        self.error_count += 1
                    if "warning" in cats:
                        self.warning_count += 1
                    if "trade" in cats:
                        self.trade_events += 1
                    if "risk" in cats:
                        self.risk_alerts += 1
        except OSError:
            pass

    def tail(self, poll_interval: float = 1.0, callback: Any = None) -> Iterator[dict[str, Any]]:
        """
        Tail all JSONL files in log_dir, yielding new entries as dicts.
        Yields each parsed entry with added 'categories' key.
        If callback is provided, calls callback(entry) for each new entry.
        """
        if not self.log_dir.exists():
            self.log_dir.mkdir(parents=True, exist_ok=True)

        tracked: dict[str, tuple[int, Any]] = {}
        while True:
            for log_file in sorted(self.log_dir.glob("*.jsonl")):
                fpath = str(log_file)
                offset = self._seen_offsets.get(fpath, 0)
                try:
                    size = log_file.stat().st_size
                    if size < offset:
                        offset = 0
                    if size == offset:
                        continue
                    with open(log_file, "r", encoding="utf-8") as f:
                        f.seek(offset)
                        for line in f:
                            entry = _parse_line(line)
                            if entry is None:
                                continue
                            entry["categories"] = _classify_entry(entry)
                            self.total_lines += 1
                            for cat in entry["categories"]:
                                if cat == "error":
                                    self.error_count += 1
                                elif cat == "warning":
                                    self.warning_count += 1
                                elif cat == "trade":
                                    self.trade_events += 1
                                elif cat == "risk":
                                    self.risk_alerts += 1
                            if callback:
                                callback(entry)
                            yield entry
                    self._seen_offsets[fpath] = log_file.stat().st_size
                except OSError:
                    pass
            time.sleep(poll_interval)

    def _reset(self) -> None:
        self.error_count = 0
        self.warning_count = 0
        self.trade_events = 0
        self.risk_alerts = 0
        self.total_lines = 0

    def _summary(self) -> dict[str, Any]:
        return {
            "total_lines": self.total_lines,
            "error_count": self.error_count,
            "warning_count": self.warning_count,
            "trade_events": self.trade_events,
            "risk_alerts": self.risk_alerts,
        }


def aggregate_logs(log_dir: str | Path = "logs", pattern: str = "*.jsonl") -> dict[str, Any]:
    """Convenience function: scan and return summary dict."""
    agg = LogAggregator(log_dir)
    return agg.scan_files(pattern)
