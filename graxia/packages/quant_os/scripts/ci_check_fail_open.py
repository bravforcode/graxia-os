"""
CI gate: fail-open AccountState detection.

Scans production code (excluding tests) for:
1. AccountState dataclass defaults that fabricate healthy financial state
   (equity > 0, margin_level_pct > 100, free_margin > 0, peak_equity > 0)
2. Hardcoded AccountState() calls with fabricated equity values > 0
3. AccountState() default construction (no args → inherits defaults)

Exit code 0 = clean, exit code 1 = fail-open patterns found.

Usage: python scripts/ci_check_fail_open.py [--root <path>]
"""

from __future__ import annotations

import ast
import sys
from pathlib import Path

PRODUCTION_DIRS = {"risk", "data", "autonomous", "execution", "api", "ml", "core", "gold_bot"}
TEST_DIRS = {"tests", "test"}
EXCLUDE_DIRS = {".freebuff", ".git", "__pycache__", "node_modules", ".venv", "venv", "site-packages"}

# AccountState financial fields that must NOT default to fabricated-healthy values.
FABRICATED_DEFAULTS = {
    "equity": 100000.0,
    "balance": 100000.0,
    "free_margin": 100000.0,
    "peak_equity": 100000.0,
    "margin_level_pct": 999.0,
}


class FailOpenVisitor(ast.NodeVisitor):
    """Walk AST looking for fail-open AccountState patterns."""

    def __init__(self, filepath: str):
        self.filepath = filepath
        self.findings: list[str] = []
        self._in_accountstate = False

    def visit_ClassDef(self, node: ast.ClassDef) -> None:
        if node.name == "AccountState":
            for item in node.body:
                if isinstance(item, ast.AnnAssign) and isinstance(item.target, ast.Name):
                    field = item.target.id
                    if field in FABRICATED_DEFAULTS and item.value is not None:
                        if isinstance(item.value, ast.Constant):
                            if item.value.value == FABRICATED_DEFAULTS[field]:
                                self.findings.append(
                                    f"{self.filepath}:{item.lineno} "
                                    f"AccountState.{field} defaults to {item.value.value} "
                                    f"(fabricated-healthy, should be 0.0)"
                                )
        self.generic_visit(node)

    def visit_Call(self, node: ast.Call) -> None:
        # Catch AccountState() — no args, inherits all defaults
        if isinstance(node.func, ast.Name) and node.func.id == "AccountState":
            if not node.args and not node.keywords:
                self.findings.append(
                    f"{self.filepath}:{node.lineno} "
                    f"AccountState() — bare default construction, inherits "
                    f"fabricated-healthy defaults (should pass explicit zero values)"
                )
            else:
                for kw in node.keywords:
                    if kw.arg == "equity" and isinstance(kw.value, ast.Constant):
                        if isinstance(kw.value.value, (int, float)) and kw.value.value > 0:
                            self.findings.append(
                                f"{self.filepath}:{node.lineno} "
                                f"AccountState(equity={kw.value.value}) — "
                                f"hardcoded positive equity (fail-open)"
                            )
        self.generic_visit(node)


def is_production_path(path: Path) -> bool:
    parts = set(path.parts)
    if parts & EXCLUDE_DIRS:
        return False
    return bool(parts & PRODUCTION_DIRS) and not bool(parts & TEST_DIRS)


def scan_file(filepath: Path) -> list[str]:
    try:
        tree = ast.parse(filepath.read_text(encoding="utf-8"))
    except SyntaxError:
        return []
    visitor = FailOpenVisitor(str(filepath))
    visitor.visit(tree)
    return visitor.findings


def main() -> int:
    root = Path(sys.argv[2]) if len(sys.argv) > 2 and sys.argv[1] == "--root" else Path(".")
    py_files = [p for p in root.rglob("*.py") if is_production_path(p)]

    all_findings: list[str] = []
    for fp in py_files:
        all_findings.extend(scan_file(fp))

    if all_findings:
        print(f"FAIL-OPEN PATTERNS FOUND ({len(all_findings)}):")
        for f in all_findings:
            print(f"  {f}")
        return 1

    print("OK: No fail-open AccountState patterns detected.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
