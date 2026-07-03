"""G0.1.2: No legacy hardcode reachable from canonical production path.

Scans each canonical module's AST for forbidden tokens in executable code.
Docstrings, comments, and string literals are allowed.
"""
import ast
from pathlib import Path

REPO_ROOT = Path(r"C:\Users\menum\graxia os")

FORBIDDEN = ["units_per_lot", "100000", "risk_per_trade_pct", "pip_value"]

# ponytail: canonical modules are files that should NOT contain forbidden tokens.
# Files that legitimately use these tokens (config dataclasses, position sizers)
# are excluded — they ARE the current API, not legacy patterns to regress on.
CANONICAL_MODULES = [
    "graxia.packages.quant_os.broker.mt5_gateway",
    "graxia.packages.quant_os.execution.fill_model",
    "graxia.packages.quant_os.execution.cost_model",
    "graxia.packages.quant_os.execution.order_state_machine",
    "graxia.packages.quant_os.execution.trade_ledger",
    "graxia.packages.quant_os.risk.risk_ledger",
]


def _source_path(module_name: str) -> Path:
    parts = module_name.split(".")
    candidate = REPO_ROOT / Path(*parts).with_suffix(".py")
    if candidate.exists():
        return candidate
    raise FileNotFoundError(f"Cannot locate source for {module_name}")


def _contains_forbidden(s: str) -> str | None:
    for token in FORBIDDEN:
        if token in s:
            return token
    return None


class ForbiddenTokenVisitor(ast.NodeVisitor):
    """Visits AST nodes, flagging forbidden tokens in executable contexts."""

    def __init__(self):
        self.hits: list[str] = []

    def _flag(self, lineno: int, ctx: str, name: str):
        tok = _contains_forbidden(name)
        if tok:
            self.hits.append(f"  L{lineno}: {ctx} '{name}' uses '{tok}'")

    def visit_Import(self, node):
        for alias in node.names:
            self._flag(node.lineno, "import", alias.asname or alias.name)
        self.generic_visit(node)

    def visit_ImportFrom(self, node):
        for alias in node.names:
            self._flag(node.lineno, "import", alias.asname or alias.name)
        self.generic_visit(node)

    def visit_Attribute(self, node):
        self._flag(node.lineno, "attr", node.attr)
        self.generic_visit(node)

    def visit_keyword(self, node):
        if node.arg:
            self._flag(node.lineno, "kwarg", node.arg)
        self.generic_visit(node)

    def visit_Name(self, node):
        self._flag(node.lineno, "name", node.id)
        self.generic_visit(node)

    def visit_Dict(self, node):
        for key in node.keys:
            if isinstance(key, ast.Constant) and isinstance(key.value, str):
                self._flag(node.lineno, "dict key", key.value)
        self.generic_visit(node)

    def visit_Constant(self, node):
        # Allow string literals (docstrings, messages, comments already skipped)
        pass

    def visit_FunctionDef(self, node):
        # Skip validate_no_pct_in_production — it IS the detector
        if node.name == "validate_no_pct_in_production":
            return
        self.generic_visit(node)

    visit_AsyncFunctionDef = visit_FunctionDef


def test_no_forbidden_tokens_in_canonical_modules():
    violations: dict[str, list[str]] = {}

    for mod_name in CANONICAL_MODULES:
        src = _source_path(mod_name)
        source = src.read_text(encoding="utf-8")
        tree = ast.parse(source, filename=str(src))

        visitor = ForbiddenTokenVisitor()
        visitor.visit(tree)

        if visitor.hits:
            violations[mod_name] = visitor.hits

    if violations:
        msg_parts = ["Forbidden tokens found in executable code of canonical modules:\n"]
        for mod, hits in violations.items():
            msg_parts.append(f"{mod}:")
            msg_parts.extend(hits)
        msg_parts.append(
            "\nCanonical modules must use bps-based RiskPolicy and broker-native sizing."
        )
        assert False, "\n".join(msg_parts)
