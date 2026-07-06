"""
bridge_automated_sync.py — Ruflow/Gracia Bridge Agent v2
=======================================================
Syncs quant_OS states, backtest results, strategy configs,
and codebase graph into the Obsidian Second Brain vault.

Upgrades implemented:
  🥇 Automated bridge-sync (Meta/states/ → vault)
  🥈 Backtest results → vault inbox
  🥉 Strategy/risk config mirror → vault
  ④ Knowledge graph sync (codebase ↔ vault)

Usage:
  python scripts/bridge_automated_sync.py           # one-shot sync
  python scripts/bridge_automated_sync.py --watch    # continuous file watcher
  python scripts/bridge_automated_sync.py --backtest # sync latest backtest only
  python scripts/bridge_automated_sync.py --graph    # rebuild graph only
"""

import argparse
import hashlib
import io
import json
import os
import re
import shutil
import sys
import time
from datetime import UTC, datetime
from pathlib import Path

# Force UTF-8 on stdout/stderr (Windows cp1252 fix)
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8")

# ─── Paths ───────────────────────────────────────────────────────────────
QUANT_OS = Path(__file__).resolve().parent.parent
VAULT = Path(
    os.environ.get(
        "OBSIDIAN_VAULT_PATH",
        r"C:\Users\menum\quant\quant bot",
    )
)

SYNC_MANIFEST = QUANT_OS / "Meta" / "bridge_manifest.json"
STATE_DIR = QUANT_OS / "Meta" / "states"
ARCHIVE_DIR = QUANT_OS / "Meta" / "archive"
EXECUTION_PLAN = QUANT_OS / "Meta" / "execution_plan.md"
PRE_REGISTER = QUANT_OS / "Meta" / "pre_register_b2.md"
STOP_LOSS_AUDIT = QUANT_OS / "Meta" / "stop_loss_audit.md"

VAULT_STATES = VAULT / "Meta" / "states" / "quant_os"
VAULT_INBOX = VAULT / "00-Inbox"
VAULT_PROJECT = VAULT / "01-projects" / "Graxia-OS" / "quant_os"
VAULT_GRAPH = VAULT_STATES / "graph"

# ─── Files to sync by category ──────────────────────────────────────────
STATE_GLOBS = ["*.md"]  # all .md in Meta/states/
ARCHIVE_GLOBS = ["*.md"]
ROOT_META = [EXECUTION_PLAN, PRE_REGISTER, STOP_LOSS_AUDIT]

STRATEGY_DIR = QUANT_OS / "strategies"
RISK_DIR = QUANT_OS / "risk"
STRATEGY_GLOBS = ["**/*.py", "**/*.yaml", "**/*.yml", "**/*.json"]
RISK_GLOBS = ["**/*.py", "**/*.yaml", "**/*.yml", "**/*.json"]

BACKTEST_DIR = QUANT_OS / "artifacts" / "walk_forward_v4"
BACKTEST_RESULTS = QUANT_OS / "artifacts"

# ══════════════════════════════════════════════════════════════════════════
#  UPGRADE 1: Automated bridge-sync (Meta/states/ → vault)
# ══════════════════════════════════════════════════════════════════════════


def sync_states_to_vault(manifest: dict) -> list:
    """Sync Meta/states/*.md and root Meta/*.md to vault's Meta/states/quant_os/."""
    synced = []

    # Ensure destination
    VAULT_STATES.mkdir(parents=True, exist_ok=True)

    # 1. Sync state files
    for f in sorted(STATE_DIR.glob("*.md")):
        synced.append(_copy_with_manifest(f, VAULT_STATES, manifest, "state"))

    # 2. Sync archive files
    vault_archive = VAULT_STATES / "archive"
    vault_archive.mkdir(parents=True, exist_ok=True)
    for f in sorted(ARCHIVE_DIR.glob("*.md")):
        synced.append(_copy_with_manifest(f, vault_archive, manifest, "archive"))

    # 3. Sync root Meta files
    for f in ROOT_META:
        if f.exists():
            synced.append(_copy_with_manifest(f, VAULT_STATES, manifest, "meta-root"))

    return synced


