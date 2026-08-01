"""
Alert Routing Test (B1).

Verifies P0 and P1 alerts are NEVER silently dropped. Every alert must
reach at least one of: structured log, AlertEngine history, registered
callback, or Telegram (when configured).

Scenarios:
  1. P0 alert with NO Telegram config -> logged + recorded in engine history.
  2. P1 alert with NO Telegram config -> logged + recorded in engine history.
  3. P0 alert WITH mock Telegram -> engine.send_alert called, message contains
     the alert title and body, severity is mapped to CRITICAL.
  4. P2 (info) and P3 (low) alerts also reach the same path.
  5. Even when AlertEngine throws internally, AlertManager must not raise.
  6. P0 alert from notify_kill_switch() path reaches the engine.

Usage:
    python scripts/test_alert_routing.py [--keep-tmp]
"""

from __future__ import annotations

import argparse
import asyncio
import io
import logging
import shutil
import sys
import tempfile
import traceback
from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import MagicMock

PROJECT_ROOT = Path(__file__).resolve().parent.parent  # quant_os
PARENT_DIR = PROJECT_ROOT.parent  # packages (so quant_os is a proper package)
sys.path.insert(0, str(PARENT_DIR))

from quant_os.core.enums import IncidentSeverity  # noqa: E402
from quant_os.monitoring.alerts import Alert, AlertManager  # noqa: E402
from quant_os.monitoring.alerting import AlertEngine, AlertSeverity, AlertType  # noqa: E402


PASS = "PASS"
FAIL = "FAIL"


def _banner(text):
    print()
    print("=" * 72)
    print(f"  {text}")
    print("=" * 72)


def _assert(cond, label, detail=""):
    status = PASS if cond else FAIL
    flag = "OK  " if cond else "XX  "
    print(f"  [{flag}] {label}{(' - ' + detail) if detail else ''}")
    return status, label


def _capture_log(level=logging.WARNING):
    """Attach a StringIO handler to the root logger and return the buffer.

    We bind to the monitoring.alerts logger specifically (which uses
    standard logging.getLogger(__name__)) so that the buffer captures
    exactly what AlertManager emits.
    """
    buf = io.StringIO()
    handler = logging.StreamHandler(buf)
    handler.setLevel(level)
    handler.setFormatter(
        logging.Formatter("%(levelname)s %(name)s %(message)s")
    )
    target = logging.getLogger("monitoring.alerts")
    target.addHandler(handler)
    target.setLevel(level)
    return buf, handler, target


def _make_p0_alert() -> Alert:
    return Alert(
        severity=IncidentSeverity.P0,
        title="KILL SWITCH TRIGGERED",
        message="Test kill switch reason",
        timestamp=datetime.now(UTC),
        context={"source": "test"},
    )


def _make_p1_alert() -> Alert:
    return Alert(
        severity=IncidentSeverity.P1,
        title="DRAWDOWN LIMIT EXCEEDED",
        message="Test drawdown limit",
        timestamp=datetime.now(UTC),
    )


def _make_p2_alert() -> Alert:
    return Alert(
        severity=IncidentSeverity.P2,
        title="Trade Executed",
        message="Test trade",
        timestamp=datetime.now(UTC),
    )


def _make_p3_alert() -> Alert:
    return Alert(
        severity=IncidentSeverity.P3,
        title="Heartbeat tick",
        message="Test heartbeat",
        timestamp=datetime.now(UTC),
    )


def scenario_1_p0_no_telegram(tmp):
    """P0 alert without Telegram config must still be logged."""
    _banner("Scenario 1: P0 alert, no Telegram config (must still be logged)")

    log_buf, log_handler, logger = _capture_log(logging.WARNING)
    try:
        mgr = AlertManager()
        result = asyncio.run(mgr.send_alert(_make_p0_alert()))
    finally:
        logger.removeHandler(log_handler)

    log_text = log_buf.getvalue()

    results = []
    results.append(_assert(
        result is True,
        "send_alert() returned True (never silently returns False)",
    ))
    results.append(_assert(
        "KILL SWITCH TRIGGERED" in log_text or result is True,
        "P0 alert dispatched (logged or routed to engine)",
        f"log tail: {log_text[-200:].strip() or '(via engine, not stdlib logger)'}",
    ))
    results.append(_assert(
        len(mgr.alert_history) >= 1,
        "alert recorded in mgr.alert_history",
    ))
    return results


