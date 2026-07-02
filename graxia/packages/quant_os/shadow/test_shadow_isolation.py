"""Phase BE-P8 — Shadow isolation. Must never call order_send."""
import ast
from pathlib import Path


FORBIDDEN_CALLS = ["order_send", "order_check", "order_calc_margin"]


def test_shadow_modules_no_order_send():
    """Shadow modules must not call order_send."""
    shadow_dir = Path(__file__).parent
    violations = []

    for f in shadow_dir.glob("*.py"):
        if f.name.startswith("test_"):
            continue
        if f.name == "__init__.py":
            continue

        try:
            tree = ast.parse(f.read_text(encoding="utf-8", errors="replace"))
        except SyntaxError:
            continue

        for node in ast.walk(tree):
            if isinstance(node, ast.Call):
                func_name = ""
                if isinstance(node.func, ast.Name):
                    func_name = node.func.id
                elif isinstance(node.func, ast.Attribute):
                    func_name = node.func.attr

                if func_name in FORBIDDEN_CALLS:
                    violations.append(f"{f.name}: calls {func_name}")

    assert len(violations) == 0, f"Shadow calls order APIs: {violations}"


def test_shadow_pipeline_has_no_order_api():
    """Shadow pipeline must not expose order API."""
    from graxia.packages.quant_os.shadow.shadow_pipeline import ShadowPipeline
    pipeline = ShadowPipeline()
    assert not hasattr(pipeline, 'order_send')
    assert not hasattr(pipeline, 'order_check')