# ══════════════════════════════════════════════════════════════════════════
#  UPGRADE 2: Backtest results → vault inbox
# ══════════════════════════════════════════════════════════════════════════


def sync_backtest_to_inbox(manifest: dict) -> list:
    """Create/update inbox notes for latest backtest run results."""
    synced = []
    VAULT_INBOX.mkdir(parents=True, exist_ok=True)

    # Find latest backtest artifacts
    backtest_dirs = sorted(BACKTEST_RESULTS.glob("walk_forward_v*"))
    if not backtest_dirs:
        return synced

    latest = backtest_dirs[-1]
    summary_note = VAULT_INBOX / f"Backtest_{latest.name}.md"

    # Gather metrics from JSON results
    json_results = list(latest.glob("*.json"))
    if json_results:
        stats = _aggregate_backtest_stats(json_results)
        content = _render_backtest_note(latest.name, stats)
        summary_note.write_text(content, encoding="utf-8")
        synced.append(("inbox", str(summary_note.relative_to(VAULT)), "backtest-summary"))

    # Per-trade parquet summary
    parquet_files = list(latest.glob("*.parquet"))
    if parquet_files:
        data_note = VAULT_INBOX / f"Backtest_{latest.name}_data.md"
        content = _render_backtest_data_note(latest.name, parquet_files)
        data_note.write_text(content, encoding="utf-8")
        synced.append(("inbox", str(data_note.relative_to(VAULT)), "backtest-data"))

    return synced


def _aggregate_backtest_stats(json_paths: list) -> dict:
    """Aggregate stats from walk_forward JSON results."""
    totals = {"net_pnl": 0, "gross_profit": 0, "gross_loss": 0, "trades": 0, "files": 0}
    for jp in json_paths:
        try:
            data = json.loads(jp.read_text(encoding="utf-8"))
            totals["net_pnl"] += data.get("net_pnl", data.get("total_net_pnl", 0))
            totals["gross_profit"] += data.get("gross_profit", data.get("total_gross_profit", 0))
            totals["gross_loss"] += data.get("gross_loss", data.get("total_gross_loss", 0))
            totals["trades"] += data.get("trade_count", data.get("total_trades", 0))
            totals["files"] += 1
        except (json.JSONDecodeError, KeyError):
            pass
    return totals


def _render_backtest_note(run_name: str, stats: dict) -> str:
    """Generate Obsidian markdown note for a backtest run."""
    now = datetime.now(UTC).strftime("%Y-%m-%d %H:%M UTC")
    return f"""---
created: {now}
tags: [backtest, bridge-auto, {run_name}]
status: inbox
---

# Backtest Results: `{run_name}`

**Synced by bridge_automated_sync.py** at {now}

| Metric | Value |
|--------|-------|
| Net PnL | ${stats.get('net_pnl', 0):.2f} |
| Gross Profit | ${stats.get('gross_profit', 0):.2f} |
| Gross Loss | ${stats.get('gross_loss', 0):.2f} |
| Total Trades | {stats.get('trades', 0)} |
| JSON Files | {stats.get('files', 0)} |

## Next Actions
- [ ] Review performance vs benchmark
- [ ] Log insights in `02-areas/trading/`
- [ ] Archive or escalate to weekly review

_Source: `{BACKTEST_RESULTS.relative_to(QUANT_OS)}/{run_name}/`_
"""


def _render_backtest_data_note(run_name: str, parquet_files: list) -> str:
    """Generate note listing available per-trade data."""
    now = datetime.now(UTC).strftime("%Y-%m-%d %H:%M UTC")
    files_list = "\n".join(f"- `{f.name}` ({f.stat().st_size / 1024:.0f} KB)" for f in parquet_files[:20])
    return f"""---
created: {now}
tags: [backtest, data, {run_name}]
status: inbox
---

# Backtest Per-Trade Data: `{run_name}`

{parquet_files.__len__()} parquet files synced at {now}.

{files_list}

_Source: `{BACKTEST_RESULTS.relative_to(QUANT_OS)}/{run_name}/`_
"""