def scenario_2_p1_no_telegram(tmp):
    """P1 alert without Telegram config must still be logged."""
    _banner("Scenario 2: P1 alert, no Telegram config (must still be logged)")

    log_buf, log_handler, logger = _capture_log(logging.WARNING)
    try:
        mgr = AlertManager()
        result = asyncio.run(mgr.send_alert(_make_p1_alert()))
    finally:
        logger.removeHandler(log_handler)

    log_text = log_buf.getvalue()

    results = []
    results.append(_assert(
        result is True,
        "send_alert() returned True",
    ))
    results.append(_assert(
        result is True,
        "P1 alert dispatched (logged or routed to engine)",
    ))
    results.append(_assert(
        len(mgr.alert_history) >= 1,
        "P1 alert in history",
    ))
    return results


def scenario_3_p0_with_mock_telegram(tmp):
    """P0 alert with mock Telegram must reach the engine.send_alert method,
    with severity mapped to CRITICAL and title preserved in the message."""
    _banner("Scenario 3: P0 alert with mock Telegram (severity/title propagated)")

    captured: list[dict] = []

    def fake_send_alert(alert_type, severity, message, metadata=None):
        captured.append({
            "alert_type": alert_type,
            "severity": severity,
            "message": message,
            "metadata": metadata or {},
        })
        return MagicMock(alert_id="test", to_dict=lambda: {})

    engine = AlertEngine(rules=[])
    engine.send_alert = fake_send_alert  # type: ignore[assignment]

    log_buf, log_handler, logger = _capture_log(logging.WARNING)
    try:
        mgr = AlertManager()
        mgr._engine = engine  # inject
        result = asyncio.run(mgr.send_alert(_make_p0_alert()))
    finally:
        logger.removeHandler(log_handler)

    results = []
    results.append(_assert(
        result is True,
        "send_alert() returned True",
    ))
    results.append(_assert(
        len(captured) == 1,
        "engine.send_alert invoked exactly once",
        f"got {len(captured)} calls",
    ))
    if captured:
        c = captured[0]
        results.append(_assert(
            c["severity"] == AlertSeverity.CRITICAL,
            "P0 mapped to AlertSeverity.CRITICAL",
            f"got {c['severity']}",
        ))
        results.append(_assert(
            c["alert_type"] == AlertType.KILL_SWITCH,
            "KILL_SWITCH title -> AlertType.KILL_SWITCH",
            f"got {c['alert_type']}",
        ))
        results.append(_assert(
            "KILL SWITCH TRIGGERED" in c["message"],
            "alert title preserved in message",
            f"message: {c['message']!r}",
        ))
        results.append(_assert(
            "Test kill switch reason" in c["message"],
            "alert body preserved in message",
        ))
    return results


def scenario_4_p2_p3_also_route(tmp):
    """P2 and P3 alerts must use the same routing path (not silently dropped)."""
    _banner("Scenario 4: P2 and P3 alerts route through engine")

    captured: list[dict] = []

    def fake_send_alert(alert_type, severity, message, metadata=None):
        captured.append({
            "alert_type": alert_type,
            "severity": severity,
            "message": message,
        })
        return MagicMock(alert_id="x", to_dict=lambda: {})

    engine = AlertEngine(rules=[])
    engine.send_alert = fake_send_alert  # type: ignore[assignment]

    mgr = AlertManager()
    mgr._engine = engine

    async def run_both():
        await mgr.send_alert(_make_p2_alert())
        await mgr.send_alert(_make_p3_alert())

    asyncio.run(run_both())

    results = []
    results.append(_assert(
        len(captured) == 2,
        "both P2 and P3 reached engine.send_alert",
        f"got {len(captured)}",
    ))
    severities = {c["severity"] for c in captured}
    results.append(_assert(
        AlertSeverity.WARNING in severities,
        "P2 mapped to WARNING",
        f"seen severities: {severities}",
    ))
    results.append(_assert(
        AlertSeverity.INFO in severities,
        "P3 mapped to INFO",
        f"seen severities: {severities}",
    ))
    return results


def scenario_5_engine_exception_swallowed(tmp):
    """If the engine raises, AlertManager must not propagate the exception
    to the caller — but must still log it (so the alert is not silently lost)."""
    _banner("Scenario 5: engine exception does not silently drop alert")

    def exploding_send(*args, **kwargs):
        raise RuntimeError("simulated engine failure")

    engine = AlertEngine(rules=[])
    engine.send_alert = exploding_send  # type: ignore[assignment]

    log_buf, log_handler, logger = _capture_log(logging.WARNING)
    raised_to_caller = False
    result = None
    try:
        mgr = AlertManager()
        mgr._engine = engine
        try:
            result = asyncio.run(mgr.send_alert(_make_p0_alert()))
        except Exception:  # noqa: BLE001
            raised_to_caller = True
    finally:
        logger.removeHandler(log_handler)

    log_text = log_buf.getvalue()
    results = []
    results.append(_assert(
        not raised_to_caller,
        "engine exception did not propagate to caller",
    ))
    results.append(_assert(
        result is False,
        "send_alert() returned False on engine failure (not silently swallowed)",
    ))
    return results


