"""Phase 10 — Controlled Expansion tests."""

from graxia.packages.quant_os.expansion.planner import ExpansionPhase, ExpansionPlanner
from graxia.packages.quant_os.expansion.tracker import ExpansionTracker


class TestExpansionPlanner:
    def test_create_planner(self):
        planner = ExpansionPlanner()
        steps = planner.list_steps()
        assert len(steps) == 5

    def test_get_current_step(self):
        planner = ExpansionPlanner()
        current = planner.get_current_step()
        assert current is not None
        assert current.phase == ExpansionPhase.PHASE_1

    def test_get_step_by_phase(self):
        planner = ExpansionPlanner()
        step = planner.get_step(ExpansionPhase.PHASE_2)
        assert step is not None
        assert "EURUSD" in step.symbols

    def test_can_advance_initial(self):
        planner = ExpansionPlanner()
        can, reason = planner.can_advance()
        assert can is True

    def test_cannot_advance_with_unpassed_gates(self):
        from graxia.packages.quant_os.expansion.planner import ExpansionStatus

        planner = ExpansionPlanner()
        planner.get_step(ExpansionPhase.PHASE_1).status = ExpansionStatus.IN_PROGRESS
        can, reason = planner.can_advance()
        assert can is False
        assert "Gates pending" in reason

    def test_can_advance_after_gates_pass(self):
        from graxia.packages.quant_os.expansion.planner import ExpansionStatus

        planner = ExpansionPlanner()
        planner.get_step(ExpansionPhase.PHASE_1).status = ExpansionStatus.IN_PROGRESS
        for gate in planner.get_step(ExpansionPhase.PHASE_1).evidence_gates:
            gate.passed = True
        can, reason = planner.can_advance()
        assert can is True

    def test_step_to_dict(self):
        planner = ExpansionPlanner()
        step = planner.get_step(ExpansionPhase.PHASE_1)
        d = step.to_dict()
        assert "phase" in d
        assert "evidence_gates" in d

    def test_planner_to_dict(self):
        planner = ExpansionPlanner()
        d = planner.to_dict()
        assert "steps" in d
        assert len(d["steps"]) == 5

    def test_phase_1_risk_limits(self):
        planner = ExpansionPlanner()
        step = planner.get_step(ExpansionPhase.PHASE_1)
        assert step.risk_limits["risk_per_trade_bps"] == 5
        assert step.risk_limits["max_open_positions"] == 1

    def test_phase_5_has_most_symbols(self):
        planner = ExpansionPlanner()
        step = planner.get_step(ExpansionPhase.PHASE_5)
        assert len(step.symbols) == 4


class TestExpansionTracker:
    def test_get_status(self):
        tracker = ExpansionTracker()
        report = tracker.get_status()
        assert report.steps_total == 5
        assert report.steps_completed == 0

    def test_complete_gate(self):
        tracker = ExpansionTracker()
        ok = tracker.complete_gate(ExpansionPhase.PHASE_1, "Kill Switch Verified", "tested")
        assert ok is True

    def test_complete_gate_nonexistent(self):
        tracker = ExpansionTracker()
        ok = tracker.complete_gate(ExpansionPhase.PHASE_1, "Nonexistent Gate")
        assert ok is False

    def test_start_phase(self):
        tracker = ExpansionTracker()
        ok = tracker.start_phase(ExpansionPhase.PHASE_1)
        assert ok is True

    def test_complete_phase(self):
        tracker = ExpansionTracker()
        tracker.start_phase(ExpansionPhase.PHASE_1)
        for gate in [
            "Micro-Live Review Pass",
            "5-Day Campaign Complete",
            "Incident Drills Pass",
            "Kill Switch Verified",
            "Reconciliation Verified",
        ]:
            tracker.complete_gate(ExpansionPhase.PHASE_1, gate, "tested")
        ok = tracker.complete_phase(ExpansionPhase.PHASE_1)
        assert ok is True

    def test_cannot_complete_without_gates(self):
        tracker = ExpansionTracker()
        tracker.start_phase(ExpansionPhase.PHASE_1)
        ok = tracker.complete_phase(ExpansionPhase.PHASE_1)
        assert ok is False

    def test_export_report(self):
        tracker = ExpansionTracker()
        import tempfile

        with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as f:
            tracker.export_report(f.name)
            import json

            data = json.load(open(f.name))
            assert "steps_completed" in data
        import os

        os.unlink(f.name)

    def test_report_summary(self):
        tracker = ExpansionTracker()
        report = tracker.get_status()
        assert report.overall_status == "ready"
        assert report.next_action == "Ready to start"