# ══════════════════════════════════════════════════════════════════════════
#  UPGRADE 3: Strategy/risk config mirror → vault
# ══════════════════════════════════════════════════════════════════════════


def sync_strategy_risk_to_vault(manifest: dict) -> list:
    """Mirror strategy and risk config files to vault project folder."""
    synced = []

    # Strategy mirror
    vault_strat = VAULT_PROJECT / "strategies"
    vault_strat.mkdir(parents=True, exist_ok=True)
    for pattern in STRATEGY_GLOBS:
        for f in sorted(STRATEGY_DIR.glob(pattern)):
            dest = vault_strat / f.relative_to(STRATEGY_DIR)
            dest.parent.mkdir(parents=True, exist_ok=True)
            synced.append(_copy_with_manifest(f, dest.parent, manifest, "strategy"))

    # Risk mirror
    vault_risk = VAULT_PROJECT / "risk"
    vault_risk.mkdir(parents=True, exist_ok=True)
    for pattern in RISK_GLOBS:
        for f in sorted(RISK_DIR.glob(pattern)):
            dest = vault_risk / f.relative_to(RISK_DIR)
            dest.parent.mkdir(parents=True, exist_ok=True)
            synced.append(_copy_with_manifest(f, dest.parent, manifest, "risk"))

    # Overview note
    overview = VAULT_PROJECT / "bridge_config_overview.md"
    content = _render_config_overview()
    overview.write_text(content, encoding="utf-8")
    synced.append(("config-overview", str(overview.relative_to(VAULT)), "overview"))

    return synced


def _render_config_overview() -> str:
    """Generate overview of mirrored strategy/risk config."""
    now = datetime.now(UTC).strftime("%Y-%m-%d %H:%M UTC")
    strat_files = list(STRATEGY_DIR.rglob("*.py")) + list(STRATEGY_DIR.rglob("*.yaml"))
    risk_files = list(RISK_DIR.rglob("*.py")) + list(RISK_DIR.rglob("*.yaml")) + list(RISK_DIR.rglob("*.json"))
    return f"""---
created: {now}
tags: [config-mirror, bridge-auto]
status: permanent
---

# quant_OS Config Mirror

Auto-synced by bridge_automated_sync.py at {now}.

## Strategies ({len(strat_files)} files)
```
{chr(10).join('  ' + str(f.relative_to(STRATEGY_DIR)) for f in sorted(strat_files)[:30])}
```

## Risk ({len(risk_files)} files)
```
{chr(10).join('  ' + str(f.relative_to(RISK_DIR)) for f in sorted(risk_files)[:30])}
```

> ⚠️ Mirror only. Source of truth remains at `graxia/packages/quant_os/`.
"""


# ══════════════════════════════════════════════════════════════════════════
#  UPGRADE 4: Knowledge graph sync (codebase ↔ vault)
# ══════════════════════════════════════════════════════════════════════════


