"""Tests for weekly report."""
from graxia.packages.quant_os.canary.weekly_report import WeeklyReport


def test_report_creates():
    report = WeeklyReport(week_start="2026-06-16", week_end="2026-06-22")
    d = report.to_dict()
    assert d["week_start"] == "2026-06-16"


def test_report_markdown():
    report = WeeklyReport(week_start="2026-06-16", week_end="2026-06-22")
    md = report.to_markdown()
    assert "Weekly Report" in md


def test_report_evaluate_pass():
    report = WeeklyReport(unresolved_incidents=0, reconciliation_accuracy_pct=100)
    ok, issues = report.evaluate()
    assert ok


def test_report_evaluate_fail():
    report = WeeklyReport(unresolved_incidents=2, reconciliation_accuracy_pct=95)
    ok, issues = report.evaluate()
    assert not ok
    assert len(issues) == 2
