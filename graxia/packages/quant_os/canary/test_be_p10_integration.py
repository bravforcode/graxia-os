"""Phase BE-P10 integration tests — demo campaign and incident drills."""

from graxia.packages.quant_os.canary.daily_report import DailyReport
from graxia.packages.quant_os.canary.demo_campaign import DemoCampaign
from graxia.packages.quant_os.canary.demo_scorecard import DemoScorecard
from graxia.packages.quant_os.canary.drills import (
    DRILL_REQUIREMENTS,
    DrillExecutor,
    DrillResult,
    DrillType,
)
from graxia.packages.quant_os.canary.weekly_report import WeeklyReport


def test_drill_executor_all_types():
    executor = DrillExecutor()
    for dt in DrillType:
        req = DRILL_REQUIREMENTS.get(dt, {})
        result = DrillResult(
            drill_type=dt.value,
            detection_time_ms=10,
            new_order_blocked=req.get("must_block", True),
            existing_position_behavior="no_change",
            alert_delivered=True,
            recovery_verified=True,
            evidence_retained=True,
            postmortem_status="resolved",
        )
        executor.execute_drill(dt, result)
    assert executor.summary()["total_drills"] == 13
    assert executor.summary()["all_passed"]


def test_daily_report_full():
    report = DailyReport(date="2026-06-22", signals=10, orders=5, fills=3)
    assert report.to_dict()["signals"] == 10
    assert "Daily Report" in report.to_markdown()


def test_weekly_report_evaluate():
    report = WeeklyReport(
        unresolved_incidents=0,
        reconciliation_accuracy_pct=100,
        risk_limit_breaches=0,
        backtest_demo_gap_pct=20,
    )
    ok, issues = report.evaluate()
    assert ok


def test_demo_scorecard_pass():
    sc = DemoScorecard()
    metrics = {
        "unexplained_orders": 0,
        "unprotected_positions": 0,
        "stale_data_orders": 0,
        "event_bypass_orders": 0,
        "risk_breaches": 0,
        "reconciliation_pct": 100,
        "critical_incidents": 0,
        "cost_gap_pct": 20,
        "evidence_label": "DEMO_OBSERVED",
    }
    sc.evaluate(metrics)
    assert sc.all_passed()


def test_demo_campaign_lifecycle():
    campaign = DemoCampaign()
    campaign.start()
    campaign.record_day(signals=10, orders=5, fills=3, incidents=0)
    campaign.complete()
    s = campaign.get_summary()
    assert s["status"] == "completed"
    assert s["days_run"] == 1
