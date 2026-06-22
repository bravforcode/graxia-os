"""Tests for daily report."""
from graxia.packages.quant_os.canary.daily_report import DailyReport, DailyReporter


def test_report_creates():
    report = DailyReport(date="2026-06-22", signals=10, orders=5)
    d = report.to_dict()
    assert d["date"] == "2026-06-22"
    assert d["signals"] == 10


def test_report_markdown():
    report = DailyReport(date="2026-06-22", signals=10)
    md = report.to_markdown()
    assert "Daily Report: 2026-06-22" in md


def test_reporter_collects():
    reporter = DailyReporter()
    reporter.add_report(DailyReport(date="2026-06-22"))
    reporter.add_report(DailyReport(date="2026-06-23"))
    assert len(reporter.get_reports()) == 2
    assert reporter.get_latest().date == "2026-06-23"
