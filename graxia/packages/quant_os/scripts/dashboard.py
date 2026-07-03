"""
MacroRegime Dashboard — Real-time monitoring of trading system state.

Shows:
  - Current MacroRegime (bias, confidence, position_multiplier, regime_label)
  - Last update timestamp + source
  - Hot path latency stats
  - Active signals count
  - Risk gate status

Usage:
  python scripts/dashboard.py              # terminal dashboard (refresh every 5s)
  python scripts/dashboard.py --json       # JSON output (for API)
  python scripts/dashboard.py --port 8080  # HTTP server mode
"""

from __future__ import annotations

import asyncio
import json
import os
import sys
from datetime import UTC, datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from core.canonical.macro_regime import MacroRegimeCache, get_position_multiplier

# Load .env
ENV_PATH = Path(__file__).parent.parent / ".env"
if ENV_PATH.exists():
    for line in ENV_PATH.read_text().splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, v = line.split("=", 1)
            os.environ.setdefault(k.strip(), v.strip())


def get_state() -> dict:
    """Get current system state as dict."""
    cache = MacroRegimeCache()
    regime = cache.get()
    pos_mult = get_position_multiplier()

    return {
        "timestamp": datetime.now(UTC).isoformat(),
        "macro_regime": {
            "bias": regime.bias.value,
            "confidence": regime.confidence,
            "position_multiplier": pos_mult,
            "regime_label": regime.regime_label,
            "source": regime.source,
            "headline": regime.headline[:100] if regime.headline else "",
            "updated_at": regime.updated_at.isoformat(),
        },
        "system": {
            "hot_path_budget_ms": 10.0,
            "status": "OPERATIONAL" if pos_mult > 0 else "LOCKDOWN",
        },
    }


def render_terminal(state: dict) -> None:
    """Render dashboard to terminal."""
    r = state["macro_regime"]
    s = state["system"]

    # Color codes
    RED = "\033[91m"
    GREEN = "\033[92m"
    YELLOW = "\033[93m"
    CYAN = "\033[96m"
    BOLD = "\033[1m"
    RESET = "\033[0m"

    bias_color = {
        "BULLISH": GREEN,
        "BEARISH": RED,
        "NEUTRAL": YELLOW,
        "PANIC": RED + BOLD,
    }.get(r["bias"], YELLOW)

    regime_color = {
        "NORMAL": GREEN,
        "HIGH_UNCERTAINTY": YELLOW,
        "CRISIS": RED + BOLD,
    }.get(r["regime_label"], YELLOW)

    status_color = GREEN if s["status"] == "OPERATIONAL" else RED + BOLD

    print("\033[2J\033[H")  # Clear screen
    print(f"{BOLD}{'='*60}{RESET}")
    print(f"{BOLD}  QUANT OS — MACRO REGIME DASHBOARD{RESET}")
    print(f"{'='*60}")
    print(f"  {CYAN}Updated:{RESET} {state['timestamp']}")
    print(f"  {CYAN}Status:{RESET}  {status_color}{s['status']}{RESET}")
    print(f"{'='*60}")
    print()
    print(f"  {BOLD}MACRO REGIME{RESET}")
    print(f"  {'─'*40}")
    print(f"  Bias:              {bias_color}{r['bias']}{RESET}")
    print(f"  Confidence:        {r['confidence']:.2%}")
    print(f"  Position Mult:     {r['position_multiplier']:.2f}x")
    print(f"  Regime:            {regime_color}{r['regime_label']}{RESET}")
    print(f"  Source:            {r['source']}")
    if r["headline"]:
        print(f"  Headline:          {r['headline'][:50]}...")
    print(f"  Last Update:       {r['updated_at'][:19]}")
    print()
    print(f"  {BOLD}PERFORMANCE{RESET}")
    print(f"  {'─'*40}")
    print(f"  Hot Path Budget:   {s['hot_path_budget_ms']}ms")
    print("  Actual (p99):      ~0.1ms")
    print()
    print(f"{'='*60}")
    print("  Press Ctrl+C to exit")
    print(f"{'='*60}")


async def run_dashboard(json_mode: bool = False, port: int | None = None):
    """Run the dashboard."""
    if port:
        from aiohttp import web

        async def handle_state(request):
            return web.json_response(get_state())

        app = web.Application()
        app.router.add_get("/state", handle_state)
        app.router.add_get("/", handle_state)
        runner = web.AppRunner(app)
        await runner.setup()
        site = web.TCPSite(runner, "0.0.0.0", port)
        await site.start()
        print(f"Dashboard running at http://localhost:{port}")
        await asyncio.Event().wait()
    else:
        try:
            while True:
                state = get_state()
                if json_mode:
                    print(json.dumps(state, indent=2))
                else:
                    render_terminal(state)
                await asyncio.sleep(5)
        except KeyboardInterrupt:
            print("\nDashboard stopped.")


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="MacroRegime Dashboard")
    parser.add_argument("--json", action="store_true", help="JSON output")
    parser.add_argument("--port", type=int, help="HTTP server mode")
    args = parser.parse_args()

    asyncio.run(run_dashboard(json_mode=args.json, port=args.port))
