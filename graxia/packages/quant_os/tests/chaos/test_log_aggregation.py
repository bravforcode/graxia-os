"""
Tests for log aggregation pipeline: aggregator, rotation, formatter, correlation_id.

Uses importlib.util to load modules directly, bypassing monitoring/__init__.py
which pulls in telegram.py with broken relative imports outside the package.
"""

from __future__ import annotations

import gzip
import importlib.util
import json
import os
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path

# ---------------------------------------------------------------------------
# Direct file-level imports — no __init__.py triggered
# ---------------------------------------------------------------------------
_pkg_root = str(Path(__file__).resolve().parents[2])
_monitoring = Path(_pkg_root) / "monitoring"


def _load_mod(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


_mod_agg = _load_mod("_m_log_aggregator", _monitoring / "log_aggregator.py")
_mod_rot = _load_mod("_m_log_rotation", _monitoring / "log_rotation.py")
_mod_fmt = _load_mod("_m_structured_formatter", _monitoring / "structured_formatter.py")

LogAggregator = _mod_agg.LogAggregator
aggregate_logs = _mod_agg.aggregate_logs
_classify_entry = _mod_agg._classify_entry
_parse_line = _mod_agg._parse_line

rotate_by_size = _mod_rot.rotate_by_size
rotate_by_time = _mod_rot.rotate_by_time
rotate_all = _mod_rot.rotate_all
_gzip_file = _mod_rot._gzip_file
_cleanup_old = _mod_rot._cleanup_old

add_structured_fields = _mod_fmt.add_structured_fields
json_formatter = _mod_fmt.json_formatter
console_formatter = _mod_fmt.console_formatter
correlation_id_var = _mod_fmt.correlation_id_var


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _write_log(path: Path, lines: list[dict]) -> None:
    with open(path, "w", encoding="utf-8") as f:
        for line in lines:
            f.write(json.dumps(line, default=str) + "\n")


def _sample_entries() -> list[dict]:
    return [
        {"level": "info", "event": "startup", "message": "engine started"},
        {"level": "warning", "event": "spread_wide", "message": "spread > threshold"},
        {"level": "error", "event": "connection_failed", "message": "broker timeout"},
        {"level": "info", "event": "trade_entry", "message": "bought XAUUSD 0.01 lot"},
        {"level": "info", "event": "trade_exit", "message": "sold XAUUSD 0.01 lot"},
        {"level": "warning", "event": "risk_drawdown", "message": "drawdown 5%"},
        {"level": "critical", "event": "risk_breach", "message": "max exposure breach"},
        {"level": "error", "event": "order_rejected", "message": "insufficient margin"},
    ]


# ---------------------------------------------------------------------------
# LogAggregator tests
# ---------------------------------------------------------------------------


class TestLogAggregator:
    def test_read_json_lines(self, tmp_path):
        d = tmp_path / "logs"
        d.mkdir()
        _write_log(d / "t.jsonl", _sample_entries())
        assert LogAggregator(d).scan_files()["total_lines"] == 8

    def test_error_and_warning_counts(self, tmp_path):
        d = tmp_path / "logs"
        d.mkdir()
        _write_log(d / "t.jsonl", _sample_entries())
        r = LogAggregator(d).scan_files()
        assert r["error_count"] == 3
        assert r["warning_count"] == 2

    def test_trade_events(self, tmp_path):
        d = tmp_path / "logs"
        d.mkdir()
        _write_log(d / "t.jsonl", _sample_entries())
        assert LogAggregator(d).scan_files()["trade_events"] == 3  # trade_entry, trade_exit, order_rejected

    def test_risk_alerts(self, tmp_path):
        d = tmp_path / "logs"
        d.mkdir()
        _write_log(d / "t.jsonl", _sample_entries())
        assert LogAggregator(d).scan_files()["risk_alerts"] == 2

    def test_empty_dir(self, tmp_path):
        d = tmp_path / "logs"
        d.mkdir()
        r = LogAggregator(d).scan_files()
        assert r == {"total_lines": 0, "error_count": 0, "warning_count": 0, "trade_events": 0, "risk_alerts": 0}

    def test_malformed_skipped(self, tmp_path):
        d = tmp_path / "logs"
        d.mkdir()
        f = d / "bad.jsonl"
        f.write_text("not json\n" + json.dumps({"level": "error", "event": "x"}) + "\n\n")
        r = LogAggregator(d).scan_files()
        assert r["total_lines"] == 1 and r["error_count"] == 1

    def test_convenience_fn(self, tmp_path):
        d = tmp_path / "logs"
        d.mkdir()
        _write_log(d / "t.jsonl", _sample_entries())
        assert aggregate_logs(d)["total_lines"] == 8

    def test_classify_entry(self):
        assert "error" in _classify_entry({"level": "error", "event": "x"})
        assert "warning" in _classify_entry({"level": "warn", "event": "x"})
        assert "trade" in _classify_entry({"level": "info", "event": "trade_entry"})
        assert "risk" in _classify_entry({"level": "info", "event": "drawdown_alert"})
        assert _classify_entry({"level": "info", "event": "startup"}) == []

    def test_parse_line(self):
        assert _parse_line('{"a":1}') == {"a": 1}
        assert _parse_line("") is None
        assert _parse_line("x") is None


# ---------------------------------------------------------------------------
# Log rotation tests
# ---------------------------------------------------------------------------


class TestLogRotation:
    def test_rotate_by_size(self, tmp_path):
        d = tmp_path / "logs"
        d.mkdir()
        f = d / "t.jsonl"
        f.write_text("x" * 11 * 1024 * 1024)
        assert rotate_by_size(f, max_bytes=10 * 1024 * 1024) is True
        assert not f.exists() and (d / "t.jsonl.1").exists()

    def test_no_rotate_under_threshold(self, tmp_path):
        d = tmp_path / "logs"
        d.mkdir()
        f = d / "t.jsonl"
        f.write_text("small")
        assert rotate_by_size(f, max_bytes=10 * 1024 * 1024) is False
        assert f.exists()

    def test_rotate_by_time_old(self, tmp_path):
        d = tmp_path / "logs"
        d.mkdir()
        f = d / "t.jsonl"
        f.write_text("old")
        old = (datetime.now(UTC) - timedelta(days=2)).timestamp()
        os.utime(f, (old, old))
        assert rotate_by_time(f) is True
        assert not f.exists()
        assert len(list(d.glob("t.*.jsonl.gz"))) == 1

    def test_no_rotate_same_day(self, tmp_path):
        d = tmp_path / "logs"
        d.mkdir()
        f = d / "t.jsonl"
        f.write_text("today")
        assert rotate_by_time(f) is False
        assert f.exists()

    def test_gzip_file(self, tmp_path):
        src = tmp_path / "data.txt"
        src.write_text("hello")
        gz = _gzip_file(src)
        assert gz.exists() and not src.exists()
        with gzip.open(gz, "rt") as fp:
            assert fp.read() == "hello"

    def test_cleanup_old(self, tmp_path):
        d = tmp_path / "logs"
        d.mkdir()
        old = (datetime.now(UTC) - timedelta(days=60)).strftime("%Y%m%d")
        gz = d / f"t.{old}.jsonl.gz"
        with gzip.open(gz, "wb") as fp:
            fp.write(b"old")
        assert _cleanup_old(d, "t", ".jsonl", 30) == 1
        assert not gz.exists()

    def test_rotate_all(self, tmp_path):
        d = tmp_path / "logs"
        d.mkdir()
        (d / "big.jsonl").write_text("x" * 11 * 1024 * 1024)
        (d / "small.jsonl").write_text("ok")
        r = rotate_all(d)
        assert r["big.jsonl"] is True
        assert r["small.jsonl"] is False


# ---------------------------------------------------------------------------
# Structured formatter tests
# ---------------------------------------------------------------------------


class TestStructuredFormatter:
    def test_add_fields(self):
        e: dict = {"event": "test"}
        r = add_structured_fields(None, "", e)
        assert "timestamp" in r and isinstance(r["line"], int)
        assert "correlation_id" in r

    def test_json_format(self):
        r = json_formatter(None, "", {"level": "info", "event": "x"})
        assert json.loads(r)["level"] == "info"

    def test_console_format_with_cid(self):
        e = {
            "level": "info",
            "event": "t",
            "timestamp": "2026-01-01T00:00:00",
            "module": "m",
            "function": "f",
            "line": 1,
            "correlation_id": "abc",
        }
        assert "cid=abc" in console_formatter(None, "", e)

    def test_console_format_no_cid(self):
        e = {
            "level": "error",
            "event": "f",
            "timestamp": "",
            "module": "",
            "function": "",
            "line": 0,
            "correlation_id": "",
        }
        assert "cid=" not in console_formatter(None, "", e)


# ---------------------------------------------------------------------------
# Correlation ID propagation tests
# ---------------------------------------------------------------------------


class TestCorrelationId:
    def test_default_empty(self):
        assert correlation_id_var.get() == ""

    def test_set_read_reset(self):
        t = correlation_id_var.set("req-42")
        assert correlation_id_var.get() == "req-42"
        correlation_id_var.reset(t)
        assert correlation_id_var.get() == ""

    def test_propagates_to_event(self):
        t = correlation_id_var.set("trade-99")
        try:
            assert add_structured_fields(None, "", {"event": "o"})["correlation_id"] == "trade-99"
        finally:
            correlation_id_var.reset(t)

    def test_isolation(self):
        ta = correlation_id_var.set("a")
        tb = correlation_id_var.set("b")
        assert correlation_id_var.get() == "b"
        correlation_id_var.reset(tb)
        assert correlation_id_var.get() == "a"
        correlation_id_var.reset(ta)
        assert correlation_id_var.get() == ""