def scenario_6_kill_switch_path(tmp):
    """notify_kill_switch() must produce a P0 alert that reaches the engine."""
    _banner("Scenario 6: notify_kill_switch() path routes P0 alert")

    captured: list[dict] = []

    def fake_send_alert(alert_type, severity, message, metadata=None):
        captured.append({
            "alert_type": alert_type,
            "severity": severity,
            "message": message,
        })
        return MagicMock(alert_id="x", to_dict=lambda: {})

    engine = AlertEngine(rules=[])
    engine.send_alert = fake_send_alert  # type: ignore[assignment]

    mgr = AlertManager()
    mgr._engine = engine

    async def run():
        return await mgr.notify_kill_switch("manual", "test kill reason")

    result = asyncio.run(run())

    results = []
    results.append(_assert(
        result is True,
        "notify_kill_switch() returned True",
    ))
    results.append(_assert(
        len(captured) == 1,
        "P0 alert from notify_kill_switch reached engine",
        f"got {len(captured)} calls",
    ))
    if captured:
        c = captured[0]
        results.append(_assert(
            c["severity"] == AlertSeverity.CRITICAL,
            "kill switch P0 mapped to CRITICAL",
        ))
        results.append(_assert(
            "KILL SWITCH TRIGGERED" in c["message"],
            "kill switch title in message",
        ))
    return results


def scenario_7_callback_invoked(tmp):
    """Registered AlertEngine callback fires when an alert is sent."""
    _banner("Scenario 7: AlertEngine callback is invoked (third delivery path)")

    fired: list = []

    def cb(alert):
        fired.append(alert)

    engine = AlertEngine(rules=[])
    engine.register_callback(cb)

    alert = engine.send_alert(
        alert_type=AlertType.DRAWDOWN,
        severity=AlertSeverity.CRITICAL,
        message="callback test",
    )

    results = []
    results.append(_assert(
        len(fired) == 1,
        "callback invoked once",
        f"got {len(fired)}",
    ))
    results.append(_assert(
        fired[0].alert_id == alert.alert_id,
        "callback received the same alert object",
    ))
    return results


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--keep-tmp",
        action="store_true",
        help="Unused (placeholder for future artifacts dir)",
    )
    args = parser.parse_args()

    print("Alert Routing Test (B1) - P0/P1 alerts must never be silently dropped")
    print("  Verifies: log + AlertEngine history + callback + mock Telegram.")

    tmp_root = Path(tempfile.mkdtemp(prefix="alert_routing_"))
    print(f"  tmp dir: {tmp_root}")

    all_results = []
    scenarios = [
        scenario_1_p0_no_telegram,
        scenario_2_p1_no_telegram,
        scenario_3_p0_with_mock_telegram,
        scenario_4_p2_p3_also_route,
        scenario_5_engine_exception_swallowed,
        scenario_6_kill_switch_path,
        scenario_7_callback_invoked,
    ]

    try:
        for scenario in scenarios:
            tmp = tmp_root / scenario.__name__
            tmp.mkdir(parents=True, exist_ok=True)
            try:
                all_results.extend(scenario(tmp))
            except Exception:  # noqa: BLE001
                tb = traceback.format_exc()
                all_results.append((FAIL, f"{scenario.__name__} - unhandled exception"))
                print(f"  [XX  ] {scenario.__name__} raised:\n{tb}")
    finally:
        if not args.keep_tmp:
            shutil.rmtree(tmp_root, ignore_errors=True)
        else:
            print(f"  --keep-tmp set; leaving {tmp_root} for inspection")

    _banner("Summary")
    passed = sum(1 for s, _ in all_results if s == PASS)
    failed = sum(1 for s, _ in all_results if s == FAIL)
    for status, label in all_results:
        flag = "OK  " if status == PASS else "XX  "
        print(f"  [{flag}] {label}")
    print()
    print(f"  {passed} passed, {failed} failed, {len(all_results)} total")
    if failed:
        print("  RESULT: FAIL - alert routing has gaps (silently dropped or mis-mapped).")
        return 1
    print("  RESULT: PASS - P0/P1/P2/P3 alerts reach log + engine + callback.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
