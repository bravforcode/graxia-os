"""
Expansion Tracker — track expansion progress and generate reports.
"""
from dataclasses import dataclass, field
from typing import List, Dict, Optional
import json
import os
from datetime import datetime, timezone
from .planner import ExpansionPlanner, ExpansionStep, ExpansionPhase, ExpansionStatus


@dataclass
class ExpansionReport:
    report_id: str
    created_at: str
    current_phase: str
    steps_completed: int
    steps_total: int
    overall_status: str
    next_action: str
    details: List[Dict] = field(default_factory=list)
    
    def to_dict(self) -> dict:
        return {
            "report_id": self.report_id,
            "created_at": self.created_at,
            "current_phase": self.current_phase,
            "steps_completed": self.steps_completed,
            "steps_total": self.steps_total,
            "overall_status": self.overall_status,
            "next_action": self.next_action,
            "details": self.details,
        }


class ExpansionTracker:
    """Track expansion progress and generate reports."""
    
    def __init__(self):
        self._planner = ExpansionPlanner()
        self._history: List[Dict] = []
    
    def get_status(self) -> ExpansionReport:
        steps = self._planner.list_steps()
        completed = sum(1 for s in steps if s.status == ExpansionStatus.COMPLETED)
        current = self._planner.get_current_step()
        
        can_advance, reason = self._planner.can_advance()
        
        details = []
        for step in steps:
            details.append({
                "phase": step.phase.value,
                "status": step.status.value,
                "gates_passed": sum(1 for g in step.evidence_gates if g.passed),
                "gates_total": len(step.evidence_gates),
                "symbols": step.symbols,
            })
        
        return ExpansionReport(
            report_id=f"exp_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}",
            created_at=datetime.now(timezone.utc).isoformat(),
            current_phase=current.phase.value if current else "completed",
            steps_completed=completed,
            steps_total=len(steps),
            overall_status="ready" if can_advance else "blocked",
            next_action=reason,
            details=details,
        )
    
    def complete_gate(self, phase: ExpansionPhase, gate_name: str, evidence: str = "") -> bool:
        step = self._planner.get_step(phase)
        if step is None:
            return False
        
        for gate in step.evidence_gates:
            if gate.name == gate_name:
                gate.passed = True
                gate.evidence = evidence
                return True
        return False
    
    def start_phase(self, phase: ExpansionPhase) -> bool:
        step = self._planner.get_step(phase)
        if step is None:
            return False
        
        can_advance, reason = self._planner.can_advance()
        if not can_advance:
            return False
        
        step.status = ExpansionStatus.IN_PROGRESS
        step.started_at = datetime.now(timezone.utc).isoformat()
        return True
    
    def complete_phase(self, phase: ExpansionPhase) -> bool:
        step = self._planner.get_step(phase)
        if step is None:
            return False
        
        if not step.all_gates_passed():
            return False
        
        step.status = ExpansionStatus.COMPLETED
        step.completed_at = datetime.now(timezone.utc).isoformat()
        return True
    
    def export_report(self, path: str) -> None:
        report = self.get_status()
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, 'w') as f:
            json.dump(report.to_dict(), f, indent=2)
