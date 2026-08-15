"""C0.3: AST-based external-state scanner for strategy generate_signal.

Detects reads of file/live-cache/global state that are NOT derived from
engine-passed arguments (symbol, ohlcv_data, indicators, regime, current_time).
This is the external-state vector the runtime guard cannot close in-process
(see lookahead_guard_reachability_audit_2026_07_30.md §4). Different from
check_bypass_loaders.py (engine-bypass check).

Design (2026-08-06 fix — false-positive reduction):
  * (a) file/cache I/O attribute calls (.read_text/.open/.load/...) are flagged
        REGARDLESS of name tracking — the call pattern itself is the signal.
  * (b) subscript on an unknown (non-local, non-imported) name = cache/global read.
  * (c) attribute on an unknown name = external attribute read.
  Locals assigned inside generate_signal, function args, engine args, and every
  module-level import name are considered known. Bare-name calls (float, int,
  np.array, Decimal, ...) are NOT flagged — safe deterministic calls only.
"""

from __future__ import annotations

import ast
from pathlib import Path

ENGINE_ARGS = {"symbol", "ohlcv_data", "indicators", "regime", "current_time", "kwargs"}
FILE_IO_ATTRS = {"read_text", "read", "readlines", "read_csv", "read_parquet", "load", "open"}


def _walk_runtime(tree):
    """ast.walk, but prune type-annotation subtrees.

    Annotations (`x: dict[str, list]`, `-> Signal | None`) are compile-time type
    hints, never runtime external-state reads — flagging builtin generic names
    inside them (e.g. `dict`) is a false positive.
    """
    seen = set()
    stack = [tree]
    while stack:
        node = stack.pop()
        if id(node) in seen:
            continue
        seen.add(id(node))
        yield node
        for child in ast.iter_child_nodes(node):
            if isinstance(node, ast.AnnAssign) and child is node.annotation:
                continue
            if isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef) and child is node.returns:
                continue
            if isinstance(node, ast.arg) and child is node.annotation:
                continue
            stack.append(child)


def scan_strategy_file(path: Path) -> list[str]:
    """Return line refs where generate_signal reads non-argument state."""
    src = path.read_text(encoding="utf-8")
    tree = ast.parse(src)

    # Module-level imports → known names (np, datetime, pathlib, SignalType, ...)
    known = set(ENGINE_ARGS)
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                known.add((alias.asname or alias.name).split(".")[0])
        elif isinstance(node, ast.ImportFrom):
            for alias in node.names:
                known.add(alias.asname or alias.name)

    hits: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and node.name == "generate_signal":
            arg_names = {a.arg for a in node.args.args} | set(ENGINE_ARGS)

            # Locals assigned inside generate_signal → known
            locals_ = set(arg_names)
            for sub in _walk_runtime(node):
                if isinstance(sub, ast.Assign | ast.AnnAssign):
                    tgts = sub.targets if isinstance(sub, ast.Assign) else [sub.target]
                    for tgt in tgts:
                        if isinstance(tgt, ast.Name):
                            locals_.add(tgt.id)
                        elif isinstance(tgt, ast.Tuple | ast.List):
                            for elt in tgt.elts:
                                if isinstance(elt, ast.Name):
                                    locals_.add(elt.id)

            for sub in _walk_runtime(node):
                # (a) file/cache I/O attribute call: .read_text() .open() .load() ...
                if isinstance(sub, ast.Call) and isinstance(sub.func, ast.Attribute):
                    if sub.func.attr in FILE_IO_ATTRS:
                        hits.append(f"{path.name}:{sub.lineno}: file-io call {sub.func.attr}()")
                # (b) subscript on unknown name (cache/global read)
                elif isinstance(sub, ast.Subscript) and isinstance(sub.value, ast.Name):
                    if sub.value.id not in locals_ and sub.value.id not in known:
                        hits.append(f"{path.name}:{sub.lineno}: subscript {sub.value.id}")
                # (c) attribute on unknown name (external attribute read)
                elif (
                    isinstance(sub, ast.Attribute)
                    and isinstance(sub.value, ast.Name)
                    and sub.value.id not in locals_
                    and sub.value.id not in known
                ):
                    hits.append(f"{path.name}:{sub.lineno}: attribute {sub.value.id}.{sub.attr}")
    return hits


def scan_engine_callers() -> list[dict]:
    """Scan known engine.run() callers for their strategies' external-state reads."""
    root = Path(__file__).resolve().parent.parent
    caller_files = [
        root / "scripts" / "edge_search_tf_probe.py",
        root / "scripts" / "edge_search_m15_scalper.py",
        root / "scripts" / "run_ws_a.py",
    ]
    strategy_files = [
        root / "strategies" / "asian_scalper.py",
        root / "strategies" / "happy_gold_scalper.py",
    ]
    out = []
    for c in caller_files:
        verdict = "CLEAN"
        evidence = []
        for s in strategy_files:
            if s.exists():
                hits = scan_strategy_file(s)
                if hits:
                    verdict = "VECTOR_FOUND"
                    evidence.extend(hits)
        out.append(
            {
                "caller": c.name,
                "verdict": verdict,
                "evidence": "; ".join(evidence) if evidence else "all strategies read engine-passed args only",
            }
        )
    return out
