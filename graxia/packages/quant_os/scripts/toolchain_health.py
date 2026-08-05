"""One-shot health check for the quant_os toolchain (Opik, turbovec, toon, jcode,
AgentMemory, Second Brain, real data). Prints PASS/WARN per component, exit 0 if
all pass, 1 if any WARN.

Usage:
    python scripts/toolchain_health.py [--json]
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import socket
import subprocess
import sys

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OPIK_CONFIG = os.path.join(os.path.expanduser("~"), ".opik.config")


def _read_opik_config() -> dict:
    """Read .opik.config without printing the api key."""
    out: dict = {"found": False}
    try:
        with open(OPIK_CONFIG, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line or "=" not in line:
                    continue
                k, _, v = line.partition("=")
                k, v = k.strip(), v.strip().strip('"').strip("'")
                if k.lower() == "api_key":
                    out["api_key_set"] = bool(v)
                else:
                    out[k.lower()] = v
        out["found"] = True
    except OSError:
        pass
    return out


def _read_mcp_json() -> set[str]:
    """Return the set of declared MCP server names in the project .mcp.json."""
    try:
        with open(os.path.join(BASE, ".mcp.json"), encoding="utf-8") as f:
            return set(json.load(f).get("mcpServers", {}).keys())
    except (OSError, ValueError):
        return set()


def _check(name: str, ok: bool, detail: str, results: list[dict]) -> None:
    results.append({"name": name, "status": "PASS" if ok else "WARN", "detail": detail})
    print(f"[{'PASS' if ok else 'WARN'}] {name}: {detail}")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()

    results: list[dict] = []

    # --- Opik ---
    cfg = _read_opik_config()
    try:
        import opik  # noqa: F401

        opik_ok = True
        opik_ver = getattr(opik, "__version__", "?")
    except ImportError:
        opik_ok, opik_ver = False, "not installed"
    proj = os.environ.get("OPIK_PROJECT_NAME") or cfg.get("project_name", "?")
    ws = os.environ.get("OPIK_WORKSPACE") or cfg.get("workspace", "?")
    _check(
        "opik",
        opik_ok and bool(cfg.get("api_key_set")) and proj == "quant_os" and ws == "phirawit-jitnarong",
        f"v{opik_ver} project={proj} workspace={ws} api_key={'set' if cfg.get('api_key_set') else 'MISSING'}",
        results,
    )

    # --- turbovec ---
    try:
        from turbovec import IdMapIndex, TurboQuantIndex  # noqa: F401

        tv_ok, tv_detail = True, "TurboQuantIndex + IdMapIndex import OK"
    except ImportError as e:
        tv_ok, tv_detail = False, f"import failed: {e}"
    _check("turbovec", tv_ok, tv_detail, results)

    # --- toon / jcode on PATH ---
    for tool, ver_flag in (("toon", "--version"), ("jcode", "--version")):
        path = shutil.which(tool)
        if path:
            try:
                r = subprocess.run([path, ver_flag], capture_output=True, text=True, timeout=15)
                ver = (r.stdout or r.stderr).strip().splitlines()[0][:60]
                _check(tool, r.returncode == 0, f"{path} -> {ver}", results)
            except (OSError, subprocess.TimeoutExpired) as e:
                _check(tool, False, f"{path} -> run failed: {e}", results)
        else:
            _check(tool, False, "not on PATH", results)

    # --- AgentMemory: stdio MCP server declared in .mcp.json (launched by the MCP client) ---
    mcp = _read_mcp_json()
    am_entry = "agentmemory-project" in mcp
    am_detail = "MCP entry 'agentmemory-project' declared" if am_entry else "MISSING from .mcp.json"
    try:
        with socket.create_connection(("127.0.0.1", 3111), timeout=2):
            am_detail += "; port 3111 listening"
    except OSError:
        am_detail += "; stdio MCP (no TCP port expected)"
    _check("agentmemory", am_entry, am_detail, results)

    # --- Second Brain: stdio MCP bridge script + .mcp.json entry ---
    sb_bridge = os.path.join(BASE, "second_brain_worker", "mcp_bridge.js")
    sb_entry = "second-brain" in mcp
    sb_ok = sb_entry and os.path.exists(sb_bridge)
    _check(
        "second-brain",
        sb_ok,
        f"MCP entry declared={sb_entry} bridge_script={'present' if os.path.exists(sb_bridge) else 'MISSING'}",
        results,
    )

    # --- real data files ---
    data_paths = [
        os.path.join(BASE, "data", "canonical", "XAUUSD_D1_clean.csv"),
        os.path.join(BASE, "data", "AUDUSD_H1.csv"),
        os.path.join(BASE, "data_pipeline", "storage", "quant_os.duckdb"),
    ]
    missing = [p for p in data_paths if not os.path.exists(p)]
    _check(
        "real-data",
        not missing,
        f"{len(data_paths) - len(missing)}/{len(data_paths)} present" + (f"; missing: {missing}" if missing else ""),
        results,
    )

    n_warn = sum(1 for r in results if r["status"] == "WARN")
    if args.json:
        print(json.dumps({"results": results, "warnings": n_warn}, indent=2))
    print(f"--- {len(results) - n_warn}/{len(results)} PASS, {n_warn} WARN ---")
    return 1 if n_warn else 0


if __name__ == "__main__":
    sys.exit(main())
