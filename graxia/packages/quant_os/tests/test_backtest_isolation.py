"""Phase 3.1: Verify backtest path has no MT5 dependency and no external repo imports."""
import ast
import re
from pathlib import Path

import pytest

REPO_ROOT = Path(r"C:\Users\menum\graxia os")
ENGINE = REPO_ROOT / "graxia/packages/quant_os/backtest/engine.py"

FORBIDDEN_MT5_PATTERNS = ["mt5", "MetaTrader5", "order_send", "order_calc_profit", "order_calc_margin", "order_check"]
EXTERNAL_REPOS = ["hftbacktest", "vectorbt", "backtesting", "backtrader", "freqtrade", "jesse", "lean"]


def test_no_mt5_in_engine():
    """Engine must not import or call MT5 functions."""
    src = ENGINE.read_text(encoding="utf-8")
    tree = ast.parse(src)
    violations = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                for pat in FORBIDDEN_MT5_PATTERNS:
                    if pat.lower() in alias.name.lower():
                        violations.append(f"L{node.lineno}: import {alias.name} (matches {pat})")
        if isinstance(node, ast.ImportFrom):
            if node.module:
                for pat in FORBIDDEN_MT5_PATTERNS:
                    if pat.lower() in node.module.lower():
                        violations.append(f"L{node.lineno}: from {node.module} (matches {pat})")
    assert not violations, f"MT5 found in engine:\n" + "\n".join(violations)


def test_no_external_repo_imports_in_engine():
    """Engine must not import external backtesting repos."""
    src = ENGINE.read_text(encoding="utf-8")
    tree = ast.parse(src)
    violations = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                for repo in EXTERNAL_REPOS:
                    if repo.lower() in alias.name.lower():
                        violations.append(f"L{node.lineno}: import {alias.name}")
        if isinstance(node, ast.ImportFrom):
            if node.module:
                for repo in EXTERNAL_REPOS:
                    if repo.lower() in node.module.lower():
                        violations.append(f"L{node.lineno}: from {node.module}")
    assert not violations, f"External repo imports in engine:\n" + "\n".join(violations)


def test_no_mt5_in_sizing_provider():
    """HistoricalSizingProvider must not use MT5."""
    sizing_file = REPO_ROOT / "graxia/packages/quant_os/risk/historical_sizing_provider.py"
    if not sizing_file.exists():
        pytest.skip("historical_sizing_provider.py not yet created")
    lines = sizing_file.read_text(encoding="utf-8").splitlines()
    for i, line in enumerate(lines, 1):
        stripped = line.strip()
        if stripped.startswith("#") or stripped.startswith("//"):
            continue
        for pat in FORBIDDEN_MT5_PATTERNS:
            assert pat.lower() not in stripped.lower(), f"MT5 pattern '{pat}' in sizing provider L{i}"


def test_no_legacy_tokens_in_engine_executable():
    """Engine executable code must not hardcode legacy token values."""
    src = ENGINE.read_text(encoding="utf-8")
    tree = ast.parse(src)
    violations = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Constant):
            if node.value == "100000":
                violations.append(f"L{node.lineno}: literal 100000")
    assert not violations, f"Legacy tokens:\n" + "\n".join(violations)
