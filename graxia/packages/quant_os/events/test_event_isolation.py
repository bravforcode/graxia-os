"""Phase BE-P3 — Event module isolation. Must not import execution modules."""
import ast
from pathlib import Path


FORBIDDEN_IMPORTS = {
    "order_send", "order_check", "order_calc_margin",
    "positions_get", "orders_get", "history_deals_get",
}


def test_event_gate_no_execution_imports():
    """event_gate.py must not import execution modules."""
    path = Path(__file__).parent / "event_gate.py"
    tree = ast.parse(path.read_text())

    for node in ast.walk(tree):
        if isinstance(node, (ast.Import, ast.ImportFrom)):
            if isinstance(node, ast.ImportFrom) and node.module:
                for forbidden in FORBIDDEN_IMPORTS:
                    assert forbidden not in node.module, \
                        f"event_gate.py imports {forbidden}"
            if isinstance(node, ast.Import):
                for alias in node.names:
                    for forbidden in FORBIDDEN_IMPORTS:
                        assert forbidden not in alias.name, \
                            f"event_gate.py imports {forbidden}"


def test_market_health_no_execution_imports():
    """market_health.py must not import execution modules."""
    path = Path(__file__).parent / "market_health.py"
    tree = ast.parse(path.read_text())

    for node in ast.walk(tree):
        if isinstance(node, (ast.Import, ast.ImportFrom)):
            if isinstance(node, ast.ImportFrom) and node.module:
                for forbidden in FORBIDDEN_IMPORTS:
                    assert forbidden not in node.module, \
                        f"market_health.py imports {forbidden}"
            if isinstance(node, ast.Import):
                for alias in node.names:
                    for forbidden in FORBIDDEN_IMPORTS:
                        assert forbidden not in alias.name, \
                            f"market_health.py imports {forbidden}"


def test_event_risk_gate_no_execution_imports():
    """event_risk_gate.py must not import execution modules."""
    path = Path(__file__).parent / "event_risk_gate.py"
    tree = ast.parse(path.read_text())

    for node in ast.walk(tree):
        if isinstance(node, (ast.Import, ast.ImportFrom)):
            if isinstance(node, ast.ImportFrom) and node.module:
                for forbidden in FORBIDDEN_IMPORTS:
                    assert forbidden not in node.module, \
                        f"event_risk_gate.py imports {forbidden}"
            if isinstance(node, ast.Import):
                for alias in node.names:
                    for forbidden in FORBIDDEN_IMPORTS:
                        assert forbidden not in alias.name, \
                            f"event_risk_gate.py imports {forbidden}"
