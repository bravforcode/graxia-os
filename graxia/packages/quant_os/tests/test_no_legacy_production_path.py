"""G0.5: No legacy hardcode reachable from canonical production path.

Scans each canonical module's source file for forbidden tokens.
This is a regression guard — new legacy patterns must not creep in.
"""
import importlib
import sys
from pathlib import Path

REPO_ROOT = Path(r"C:\Users\menum\graxia os")

FORBIDDEN = ["units_per_lot", "100000", "risk_per_trade_pct", "pip_value"]

CANONICAL_MODULES = [
    "graxia.packages.quant_os.risk.position_sizer_v2",
    "graxia.packages.quant_os.risk.pre_trade_risk",
    "graxia.packages.quant_os.risk.risk_policy",
    "graxia.packages.quant_os.execution.fill_model",
    "graxia.packages.quant_os.execution.cost_model",
    "graxia.packages.quant_os.backtest.mtf_cursor",
]


def _source_path(module_name: str) -> Path:
    """Resolve a dotted module name to its .py source file."""
    parts = module_name.split(".")
    # Walk from repo root: graxia/packages/quant_os/...
    candidate = REPO_ROOT / Path(*parts).with_suffix(".py")
    if candidate.exists():
        return candidate
    # Fallback: use importlib
    spec = importlib.util.find_spec(module_name)
    if spec and spec.origin:
        return Path(spec.origin)
    raise FileNotFoundError(f"Cannot locate source for {module_name}")


def test_no_forbidden_tokens_in_canonical_modules():
    """Each canonical module must be free of forbidden legacy tokens."""
    violations: dict[str, list[str]] = {}

    for mod_name in CANONICAL_MODULES:
        src = _source_path(mod_name)
        lines = src.read_text(encoding="utf-8").splitlines()
        hits = []
        for i, line in enumerate(lines, 1):
            # Skip comments
            stripped = line.strip()
            if stripped.startswith("#"):
                continue
            for token in FORBIDDEN:
                if token in line:
                    hits.append(f"  L{i}: {token}")
        if hits:
            violations[mod_name] = hits

    if violations:
        msg_parts = ["Forbidden tokens found in canonical modules:\n"]
        for mod, hits in violations.items():
            msg_parts.append(f"{mod}:")
            msg_parts.extend(hits)
        msg_parts.append(
            "\nCanonical modules must use bps-based RiskPolicy and broker-native sizing."
        )
        assert False, "\n".join(msg_parts)
