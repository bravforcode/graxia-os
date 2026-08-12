"""BE-P8.2 — AST isolation check for shadow code.

No execution API imports allowed in shadow modules.
"""
import ast
from pathlib import Path


SHADOW_DIR = Path(__file__).parent
FORBIDDEN_MODULES = [
    "execution", "order", "trade", "broker.adapter",
]
FORBIDDEN_FUNCTION_NAMES = [
    "order_send", "order_check", "order_calc_margin",
]

# Test files may reference these for AST scanning, but production code must not
PRODUCTION_FILES = [
    "pipeline.py",
    "broker_observed_runner.py",
    "shadow_pipeline.py",
    "shadow_campaign.py",
    "shadow_pass_criteria.py",
    "shadow_telemetry.py",
    "event_risk_gate.py",
    "market_health.py",
    "failure_rules.py",
    "telemetry.py",
]


def test_no_execution_imports_in_shadow_production():
    """Shadow production code must never import execution APIs."""
    for fname in PRODUCTION_FILES:
        fpath = SHADOW_DIR / fname
        if not fpath.exists():
            continue
        src = fpath.read_text(encoding="utf-8")
        tree = ast.parse(src)
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom) and node.module:
                mod = node.module.lower()
                for forbidden in FORBIDDEN_MODULES:
                    assert forbidden not in mod, (
                        f"Forbidden import '{mod}' (matches '{forbidden}') in {fname}"
                    )
            if isinstance(node, ast.Call):
                if isinstance(node.func, ast.Name):
                    for forbidden in FORBIDDEN_FUNCTION_NAMES:
                        assert node.func.id != forbidden, (
                            f"Forbidden call '{forbidden}' in {fname}"
                        )


def test_broker_observed_runner_isolation():
    """broker_observed_runner.py must not import execution modules."""
    fpath = SHADOW_DIR / "broker_observed_runner.py"
    if not fpath.exists():
        return
    src = fpath.read_text(encoding="utf-8")
    tree = ast.parse(src)
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module:
            mod = node.module.lower()
            assert "execution" not in mod, f"Execution import in broker_observed_runner: {mod}"
            assert "trade" not in mod, f"Trade import in broker_observed_runner: {mod}"
