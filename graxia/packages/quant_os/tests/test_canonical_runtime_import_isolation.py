"""Phase 3.1A — Dynamic import isolation.

Assert canonical backtest path does not import forbidden packages at runtime.
"""
import ast
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(r"C:\Users\menum\graxia os")
ENGINE_PATH = REPO_ROOT / "graxia" / "packages" / "quant_os" / "backtest" / "engine.py"

FORBIDDEN_MODULES = [
    "MetaTrader5", "mt5", "ccxt", "vectorbt", "backtesting",
    "backtrader", "hftbacktest", "yfinance", "yahooquery", "coingecko",
]


def test_no_forbidden_imports_in_canonical():
    """Canonical package must not import forbidden modules at import time."""
    result = subprocess.run(
        [
            sys.executable, "-c",
            "import sys; import graxia.packages.quant_os; "
            "loaded = set(sys.modules.keys()); "
            "forbidden = " + repr(FORBIDDEN_MODULES) + "; "
            "found = [m for m in forbidden if m in loaded]; "
            "exit(1 if found else 0)",
        ],
        capture_output=True, text=True, timeout=30,
        cwd=str(REPO_ROOT),
    )
    assert result.returncode == 0, (
        f"Forbidden imports found:\nstdout: {result.stdout}\nstderr: {result.stderr}"
    )


def test_engine_module_no_forbidden_imports():
    """Engine source must not contain forbidden imports (AST scan)."""
    src = ENGINE_PATH.read_text(encoding="utf-8")
    tree = ast.parse(src)
    violations = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                for f in FORBIDDEN_MODULES:
                    if f.lower() in alias.name.lower():
                        violations.append(f"L{node.lineno}: import {alias.name}")
        if isinstance(node, ast.ImportFrom):
            if node.module:
                for f in FORBIDDEN_MODULES:
                    if f.lower() in node.module.lower():
                        violations.append(f"L{node.lineno}: from {node.module}")
    assert not violations, "Forbidden imports in engine:\n" + "\n".join(violations)


def test_no_order_send_in_engine():
    """Engine must not call or import order_send."""
    src = ENGINE_PATH.read_text(encoding="utf-8")
    tree = ast.parse(src)
    for node in ast.walk(tree):
        if isinstance(node, ast.Attribute) and node.attr == "order_send":
            assert False, f"order_send call at L{node.lineno}"
        if isinstance(node, ast.Name) and node.id == "order_send":
            assert False, f"order_send reference at L{node.lineno}"


def test_no_forbidden_tokens_in_engine_executable():
    """Engine executable code must not use legacy tokens."""
    src = ENGINE_PATH.read_text(encoding="utf-8")
    tree = ast.parse(src)
    violations = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Attribute):
            if node.attr in ("units_per_lot", "risk_per_trade_pct"):
                violations.append(f"L{node.lineno}: .{node.attr}")
        if isinstance(node, ast.Constant):
            if node.value == "100000":
                violations.append(f"L{node.lineno}: literal 100000")
    assert not violations, "Legacy tokens:\n" + "\n".join(violations)
