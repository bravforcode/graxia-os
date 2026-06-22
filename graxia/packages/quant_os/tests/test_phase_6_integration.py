"""Phase 6 integration tests — shadow mode and market health."""
from graxia.packages.quant_os.shadow.pipeline import ShadowPipeline
from graxia.packages.quant_os.shadow.telemetry import ShadowTelemetry


def test_shadow_pipeline_exists():
    """ShadowPipeline must exist and instantiate."""
    pipeline = ShadowPipeline()
    assert pipeline is not None


def test_shadow_telemetry_exists():
    """ShadowTelemetry must exist and instantiate."""
    telemetry = ShadowTelemetry()
    assert telemetry is not None


def test_shadow_pipeline_has_required_methods():
    """ShadowPipeline must have required methods."""
    pipeline = ShadowPipeline()
    assert hasattr(pipeline, 'start_session')
    assert hasattr(pipeline, 'end_session')
    assert hasattr(pipeline, 'process_signal')


def test_shadow_telemetry_has_required_methods():
    """ShadowTelemetry must have required methods."""
    telemetry = ShadowTelemetry()
    assert hasattr(telemetry, 'record_signal_created')
    assert hasattr(telemetry, 'record_signal_rejected')
    assert hasattr(telemetry, 'export_json')


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
    from datetime import datetime, timedelta
    result = gate.check(datetime.now(), [])
    assert not result.blocked


def test_no_order_send_in_shadow_path():
    """Shadow path must not import order_send."""
    import ast
    from pathlib import Path
    shadow_dir = Path(r"C:\Users\menum\graxia os\graxia\packages\quant_os\shadow")
    if shadow_dir.exists():
        for py_file in shadow_dir.glob("*.py"):
            src = py_file.read_text(encoding="utf-8")
            if "order_send" in src:
                assert False, f"order_send found in {py_file.name}"
