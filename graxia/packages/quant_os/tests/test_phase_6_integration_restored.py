"""Phase 6 integration tests — shadow mode and market health.

RESTORED from deleted test_phase_6_integration.py (BE-P8 commit 56113fd).
Migrated to current API. order_send check scoped to production code only.
"""
from graxia.packages.quant_os.shadow.pipeline import ShadowPipeline


def test_shadow_pipeline_exists():
    """ShadowPipeline must exist and instantiate."""
    pipeline = ShadowPipeline()
    assert pipeline is not None


def test_shadow_pipeline_has_required_methods():
    """ShadowPipeline must have required methods."""
    pipeline = ShadowPipeline()
    assert hasattr(pipeline, 'start_session')
    assert hasattr(pipeline, 'end_session')
    assert hasattr(pipeline, 'process_signal')
    assert hasattr(pipeline, 'open_position')
    assert hasattr(pipeline, 'check_position_exit')


def test_shadow_results_directory_exists():
    """Shadow results directory must exist."""
    from pathlib import Path
    results_dir = Path(r"C:\Users\menum\graxia os\graxia\packages\quant_os\shadow_results")
    assert results_dir.exists()


def test_market_health_machine_exists():
    """MarketHealthMachine must exist."""
    from graxia.packages.quant_os.shadow.market_health import MarketHealthMachine
    machine = MarketHealthMachine()
    check = machine.check(True, True, True, True)
    assert check.state.value == "healthy"


def test_event_risk_gate_exists():
    """EventRiskGate must exist."""
    from graxia.packages.quant_os.shadow.event_risk_gate import EventRiskGate
    gate = EventRiskGate()
    from datetime import datetime
    result = gate.check(datetime.now(), [])
    assert not result.blocked


def test_no_order_send_in_shadow_production_code():
    """Shadow production code must not call order_send."""
    import ast
    from pathlib import Path
    shadow_dir = Path(r"C:\Users\menum\graxia os\graxia\packages\quant_os\shadow")
    if shadow_dir.exists():
        for py_file in shadow_dir.glob("*.py"):
            # Skip test files
            if py_file.name.startswith("test_"):
                continue
            src = py_file.read_text(encoding="utf-8")
            tree = ast.parse(src)
            for node in ast.walk(tree):
                if isinstance(node, ast.Call):
                    if isinstance(node.func, ast.Name) and node.func.id == "order_send":
                        assert False, f"order_send() call found in {py_file.name}"
                    if isinstance(node.func, ast.Attribute) and node.func.attr == "order_send":
                        assert False, f"order_send() call found in {py_file.name}"
