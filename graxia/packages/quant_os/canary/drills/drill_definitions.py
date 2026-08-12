"""Phase 8 — Drill definitions for demo campaign."""
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum


class DrillType(Enum):
    KILL_SWITCH = "kill_switch"
    MT5_DISCONNECT = "mt5_disconnect"
    STALE_TICK = "stale_tick"
    SPREAD_SHOCK = "spread_shock"
    CONTRACT_MISMATCH = "contract_mismatch"
    POSITION_INJECTION = "position_injection"
    ORDER_TIMEOUT = "order_timeout"
    MISSING_STOP = "missing_stop"
    RESTART_RECOVERY = "restart_recovery"
    ALERT_FAILURE = "alert_failure"


@dataclass
class DrillResult:
    drill_type: DrillType
    passed: bool
    artifact_path: str
    expected_behavior: str
    observed_behavior: str
    duration_seconds: float
    timestamp: datetime = field(default_factory=datetime.utcnow)


@dataclass
class DrillDefinition:
    drill_type: DrillType
    name: str
    description: str
    preconditions: list[str]
    steps: list[str]
    expected_outcome: str
    artifact_requirements: list[str]


DRILL_CATALOG = {
    DrillType.KILL_SWITCH: DrillDefinition(
        drill_type=DrillType.KILL_SWITCH,
        name="Kill-Switch Activation",
        description="Verify kill switch blocks all new orders",
        preconditions=["Kill switch file exists", "Demo account active"],
        steps=[
            "Activate kill switch",
            "Attempt to submit order",
            "Verify order is rejected",
            "Deactivate kill switch",
            "Verify orders can be submitted again",
        ],
        expected_outcome="Orders blocked while kill switch active, allowed after deactivation",
        artifact_requirements=["kill_switch_log", "order_rejection_log"],
    ),
    DrillType.MT5_DISCONNECT: DrillDefinition(
        drill_type=DrillType.MT5_DISCONNECT,
        name="MT5 Terminal Disconnect",
        description="Verify graceful handling of MT5 disconnect",
        preconditions=["MT5 connection active"],
        steps=[
            "Disconnect MT5 terminal",
            "Verify system detects disconnection",
            "Verify no orders sent while disconnected",
            "Reconnect MT5 terminal",
            "Verify system resumes normal operation",
        ],
        expected_outcome="System detects disconnect, blocks orders, resumes after reconnect",
        artifact_requirements=["disconnect_log", "recovery_log"],
    ),
    DrillType.STALE_TICK: DrillDefinition(
        drill_type=DrillType.STALE_TICK,
        name="Stale-Tick Injection",
        description="Verify stale tick detection and rejection",
        preconditions=["Feed active", "Stale threshold configured"],
        steps=[
            "Inject stale tick data",
            "Verify system detects staleness",
            "Verify order is rejected due to stale data",
            "Resume fresh tick feed",
            "Verify system accepts fresh ticks",
        ],
        expected_outcome="Stale ticks rejected, fresh ticks accepted",
        artifact_requirements=["stale_detection_log", "order_rejection_log"],
    ),
    DrillType.SPREAD_SHOCK: DrillDefinition(
        drill_type=DrillType.SPREAD_SHOCK,
        name="Spread-Shock Injection",
        description="Verify wide spread detection and order rejection",
        preconditions=["Spread monitor active"],
        steps=[
            "Inject wide spread (e.g., 10x normal)",
            "Verify system detects wide spread",
            "Verify order is rejected",
            "Resume normal spread",
            "Verify system accepts orders again",
        ],
        expected_outcome="Wide spreads rejected, normal spreads accepted",
        artifact_requirements=["spread_monitor_log", "order_rejection_log"],
    ),
}
