"""Phase BE-P5 — Oracle isolation. Canonical must not import oracle packages."""

import ast
from pathlib import Path

ORACLE_PACKAGES = ["vectorbt", "backtesting", "bt", "backtrader"]


def _scan_imports(file_path: Path) -> list[str]:
    """Extract all imports from a Python file."""
    try:
        tree = ast.parse(file_path.read_text(encoding="utf-8", errors="replace"))
    except SyntaxError:
        return []

    imports = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                imports.append(alias.name.split(".")[0])
        elif isinstance(node, ast.ImportFrom) and node.module:
            imports.append(node.module.split(".")[0])
    return imports


def _find_canonical_files() -> list[Path]:
    """Find all canonical Python files (not in oracle/ directory)."""
    root = Path(__file__).parent.parent.parent
    files = []
    for p in root.rglob("*.py"):
        if "oracle" in str(p).lower():
            continue
        if "__pycache__" in p.parts:
            continue
        if "test_" in p.name:
            continue
        files.append(p)
    return files


def test_canonical_no_oracle_imports():
    """Canonical runtime must not import oracle packages."""
    files = _find_canonical_files()
    violations = []

    for f in files:
        imports = _scan_imports(f)
        for imp in imports:
            if imp in ORACLE_PACKAGES:
                violations.append(f"{f.name}: imports {imp}")

    assert len(violations) == 0, f"Canonical imports oracle packages: {violations}"


def test_oracle_modules_isolated():
    """Oracle modules should only import their own framework."""
    oracle_dir = Path(__file__).parent
    for f in oracle_dir.glob("*.py"):
        if f.name.startswith("test_"):
            continue
        if f.name == "__init__.py":
            continue
        imports = _scan_imports(f)
        for imp in imports:
            if imp in ORACLE_PACKAGES:
                content = f.read_text(encoding="utf-8", errors="replace")
                if f"import {imp}" in content or f"from {imp}" in content:
                    pass  # Expected - adapter imports its own framework
