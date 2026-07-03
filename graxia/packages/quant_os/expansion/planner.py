"""
Controlled Expansion Planner — define expansion steps with evidence gates.

Expansion order per master plan:
1. One symbol (XAUUSD) — micro-live
2. Two symbols (XAUUSD + EURUSD)
3. Three symbols
4. Multiple strategies
5. Portfolio allocation

Each step requires passing evidence gates before proceeding.
"""

from dataclasses import dataclass, field
from enum import Enum


class ExpansionPhase(Enum):
    PHASE_1 = "one_symbol_micro_live"
    PHASE_2 = "two_symbols"
    PHASE_3 = "three_symbols"
    PHASE_4 = "multiple_strategies"
    PHASE_5 = "portfolio_allocation"


class ExpansionStatus(Enum):
    NOT_STARTED = "not_started"
    IN_PROGRESS = "in_progress"
    BLOCKED = "blocked"
    COMPLETED = "completed"


@dataclass
class EvidenceGate:
    name: str
    description: str
    passed: bool = False
    evidence: str = ""

    def to_dict(self) -> dict:
        return {"name": self.name, "description": self.description, "passed": self.passed, "evidence": self.evidence}


@dataclass
class ExpansionStep:
    phase: ExpansionPhase
    description: str
    status: ExpansionStatus = ExpansionStatus.NOT_STARTED
    symbols: list[str] = field(default_factory=list)
    strategies: list[str] = field(default_factory=list)
    risk_limits: dict[str, float] = field(default_factory=dict)
    evidence_gates: list[EvidenceGate] = field(default_factory=list)
    started_at: str | None = None
    completed_at: str | None = None

    def all_gates_passed(self) -> bool:
        return all(g.passed for g in self.evidence_gates)

    def to_dict(self) -> dict:
        return {
            "phase": self.phase.value,
            "description": self.description,
            "status": self.status.value,
            "symbols": self.symbols,
            "strategies": self.strategies,
            "risk_limits": self.risk_limits,
            "evidence_gates": [g.to_dict() for g in self.evidence_gates],
            "started_at": self.started_at,
            "completed_at": self.completed_at,
        }


