"""
notebooklm_batch_v2.py — Create notebooks, select each, add sources
"""

import asyncio
import json
import os
from pathlib import Path
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

VAULT = Path(os.environ["USERPROFILE"]) / "Documents" / "ObsidianVault" / "Second Brain"
QUANT = (
    Path(os.environ["USERPROFILE"]) / "graxia os" / "graxia" / "packages" / "quant_os"
)
TRADING = VAULT / "03-resources" / "trading"
STRATEGIES = VAULT / "skills" / "trading" / "strategies"
MACRO = TRADING / "macro"
BACKTEST = TRADING / "backtest"
MODELS = TRADING / "models"
TRADES = VAULT / "07-Daily" / "trades"


def read_file(p):
    try:
        return p.read_text(encoding="utf-8")
    except:
        return ""


def collect_all_sources():
    sources = {}

    # Strategy sources
    for f in STRATEGIES.glob("*.md"):
        if f.name == "Index.md":
            continue
        sources[f"strategy-{f.stem}"] = [("Strategy: " + f.stem, read_file(f))]

    # Backtest sources
    bt_files = list(BACKTEST.glob("*.md"))
    xauusd = [f for f in bt_files if "xauusd" in f.name.lower()]
    sources["backtest-xauusd"] = [(f.stem, read_file(f)) for f in xauusd]
    sources["backtest-multi-symbol"] = [(f.stem, read_file(f)) for f in bt_files]
    sources["backtest-strategies"] = [(f.stem, read_file(f)) for f in bt_files]

    # MTM/MRB/MLB
    mtm = (
        list(BACKTEST.glob("*MTM*"))
        + list(BACKTEST.glob("*MRB*"))
        + list(BACKTEST.glob("*MLB*"))
    )
    sources["backtest-mtm-mrb-mlb"] = [(f.stem, read_file(f)) for f in mtm]

    # Cost analysis
    bq = (
        list((QUANT / "results").glob("backtest_*.json"))
        if (QUANT / "results").exists()
        else []
    )
    sources["backtest-cost-analysis"] = [(f.stem, read_file(f)[:30000]) for f in bq]

    # Macro sources
    for f in MACRO.glob("*.md"):
        content = read_file(f)
        key = "macro-dashboard"
        if "yield" in f.name.lower():
            key = "macro-yields"
        elif "credit" in f.name.lower():
            key = "macro-credit"
        elif "liquid" in f.name.lower():
            key = "macro-liquidity"
        elif "cross" in f.name.lower():
            key = "macro-cross-market"
        elif "weekly" in f.name.lower():
            key = "macro-weekly"
        sources.setdefault(key, []).append((f.stem, content))

    # Model sources
    for f in MODELS.glob("*.md"):
        sources.setdefault("ml-model-registry", []).append((f.stem, read_file(f)))

    # ML training results
    mlr = QUANT / "results" / "ml_training_results.json"
    if mlr.exists():
        sources["ml-training-results"] = [
            ("ml_training_results", read_file(mlr)[:30000])
        ]

    # Trade journal
    for f in TRADES.glob("*.md"):
        sources.setdefault("trade-journal", []).append((f.stem, read_file(f)))

    # Risk
    for f in (TRADING / "risk").glob("*.md"):
        sources.setdefault("risk-management", []).append((f.stem, read_file(f)))

    # Regime
    for f in (TRADING / "regime").glob("*.md"):
        sources.setdefault("regime-analysis", []).append((f.stem, read_file(f)))

    # Signals
    for f in (TRADING / "signals").glob("*.md"):
        sources.setdefault("signal-quality", []).append((f.stem, read_file(f)))

    # Attribution
    for f in (TRADING / "attribution").glob("*.md"):
        sources.setdefault("attribution", []).append((f.stem, read_file(f)))

    # Ensemble
    for f in (TRADING / "ensemble").glob("*.md"):
        sources.setdefault("ensemble-optimizer", []).append((f.stem, read_file(f)))

    # System architecture
    meta = QUANT / "Meta"
    if meta.exists():
        for f in meta.glob("*.md"):
            sources.setdefault("system-architecture", []).append((f.stem, read_file(f)))

    # XAUUSD playbook
    sources["xauusd-playbook"] = [(f.stem, read_file(f)) for f in xauusd]

    # Multi-asset overview (all strategies)
    for f in STRATEGIES.glob("*.md"):
        if f.name != "Index.md":
            sources.setdefault("multi-asset-overview", []).append(
                (f.stem, read_file(f))
            )

    # Daily briefing
    for f in MACRO.glob("*.md"):
        sources.setdefault("daily-briefing", []).append((f.stem, read_file(f)))
    for f in (TRADING / "regime").glob("*.md"):
        sources.setdefault("daily-briefing", []).append((f.stem, read_file(f)))

    return sources


