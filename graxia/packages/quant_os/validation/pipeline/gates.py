"""Automated pass/fail gate logic for validation pipeline."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum

from .config import PipelineConfig


class GateStatus(Enum):
    PASS = "PASS"
    FAIL = "FAIL"
    WARN = "WARN"
    SKIP = "SKIP"


@dataclass
class GateResult:
    """Result of a single gate check."""

    name: str
    status: GateStatus
    metric: float = 0.0
    threshold: float = 0.0
    details: str = ""

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "status": self.status.value,
            "metric": round(self.metric, 6),
            "threshold": round(self.threshold, 6),
            "details": self.details,
        }


@dataclass
class GateSummary:
    """Aggregated gate results."""

    gates: list[GateResult] = field(default_factory=list)
    overall: GateStatus = GateStatus.SKIP

    def to_dict(self) -> dict:
        return {
            "overall": self.overall.value,
            "gates": [g.to_dict() for g in self.gates],
            "pass_count": sum(1 for g in self.gates if g.status == GateStatus.PASS),
            "fail_count": sum(1 for g in self.gates if g.status == GateStatus.FAIL),
            "total": len(self.gates),
        }


class GateEngine:
    """Automated gate evaluation."""

    def __init__(self, config: PipelineConfig):
        self.config = config

    def evaluate(
        self,
        wfa_result: dict | None = None,
        mc_result: dict | None = None,
        dsr_result: dict | None = None,
        pbo_result: dict | None = None,
        stress_result: dict | None = None,
        bootstrap_result: dict | None = None,
    ) -> GateSummary:
        """Evaluate all gates from pipeline results."""
        gates = []

        # Walk-Forward Analysis gates
        if wfa_result:
            gates.extend(self._eval_wfa(wfa_result))

        # Monte Carlo gates
        if mc_result:
            gates.extend(self._eval_mc(mc_result))

        # DSR gate
        if dsr_result:
            gates.append(self._eval_dsr(dsr_result))

        # PBO gate
        if pbo_result:
            gates.append(self._eval_pbo(pbo_result))

        # Stress test gate
        if stress_result:
            gates.append(self._eval_stress(stress_result))

        # Bootstrap gate
        if bootstrap_result:
            gates.extend(self._eval_bootstrap(bootstrap_result))

        # Overall: PASS if all pass, FAIL if any fail, WARN otherwise
        if not gates:
            overall = GateStatus.SKIP
        elif any(g.status == GateStatus.FAIL for g in gates):
            overall = GateStatus.FAIL
        elif any(g.status == GateStatus.WARN for g in gates):
            overall = GateStatus.WARN
        else:
            overall = GateStatus.PASS

        return GateSummary(gates=gates, overall=overall)

    def _eval_wfa(self, r: dict) -> list[GateResult]:
        gates = []
        oos_pos = r.get("oos_consistency", 0.0)
        gates.append(
            GateResult(
                name="wfa_oos_positive",
                status=GateStatus.PASS if oos_pos >= self.config.wfa_min_oos_positive else GateStatus.FAIL,
                metric=oos_pos,
                threshold=self.config.wfa_min_oos_positive,
                details=f"{oos_pos:.1%} OOS windows positive",
            )
        )

        wfe = r.get("walk_forward_efficiency", 0.0)
        gates.append(
            GateResult(
                name="wfa_wfe",
                status=GateStatus.PASS if wfe >= self.config.wfa_min_wfe else GateStatus.FAIL,
                metric=wfe,
                threshold=self.config.wfa_min_wfe,
                details=f"WFE={wfe:.4f}",
            )
        )

        degradation = r.get("overfitting_score", 0.0)
        gates.append(
            GateResult(
                name="wfa_degradation",
                status=GateStatus.PASS if degradation <= self.config.wfa_max_degradation else GateStatus.FAIL,
                metric=degradation,
                threshold=self.config.wfa_max_degradation,
                details=f"Degradation={degradation:.1%}",
            )
        )
        return gates

    def _eval_mc(self, r: dict) -> list[GateResult]:
        gates = []
        ruin = r.get("prob_ruin", 1.0)
        gates.append(
            GateResult(
                name="mc_ruin_prob",
                status=GateStatus.PASS if ruin < self.config.mc_max_ruin_prob else GateStatus.FAIL,
                metric=ruin,
                threshold=self.config.mc_max_ruin_prob,
                details=f"P(Ruin)={ruin:.2%}",
            )
        )

        dd_p95 = r.get("p95_max_dd_pct", 1.0)
        gates.append(
            GateResult(
                name="mc_drawdown_p95",
                status=GateStatus.PASS if dd_p95 < self.config.mc_max_dd_p95 else GateStatus.WARN,
                metric=dd_p95,
                threshold=self.config.mc_max_dd_p95,
                details=f"95th percentile DD={dd_p95:.1%}",
            )
        )
        return gates

    def _eval_dsr(self, r: dict) -> GateResult:
        dsr = r.get("deflated_sharpe", 0.0)
        return GateResult(
            name="deflated_sharpe",
            status=GateStatus.PASS if dsr > self.config.dsr_min_value else GateStatus.FAIL,
            metric=dsr,
            threshold=self.config.dsr_min_value,
            details=f"DSR={dsr:.4f}",
        )

    def _eval_pbo(self, r: dict) -> GateResult:
        pbo = r.get("pbo", 1.0)
        return GateResult(
            name="pbo_overfitting",
            status=GateStatus.PASS if pbo < self.config.pbo_max_value else GateStatus.FAIL,
            metric=pbo,
            threshold=self.config.pbo_max_value,
            details=f"PBO={pbo:.4f}",
        )

    def _eval_stress(self, r: dict) -> GateResult:
        pos_rate = r.get("positive_rate", 0.0)
        return GateResult(
            name="stress_test",
            status=GateStatus.PASS if pos_rate >= self.config.stress_min_positive else GateStatus.FAIL,
            metric=pos_rate,
            threshold=self.config.stress_min_positive,
            details=f"{pos_rate:.1%} scenarios positive",
        )

    def _eval_bootstrap(self, r: dict) -> list[GateResult]:
        gates = []
        ci_lower = r.get("sharpe_ci_lower", -999)
        gates.append(
            GateResult(
                name="bootstrap_sharpe_ci",
                status=GateStatus.PASS if ci_lower > self.config.bootstrap_sharpe_ci_lower_min else GateStatus.FAIL,
                metric=ci_lower,
                threshold=self.config.bootstrap_sharpe_ci_lower_min,
                details=f"Sharpe CI lower={ci_lower:.4f}",
            )
        )
        return gates
