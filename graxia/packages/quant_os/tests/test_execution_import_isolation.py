"""Test execution import isolation: order_send only in order_submission.py."""
import ast
from pathlib import Path

EXECUTION_DIR = Path(__file__).resolve().parent.parent / "execution"
SOLE_ALLOWLIST = "demo_canary/order_submission.py"


def _find_order_send_calls(root: Path) -> list[tuple[str, int]]:
    """Return [(file_relpath, lineno), ...] with `order_send` AST calls."""
    hits = []
    for pyfile in sorted(root.rglob("*.py")):
        rel = pyfile.relative_to(root).as_posix()
        if rel == SOLE_ALLOWLIST:
            continue
        try:
            tree = ast.parse(pyfile.read_text(encoding="utf-8"))
        except SyntaxError:
            continue
        for node in ast.walk(tree):
            if isinstance(node, ast.Call):
                func = node.func
                if isinstance(func, ast.Attribute) and func.attr == "order_send":
                    hits.append((rel, node.lineno))
                elif isinstance(func, ast.Name) and func.id == "order_send":
                    hits.append((rel, node.lineno))
    return hits


def test_order_send_only_in_allowlist():
    hits = _find_order_send_calls(EXECUTION_DIR)
    assert not hits, (
        f"order_send found outside {SOLE_ALLOWLIST}: "
        + "; ".join(f"{f}:{l}" for f, l in hits)
    )


def test_broker_adapter_has_order_submission_disabled():
    """Verify broker_adapter.py has the submission guard comment."""
    ba_path = EXECUTION_DIR / "broker_adapter.py"
    text = ba_path.read_text(encoding="utf-8")
    assert "order_submission.py" in text, (
        "broker_adapter.py must reference order_submission.py as the sole allowlist"
    )


def test_submission_enabled_is_callable():
    """Verify the allowlist module exports a callable."""
    from execution.demo_canary.order_submission import is_submission_enabled
    assert callable(is_submission_enabled)