NOTEBOOK_MAP = {
    "strategy-bos-choch": (
        "Strategy: BOS/CHOCH",
        "Break of Structure / Change of Character",
    ),
    "strategy-ema-cross": ("Strategy: EMA Cross", "EMA crossover trend following"),
    "strategy-fair_value_gap": (
        "Strategy: Fair Value Gap",
        "FVG imbalances, institutional flow",
    ),
    "strategy-fibonacci": ("Strategy: Fibonacci", "Retracement and extension levels"),
    "strategy-liquidity_sweep": ("Strategy: Liquidity Sweep", "Stop hunt detection"),
    "strategy-london_breakout": (
        "Strategy: London Breakout",
        "London session volatility",
    ),
    "strategy-multi_tf_align": (
        "Strategy: Multi-TF Alignment",
        "Multi-timeframe confluence",
    ),
    "strategy-news_fade": ("Strategy: News Fade", "Fade impulse after news"),
    "strategy-opening_range": ("Strategy: Opening Range", "First hour breakout"),
    "strategy-order_block": ("Strategy: Order Block", "Institutional supply/demand"),
    "strategy-rsi_divergence": ("Strategy: RSI Divergence", "Momentum shifts"),
    "strategy-supply_demand": ("Strategy: Supply/Demand", "Zone-based trading"),
    "strategy-vwap_rejection": ("Strategy: VWAP Rejection", "Mean reversion from VWAP"),
    "backtest-xauusd": ("Backtest: XAUUSD", "Gold backtest results"),
    "backtest-multi-symbol": ("Backtest: Multi-Symbol", "All symbols backtest"),
    "backtest-strategies": (
        "Backtest: Strategy Comparison",
        "Strategy perf comparison",
    ),
    "backtest-mtm-mrb-mlb": ("Backtest: MTM/MRB/MLB", "Three strategy variants"),
    "backtest-cost-analysis": ("Backtest: Cost Analysis", "Transaction cost impact"),
    "macro-dashboard": ("Macro: Dashboard", "Daily macro overview"),
    "macro-yields": ("Macro: Yield Curve", "US yield analysis"),
    "macro-credit": ("Macro: Credit Markets", "Credit spreads"),
    "macro-liquidity": ("Macro: Liquidity", "Fed, RRP, TGA"),
    "macro-cross-market": ("Macro: Cross-Market", "Cross-asset correlations"),
    "macro-weekly": ("Macro: Weekly Review", "Weekly summary"),
    "ml-model-registry": ("ML: Model Registry", "All ML models"),
    "ml-training-results": ("ML: Training Results", "Training history"),
    "ml-feature-importance": ("ML: Feature Importance", "Feature rankings"),
    "ml-live-performance": ("ML: Live Performance", "Live predictions"),
    "trade-journal": ("Trade Journal", "Live trades and P&L"),
    "risk-management": ("Risk Management", "Drawdown, circuit breaker"),
    "regime-analysis": ("Regime Analysis", "Market regime detection"),
    "signal-quality": ("Signal Quality", "Hit rate, false positives"),
    "attribution": ("P&L Attribution", "P&L by strategy/symbol"),
    "ensemble-optimizer": ("Ensemble Optimizer", "Weight optimization"),
    "system-architecture": ("System Architecture", "Trading system design"),
    "xauusd-playbook": ("XAUUSD Playbook", "Gold trading playbook"),
    "multi-asset-overview": ("Multi-Asset Overview", "Cross-asset analysis"),
    "daily-briefing": ("Daily Briefing", "Pre-market briefing"),
}


async def run():
    all_sources = collect_all_sources()

    params = StdioServerParameters(command="npx", args=["-y", "notebooklm-mcp@latest"])
    results = {"created": 0, "sources_ok": 0, "sources_fail": 0, "errors": []}

    async with stdio_client(params) as (r, w):
        async with ClientSession(r, w) as s:
            await s.initialize()

            for nb_id, (nb_name, nb_desc) in NOTEBOOK_MAP.items():
                print(f"\n--- {nb_name} ---")

                # Create notebook
                try:
                    await s.call_tool(
                        "add_notebook", {"name": nb_name, "description": nb_desc}
                    )
                    results["created"] += 1
                    print("  [OK] Created")
                except Exception as e:
                    if "already" not in str(e).lower():
                        print(f"  [FAIL] Create: {e}")
                        results["errors"].append(f"create {nb_id}: {e}")
                        continue

                # Select notebook
                try:
                    await s.call_tool("select_notebook", {"notebook_id": nb_id})
                except Exception as e:
                    print(f"  [WARN] Select: {e}")

                # Add sources
                src_list = all_sources.get(nb_id, [])
                for src_title, src_text in src_list:
                    if not src_text or len(src_text.strip()) < 10:
                        continue
                    if len(src_text) > 40000:
                        src_text = src_text[:40000] + "\n[TRUNCATED]"

                    try:
                        await s.call_tool(
                            "add_source",
                            {
                                "type": "text",
                                "content": src_text,
                                "title": src_title,
                                "notebook_id": nb_id,
                            },
                        )
                        results["sources_ok"] += 1
                        print(f"    [OK] {src_title}")
                    except Exception as e:
                        results["sources_fail"] += 1
                        err_msg = str(e)[:80]
                        print(f"    [FAIL] {src_title}: {err_msg}")
                        results["errors"].append(f"{nb_id}/{src_title}: {err_msg}")

    return results


def main():
    print("=" * 50)
    print("  NOTEBOOKLM BATCH v2")
    print("=" * 50)

    results = asyncio.run(run())

    print("\n" + "=" * 50)
    print(f"  Created: {results['created']}")
    print(f"  Sources OK: {results['sources_ok']}")
    print(f"  Sources Fail: {results['sources_fail']}")
    print(f"  Errors: {len(results['errors'])}")

    if results["errors"]:
        print("\n  Sample errors:")
        for e in results["errors"][:5]:
            print(f"    - {e}")

    # Save registry
    out = Path(__file__).parent / "notebooklm_registry.json"
    out.write_text(json.dumps(results, indent=2, default=str), encoding="utf-8")
    print(f"\n  Saved: {out}")


if __name__ == "__main__":
    main()
