import ast
from pathlib import Path

import pytest

from app.core.observability import timed

APP_ROOT = Path(__file__).resolve().parents[1] / "app"
STDLIB_LOG_LEVELS = {"debug", "info", "warning", "warn", "error", "exception", "critical"}
STDLIB_LOG_KWARGS = {"exc_info", "stack_info", "stacklevel", "extra"}


def _uses_stdlib_logger(tree: ast.Module) -> bool:
    for node in tree.body:
        if not isinstance(node, ast.Assign):
            continue
        if not any(isinstance(target, ast.Name) and target.id == "logger" for target in node.targets):
            continue
        call = node.value
        if isinstance(call, ast.Call) and isinstance(call.func, ast.Attribute) and call.func.attr == "getLogger":
            return True
    return False


def _structured_kwargs_on_stdlib_logger(path: Path) -> list[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    if not _uses_stdlib_logger(tree):
        return []
    hits = []
    for node in ast.walk(tree):
        if not (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and node.func.attr in STDLIB_LOG_LEVELS
            and isinstance(node.func.value, ast.Name)
            and node.func.value.id == "logger"
        ):
            continue
        kwargs = [kw.arg for kw in node.keywords if kw.arg not in STDLIB_LOG_KWARGS]
        if kwargs:
            hits.append(f"{path.relative_to(APP_ROOT.parent)}:{node.lineno} kwargs={kwargs}")
    return hits


def test_stdlib_logger_calls_never_pass_structured_kwargs():
    hits = []
    for path in sorted(APP_ROOT.rglob("*.py")):
        hits.extend(_structured_kwargs_on_stdlib_logger(path))
    assert hits == []


async def test_timed_reraises_original_error_not_logger_type_error():
    @timed("stdlib_logger_regression")
    async def fails():
        raise ValueError("boom")

    with pytest.raises(ValueError, match="boom"):
        await fails()
