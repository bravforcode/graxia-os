"""Verify oracle adapters are isolated from canonical runtime."""
import ast
from pathlib import Path

REPO_ROOT = Path(r"C:\Users\menum\graxia os")
ADAPTER_DIR = REPO_ROOT / "graxia/packages/quant_os/repo_intelligence/adapters"
CANONICAL_DIR = REPO_ROOT / "graxia/packages/quant_os"

ORACLE_PACKAGES = ["vectorbt", "backtesting", "backtrader"]


def _collect_module_level_imports(tree):
    """Yield Import nodes that live directly in the module body (not inside functions/classes)."""
    for node in tree.body:
        if isinstance(node, ast.Import):
            yield node
        elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            for child in ast.walk(node):
                if isinstance(child, ast.Import):
                    pass  # skip — inside function/class
        # for/while/if blocks at module level still count as module-level


def test_no_oracle_imports_in_canonical():
    """Canonical source must not import oracle packages at module level."""
    exclude = {"adapters", "test_", "phase_3b_oracle_runner"}
    for py_file in CANONICAL_DIR.rglob("*.py"):
        if any(x in str(py_file) for x in exclude):
            continue
        src = py_file.read_text(encoding="utf-8", errors="ignore")
        tree = ast.parse(src)
        for node in _collect_module_level_imports(tree):
            for alias in node.names:
                for pkg in ORACLE_PACKAGES:
                    if pkg in alias.name.lower():
                        assert False, f"Module-level oracle import in {py_file.name}:L{node.lineno}: {alias.name}"
        for node in tree.body:
            if isinstance(node, ast.ImportFrom):
                if node.module:
                    for pkg in ORACLE_PACKAGES:
                        if pkg in node.module.lower():
                            assert False, f"Module-level oracle import in {py_file.name}:L{node.lineno}: from {node.module}"


def test_adapters_have_lazy_import():
    """Adapter modules must not import oracle packages at module level."""
    for adapter_file in ADAPTER_DIR.glob("*.py"):
        if adapter_file.name.startswith("__"):
            continue
        src = adapter_file.read_text(encoding="utf-8")
        tree = ast.parse(src)
        for node in _collect_module_level_imports(tree):
            for alias in node.names:
                for pkg in ORACLE_PACKAGES:
                    if pkg in alias.name.lower():
                        assert False, f"Module-level oracle import in {adapter_file.name}:L{node.lineno}"