class ExpansionPlanner:
    """Define and track controlled expansion steps."""

    def __init__(self):
        self._steps: list[ExpansionStep] = self._create_default_steps()

    def _create_default_steps(self) -> list[ExpansionStep]:
        return [
            ExpansionStep(
                phase=ExpansionPhase.PHASE_1,
                description="One symbol (XAUUSD) — micro-live with tightest risk limits",
                symbols=["XAUUSD"],
                strategies=["liquidity_sweep_locked"],
                risk_limits={
                    "risk_per_trade_bps": 5,
                    "max_daily_loss_bps": 20,
                    "max_weekly_loss_bps": 50,
                    "max_total_drawdown_bps": 100,
                    "max_open_positions": 1,
                    "max_orders_per_day": 2,
                },
                evidence_gates=[
                    EvidenceGate("Micro-Live Review Pass", "Phase 9 verdict = APPROVED"),
                    EvidenceGate("5-Day Campaign Complete", "Campaign results collected"),
                    EvidenceGate("Incident Drills Pass", "11/11 drills pass"),
                    EvidenceGate("Kill Switch Verified", "Kill switch tested and working"),
                    EvidenceGate("Reconciliation Verified", "Post-fill verification complete"),
                ],
            ),
            ExpansionStep(
                phase=ExpansionPhase.PHASE_2,
                description="Two symbols (XAUUSD + EURUSD) — expand with same strategy",
                symbols=["XAUUSD", "EURUSD"],
                strategies=["liquidity_sweep_locked"],
                risk_limits={
                    "risk_per_trade_bps": 5,
                    "max_daily_loss_bps": 30,
                    "max_weekly_loss_bps": 75,
                    "max_total_drawdown_bps": 150,
                    "max_open_positions": 2,
                    "max_orders_per_day": 4,
                },
                evidence_gates=[
                    EvidenceGate("Phase 1 Complete", "Phase 1 evidence collected"),
                    EvidenceGate("EURUSD Data Clean", "EURUSD contract and data verified"),
                    EvidenceGate("EURUSD Strategy Validated", "EURUSD hypothesis tested"),
                    EvidenceGate("Cross-Symbol Risk OK", "Multi-symbol risk checks pass"),
                ],
            ),
            ExpansionStep(
                phase=ExpansionPhase.PHASE_3,
                description="Three symbols — add GBPUSD or USDJPY",
                symbols=["XAUUSD", "EURUSD", "GBPUSD"],
                strategies=["liquidity_sweep_locked"],
                risk_limits={
                    "risk_per_trade_bps": 8,
                    "max_daily_loss_bps": 40,
                    "max_weekly_loss_bps": 100,
                    "max_total_drawdown_bps": 200,
                    "max_open_positions": 3,
                    "max_orders_per_day": 6,
                },
                evidence_gates=[
                    EvidenceGate("Phase 2 Complete", "Phase 2 evidence collected"),
                    EvidenceGate("Third Symbol Validated", "Third symbol tested"),
                    EvidenceGate("Portfolio Risk OK", "Portfolio-level risk checks pass"),
                ],
            ),
            ExpansionStep(
                phase=ExpansionPhase.PHASE_4,
                description="Multiple strategies — add second strategy",
                symbols=["XAUUSD", "EURUSD", "GBPUSD"],
                strategies=["liquidity_sweep_locked", "mean_reversion_bollinger"],
                risk_limits={
                    "risk_per_trade_bps": 10,
                    "max_daily_loss_bps": 50,
                    "max_weekly_loss_bps": 150,
                    "max_total_drawdown_bps": 300,
                    "max_open_positions": 4,
                    "max_orders_per_day": 8,
                },
                evidence_gates=[
                    EvidenceGate("Phase 3 Complete", "Phase 3 evidence collected"),
                    EvidenceGate("Second Strategy Validated", "Second strategy tested"),
                    EvidenceGate("Strategy Correlation OK", "Strategies not correlated"),
                ],
            ),
            ExpansionStep(
                phase=ExpansionPhase.PHASE_5,
                description="Portfolio allocation — full production configuration",
                symbols=["XAUUSD", "EURUSD", "GBPUSD", "USDJPY"],
                strategies=["liquidity_sweep_locked", "mean_reversion_bollinger", "multi_timeframe_momentum"],
                risk_limits={
                    "risk_per_trade_bps": 15,
                    "max_daily_loss_bps": 75,
                    "max_weekly_loss_bps": 200,
                    "max_total_drawdown_bps": 400,
                    "max_open_positions": 5,
                    "max_orders_per_day": 10,
                },
                evidence_gates=[
                    EvidenceGate("Phase 4 Complete", "Phase 4 evidence collected"),
                    EvidenceGate("All Strategies Validated", "All strategies tested"),
                    EvidenceGate("Portfolio Optimization OK", "Allocation optimized"),
                    EvidenceGate("Final Review Pass", "Full review complete"),
                ],
            ),
        ]

    def get_current_step(self) -> ExpansionStep | None:
        for step in self._steps:
            if step.status in (ExpansionStatus.NOT_STARTED, ExpansionStatus.IN_PROGRESS):
                return step
        return None

    def get_step(self, phase: ExpansionPhase) -> ExpansionStep | None:
        for step in self._steps:
            if step.phase == phase:
                return step
        return None

    def list_steps(self) -> list[ExpansionStep]:
        return self._steps

    def can_advance(self) -> tuple[bool, str]:
        current = self.get_current_step()
        if current is None:
            return False, "All phases completed"
        if current.status == ExpansionStatus.NOT_STARTED:
            return True, "Ready to start"
        if current.status == ExpansionStatus.IN_PROGRESS:
            if current.all_gates_passed():
                return True, "All gates passed, ready to complete"
            failed = [g.name for g in current.evidence_gates if not g.passed]
            return False, f"Gates pending: {', '.join(failed)}"
        if current.status == ExpansionStatus.BLOCKED:
            return False, "Phase blocked"
        return False, "Unknown status"

    def to_dict(self) -> dict:
        return {
            "steps": [s.to_dict() for s in self._steps],
            "current_phase": self.get_current_step().phase.value if self.get_current_step() else "completed",
        }