def sync_knowledge_graph(manifest: dict) -> list:
    """Analyze quant_OS codebase structure and sync a dependency graph to vault."""
    synced = []
    VAULT_GRAPH.mkdir(parents=True, exist_ok=True)

    # Build graph: module dependencies from Python imports
    # quant_OS uses flat layout: core/, execution/, risk/, strategies/ etc.
    graph = _build_import_graph(QUANT_OS)

    # Write graph JSON
    graph_file = VAULT_GRAPH / "codebase_graph.json"
    graph_file.write_text(json.dumps(graph, indent=2), encoding="utf-8")
    synced.append(("graph", str(graph_file.relative_to(VAULT)), "graph-json"))

    # Write human-readable summary
    summary = _render_graph_summary(graph)
    summary_file = VAULT_GRAPH / "codebase_graph.md"
    summary_file.write_text(summary, encoding="utf-8")
    synced.append(("graph", str(summary_file.relative_to(VAULT)), "graph-summary"))

    # Generate MOC-style note linking key modules
    moc = _render_graph_moc(graph)
    moc_file = VAULT_STATES / "quant_os_ARCHITECTURE.md"
    moc_file.write_text(moc, encoding="utf-8")
    synced.append(("graph", str(moc_file.relative_to(VAULT)), "architecture-moc"))

    # Write lean-ctx enrichable manifest
    enrich_manifest = VAULT_GRAPH / "enrich_nodes.json"
    enrich_manifest.write_text(
        json.dumps(
            {
                "source": "quant_os",
                "generated": datetime.now(UTC).isoformat(),
                "nodes": [{"id": n, "type": guess_node_type(n)} for n in graph["nodes"]],
                "description": "Import dependency graph for lean-ctx enrichment",
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    synced.append(("graph", str(enrich_manifest.relative_to(VAULT)), "enrich-manifest"))

    return synced


def guess_node_type(node_name: str) -> str:
    """Guess if a node is a module, subpackage, or unknown."""
    if node_name.count(".") >= 1:
        return "submodule"
    return "package"


def _build_import_graph(source_dir: Path) -> dict:
    """Walk Python files and extract import dependencies."""
    nodes = set()
    edges = []

    py_files = list(source_dir.rglob("*.py"))
    # Determine package root: find the parent with __init__.py or use source_dir.name
    pkg_root = source_dir
    root_pkg = source_dir.name  # e.g. "quant_os"

    for f in py_files:
        # Skip hidden dirs, venv, tests, scripts
        rel_str = str(f.relative_to(source_dir))
        if any(p.startswith(".") or p == ".venv" or p == "__pycache__" for p in rel_str.split(os.sep)):
            continue
        if rel_str.startswith("scripts") or rel_str.startswith("tests"):
            continue

        # Convert file path to dotted module name relative to source_dir
        mod = rel_str.replace(os.sep, "/").replace(".py", "").replace("/", ".")
        nodes.add(mod)

        try:
            text = f.read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError):
            continue

        # Extract explicit imports (local package imports only)
        for m in re.finditer(
            r"^(?:from\s+([\w.]+)|from\s+(\.+[\w.]*)|import\s+([\w.]+))",
            text,
            re.MULTILINE,
        ):
            target = m.group(1) or m.group(2) or m.group(3) or ""
            target = target.strip()
            if not target:
                continue

            # Resolve relative imports (..core.enums → quant_os.core.enums)
            if target.startswith("."):
                depth = len(target) - len(target.lstrip("."))
                pkg_parts = mod.split(".")
                if depth > 0 and len(pkg_parts) > depth:
                    base = ".".join(pkg_parts[:-depth])
                    resolved = f"{base}.{target.lstrip('.')}"
                    edges.append({"source": mod, "target": resolved})
                continue

            # Accept absolute imports starting with root_pkg
            if target.startswith(root_pkg):
                edges.append({"source": mod, "target": target})
                continue

            # Accept short-form imports from quant_OS top-level packages
            first = target.split(".")[0]
            if first in (
                "core",
                "execution",
                "risk",
                "validation",
                "strategies",
                "api",
                "broker",
                "market_data",
                "shadow",
                "canary",
                "backtest",
                "oracle",
                "live",
                "expansion",
                "demo_campaign",
                "mt5_connector",
                "live_readiness",
            ):
                edges.append({"source": mod, "target": f"{root_pkg}.{target}"})

    return {
        "metadata": {
            "title": "quant_OS Import Dependency Graph",
            "generated": datetime.now(UTC).isoformat(),
            "package": root_pkg,
        },
        "nodes": sorted(nodes),
        "edges": edges,
    }


def _render_graph_summary(graph: dict) -> str:
    """Render a human-readable graph summary in markdown."""
    now = datetime.now(UTC).strftime("%Y-%m-%d %H:%M UTC")
    node_count = len(graph["nodes"])
    edge_count = len(graph["edges"])
    return (
        f"""---
created: {now}
tags: [codebase-graph, bridge-auto, quant_os]
---

# quant_OS Knowledge Graph

**Auto-generated by bridge_automated_sync.py** at {now}

| Metric | Value |
|--------|-------|
| Nodes (modules) | {node_count} |
| Edges (dependencies) | {edge_count} |
| Package | `{graph['metadata']['package']}` |

## Module List

| Module | Type |
|--------|------|
"""
        + "\n".join(f"| `{n}` | {guess_node_type(n)} |" for n in sorted(graph["nodes"]))
        + "\n\n"
        + _render_mermaid_graph(graph)
    )


def _render_mermaid_graph(graph: dict) -> str:
    """Generate a Mermaid.js dependency graph."""
    lines = ["```mermaid", "graph LR"]
    for n in sorted(graph["nodes"]):
        safe = n.replace(".", "_").replace("-", "_")
        label = n.split(".")[-1]
        lines.append(f"  {safe}[{label}]")
    for e in graph["edges"][:50]:  # cap at 50 edges for readability
        src = e["source"].replace(".", "_").replace("-", "_")
        tgt = e["target"].replace(".", "_").replace("-", "_")
        lines.append(f"  {src} --> {tgt}")
    lines.append("```")
    return "\n".join(lines)


def _render_graph_moc(graph: dict) -> str:
    """Generate a Map of Content note for quant_OS architecture."""
    now = datetime.now(UTC).strftime("%Y-%m-%d %H:%M UTC")
    # Group by top-level package
    pkg_groups = {}
    for n in sorted(graph["nodes"]):
        parts = n.split(".")
        if len(parts) >= 2:
            top = parts[1]  # quant_os.X.Y → X
            pkg_groups.setdefault(top, []).append(n)

    sections = "\n".join(
        f"### `{pkg}`\n" + "\n".join(f"- `{m}`" for m in sorted(modules)[:15])
        for pkg, modules in sorted(pkg_groups.items())
    )
    return f"""---
created: {now}
tags: [architecture, moc, bridge-auto]
---

# quant_OS Architecture — Map of Content

**Auto-generated** at {now}

{len(graph['nodes'])} modules · {len(graph['edges'])} dependencies

## Package Breakdown

{sections}

## Source

Graph data: `Meta/states/quant_os/graph/codebase_graph.json`
Mermaid diagram: `Meta/states/quant_os/graph/codebase_graph.md`
"""


# ══════════════════════════════════════════════════════════════════════════
#  Manifest management
# ══════════════════════════════════════════════════════════════════════════


def load_manifest() -> dict:
    """Load or create the sync manifest (tracks file hashes)."""
    if SYNC_MANIFEST.exists():
        try:
            return json.loads(SYNC_MANIFEST.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            pass
    return {"files": {}, "last_sync": None, "syncs_total": 0}


def save_manifest(manifest: dict):
    """Persist the sync manifest."""
    manifest["last_sync"] = datetime.now(UTC).isoformat()
    manifest["syncs_total"] = manifest.get("syncs_total", 0) + 1
    SYNC_MANIFEST.write_text(json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8")


def file_hash(path: Path) -> str:
    """SHA-256 hash of file content."""
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _copy_with_manifest(src: Path, dest_dir: Path, manifest: dict, category: str) -> tuple:
    """Copy file if changed, update manifest. Returns (category, dest_rel, status)."""
    dest = dest_dir / src.name
    key = str(src.resolve())

    # Skip if unchanged
    if dest.exists():
        current = file_hash(src)
        cached = manifest.get("files", {}).get(key, {}).get("hash")
        if current == cached:
            return (category, str(dest.relative_to(VAULT)), "skipped")

    # Copy
    dest.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(str(src), str(dest))

    # Update manifest
    manifest.setdefault("files", {})[key] = {
        "hash": file_hash(src),
        "dest": str(dest.relative_to(VAULT)),
        "synced_at": datetime.now(UTC).isoformat(),
        "category": category,
    }
    return (category, str(dest.relative_to(VAULT)), "copied")


# ══════════════════════════════════════════════════════════════════════════
#  Watch mode (upgrade 1 continuous)
# ══════════════════════════════════════════════════════════════════════════


def watch_states():
    """Poll for changes in Meta/states/ every 30s."""
    print(f"[bridge] WATCH mode active. Polling {STATE_DIR} every 30s...")
    last_hashes = {}
    for f in STATE_DIR.glob("*.md"):
        last_hashes[str(f)] = file_hash(f)

    while True:
        time.sleep(30)
        changed = []
        for f in STATE_DIR.glob("*.md"):
            key = str(f)
            h = file_hash(f)
            if key not in last_hashes or last_hashes[key] != h:
                changed.append(f.name)
                last_hashes[key] = h

        if changed:
            print(f"[bridge] Detected changes: {', '.join(changed)}")
            manifest = load_manifest()
            synced = sync_states_to_vault(manifest)
            save_manifest(manifest)
            print(f"[bridge] Synced {len(synced)} files to vault.")
        else:
            # Low-frequency heartbeat
            print(".", end="", flush=True)


# ══════════════════════════════════════════════════════════════════════════
#  Main
# ══════════════════════════════════════════════════════════════════════════


def main():
    parser = argparse.ArgumentParser(description="Ruflow/Gracia Bridge Agent v2")
    parser.add_argument("--watch", action="store_true", help="Continuous file watch mode")
    parser.add_argument("--backtest", action="store_true", help="Sync backtest results only")
    parser.add_argument("--graph", action="store_true", help="Rebuild graph only")
    args = parser.parse_args()

    # Validate vault access
    if not VAULT.exists():
        print(f"[bridge] ERROR: Vault not found at {VAULT}")
        print("[bridge] Set OBSIDIAN_VAULT_PATH or ensure default path exists.")
        sys.exit(1)

    if args.watch:
        # Continuous watch (upgrade 1)
        manifest = load_manifest()
        sync_states_to_vault(manifest)
        save_manifest(manifest)
        print("[bridge] Initial sync complete. Entering watch mode.")
        watch_states()
        return

    manifest = load_manifest()
    all_synced = []

    if args.backtest:
        print("[bridge] Backtest-only sync...")
        all_synced += sync_backtest_to_inbox(manifest)
    elif args.graph:
        print("[bridge] Graph-only rebuild...")
        all_synced += sync_knowledge_graph(manifest)
    else:
        # Full sync (all 4 upgrades)
        print("[bridge] Full sync — all 4 upgrades...")
        all_synced += sync_states_to_vault(manifest)
        all_synced += sync_backtest_to_inbox(manifest)
        all_synced += sync_strategy_risk_to_vault(manifest)
        all_synced += sync_knowledge_graph(manifest)

    save_manifest(manifest)

    # Report
    copied = [s for s in all_synced if s[2] == "copied"]
    skipped = [s for s in all_synced if s[2] == "skipped"]
    print("\n[bridge] === Sync Summary ===")
    print(f"[bridge] Files copied: {len(copied)}")
    print(f"[bridge] Files skipped (unchanged): {len(skipped)}")
    for cat, path, status in copied:
        print(f"  + [{cat}] {path}")
    print("[bridge] ====================")

    # Update bridge handoff state
    _update_bridge_state(len(copied), len(all_synced))


def _update_bridge_state(copied: int, total: int):
    """Append a sync entry to the bridge state file."""
    now = datetime.now(UTC).strftime("%Y-%m-%d %H:%M UTC")
    entry = f"\n- {now} | bridge_automated_sync.py | {copied}/{total} files synced\n"
    state_file = STATE_DIR / "bridge_state.md"
    if state_file.exists():
        existing = state_file.read_text(encoding="utf-8")
        state_file.write_text(existing + entry, encoding="utf-8")
    else:
        state_file.write_text(
            f"# Bridge State\n\nTracking automated syncs.\n{entry}",
            encoding="utf-8",
        )


if __name__ == "__main__":
    main()
