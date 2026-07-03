"""Phase BE-P10 — Drill definitions for incident drills."""
from dataclasses import dataclass
from enum import Enum


class DrillType(Enum):
    KILL_SWITCH = "kill_switch"
    MT5_DISCONNECT = "mt5_disconnect"
    STALE_TICK = "stale_tick"
    WIDE_SPREAD = "wide_spread"
    CLOCK_DRIFT = "clock_drift"
    WRONG_BROKER_PROFILE = "wrong_broker_profile"
    CONTRACT_CHANGE = "contract_change"
    ORDER_TIMEOUT = "order_timeout"
    BROKER_REJECTION = "broker_rejection"
    MISSING_SL_TP = "missing_sl_tp"
    MANUAL_POSITION_MISMATCH = "manual_position_mismatch"
    EVENT_BLACKOUT = "event_blackout"
    RESTART_RECOVERY = "restart_recovery"


@dataclass
class DrillResult:
    drill_type: str
    detection_time_ms: float
    new_order_blocked: bool
    existing_position_behavior: str
    alert_delivered: bool
    recovery_verified: bool
    evidence_retained: bool
    postmortem_status: str  # open, resolved
    passed: bool = False


DRILL_REQUIREMENTS = {
    DrillType.KILL_SWITCH: {
        "description": "Activate kill switch and verify all orders blocked",
        "detection_time_ms_max": 100,
        "must_block": True,
    },
    DrillType.MT5_DISCONNECT: {
        "description": "Disconnect MT5 and verify stale feed detection",
        "detection_time_ms_max": 5000,
        "must_block": True,
    },
    DrillType.STALE_TICK: {
        "description": "Feed stale ticks and verify rejection",
        "detection_time_ms_max": 5000,
        "must_block": True,
    },
    DrillType.WIDE_SPREAD: {
        "description": "Feed wide spread and verify spread shock block",
        "detection_time_ms_max": 1000,
        "must_block": True,
    },
    DrillType.CLOCK_DRIFT: {
        "description": "Simulate clock drift and verify detection",
        "detection_time_ms_max": 1000,
        "must_block": True,
    },
    DrillType.WRONG_BROKER_PROFILE: {
        "description": "Connect wrong broker and verify rejection",
        "detection_time_ms_max": 100,
        "must_block": True,
    },
    DrillType.CONTRACT_CHANGE: {
        "description": "Detect contract property change",
        "detection_time_ms_max": 5000,
        "must_block": False,
    },
    DrillType.ORDER_TIMEOUT: {
        "description": "Simulate order timeout and verify reconcile",
        "detection_time_ms_max": 30000,
        "must_block": True,
    },
    DrillType.BROKER_REJECTION: {
        "description": "Simulate broker rejection and verify safe state",
        "detection_time_ms_max": 5000,
        "must_block": True,
    },
    DrillType.MISSING_SL_TP: {
        "description": "Verify missing SL triggers CRITICAL_INCIDENT",
        "detection_time_ms_max": 100,
        "must_block": True,
    },
    DrillType.MANUAL_POSITION_MISMATCH: {
        "description": "Detect manual position change and enter safe mode",
        "detection_time_ms_max": 5000,
        "must_block": True,
    },
    DrillType.EVENT_BLACKOUT: {
        "description": "Verify high-impact event blocks entries",
        "detection_time_ms_max": 1000,
        "must_block": True,
    },
    DrillType.RESTART_RECOVERY: {
        "description": "Restart system and verify state recovery",
        "detection_time_ms_max": 10000,
        "must_block": False,
    },
}


class DrillExecutor:
    """Execute drills and track results."""

    def __init__(self):
        self._results: list[DrillResult] = []

    def execute_drill(self, drill_type: DrillType, result: DrillResult) -> None:
        req = DRILL_REQUIREMENTS.get(drill_type, {})
        result.passed = (
            result.detection_time_ms <= req.get("detection_time_ms_max", 999999) and
            result.new_order_blocked == req.get("must_block", False) and
            result.alert_delivered and
            result.recovery_verified and
            result.evidence_retained
        )
        self._results.append(result)

    def get_results(self) -> list[DrillResult]:
        return self._results.copy()

    def get_passed(self) -> list[DrillResult]:
        return [r for r in self._results if r.passed]

    def get_failed(self) -> list[DrillResult]:
        return [r for r in self._results if not r.passed]

    def summary(self) -> dict:
        total = len(self._results)
        passed = sum(1 for r in self._results if r.passed)
        return {
            "total_drills": total,
            "passed": passed,
            "failed": total - passed,
            "all_passed": passed == total,
        }
