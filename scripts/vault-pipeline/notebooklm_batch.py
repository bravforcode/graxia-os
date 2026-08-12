"""
notebooklm_batch.py — Batch create notebooks and add sources via MCP protocol
"""

import asyncio
import json
import os
from pathlib import Path

# MCP client imports
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

# ═══════════════════════════════════════════════════════════════
# NOTEBOOK DEFINITIONS — maximum coverage
# ═══════════════════════════════════════════════════════════════

NOTEBOOKS = {
    # ── STRATEGY NOTEBOOKS (13) ──
    "strategy-bos-choch": {
        "name": "Strategy: BOS/CHOCH",
        "desc": "Break of Structure / Change of Character strategy analysis, entries, exits, and backtest results",
        "sources": [
            (
                "Strategy: BOS/CHOCH",
                (STRATEGIES / "bos_choch.md").read_text(encoding="utf-8")
                if (STRATEGIES / "bos_choch.md").exists()
                else "No data",
            ),
        ],
    },
    "strategy-ema-cross": {
        "name": "Strategy: EMA Cross",
        "desc": "EMA crossover strategy for trend following, multi-timeframe analysis",
        "sources": [
            (
                "Strategy: EMA Cross",
                (STRATEGIES / "ema_cross.md").read_text(encoding="utf-8")
                if (STRATEGIES / "ema_cross.md").exists()
                else "No data",
            ),
        ],
    },
    "strategy-fvg": {
        "name": "Strategy: Fair Value Gap",
        "desc": "Fair Value Gap (FVG) imbalances strategy, institutional order flow",
        "sources": [
            (
                "Strategy: Fair Value Gap",
                (STRATEGIES / "fair_value_gap.md").read_text(encoding="utf-8")
                if (STRATEGIES / "fair_value_gap.md").exists()
                else "No data",
            ),
        ],
    },
    "strategy-fibonacci": {
        "name": "Strategy: Fibonacci",
        "desc": "Fibonacci retracement and extension strategy, confluence zones",
        "sources": [
            (
                "Strategy: Fibonacci",
                (STRATEGIES / "fibonacci.md").read_text(encoding="utf-8")
                if (STRATEGIES / "fibonacci.md").exists()
                else "No data",
            ),
        ],
    },
    "strategy-liquidity-sweep": {
        "name": "Strategy: Liquidity Sweep",
        "desc": "Liquidity sweep strategy, stop hunt detection, institutional manipulation",
        "sources": [
            (
                "Strategy: Liquidity Sweep",
                (STRATEGIES / "liquidity_sweep.md").read_text(encoding="utf-8")
                if (STRATEGIES / "liquidity_sweep.md").exists()
                else "No data",
            ),
        ],
    },
    "strategy-london-breakout": {
        "name": "Strategy: London Breakout",
        "desc": "London session breakout strategy, volatility expansion patterns",
        "sources": [
            (
                "Strategy: London Breakout",
                (STRATEGIES / "london_breakout.md").read_text(encoding="utf-8")
                if (STRATEGIES / "london_breakout.md").exists()
                else "No data",
            ),
        ],
    },
    "strategy-multi-tf": {
        "name": "Strategy: Multi-TF Alignment",
        "desc": "Multi-timeframe alignment strategy, confluence across timeframes",
        "sources": [
            (
                "Strategy: Multi-TF Align",
                (STRATEGIES / "multi_tf_align.md").read_text(encoding="utf-8")
                if (STRATEGIES / "multi_tf_align.md").exists()
                else "No data",
            ),
        ],
    },
    "strategy-news-fade": {
        "name": "Strategy: News Fade",
        "desc": "News fade strategy, trading against impulse moves after news releases",
        "sources": [
            (
                "Strategy: News Fade",
                (STRATEGIES / "news_fade.md").read_text(encoding="utf-8")
                if (STRATEGIES / "news_fade.md").exists()
                else "No data",
            ),
        ],
    },
    "strategy-opening-range": {
        "name": "Strategy: Opening Range",
        "desc": "Opening range breakout strategy, first hour/15min range expansion",
        "sources": [
            (
                "Strategy: Opening Range",
                (STRATEGIES / "opening_range.md").read_text(encoding="utf-8")
                if (STRATEGIES / "opening_range.md").exists()
                else "No data",
            ),
        ],
    },
    "strategy-order-block": {
        "name": "Strategy: Order Block",
        "desc": "Order block strategy, institutional supply/demand zones, mitigation entries",
        "sources": [
            (
                "Strategy: Order Block",
                (STRATEGIES / "order_block.md").read_text(encoding="utf-8")
                if (STRATEGIES / "order_block.md").exists()
                else "No data",
            ),
        ],
    },
    "strategy-rsi-divergence": {
        "name": "Strategy: RSI Divergence",
        "desc": "RSI divergence strategy, momentum shifts, hidden and regular divergences",
        "sources": [
            (
                "Strategy: RSI Divergence",
                (STRATEGIES / "rsi_divergence.md").read_text(encoding="utf-8")
                if (STRATEGIES / "rsi_divergence.md").exists()
                else "No data",
            ),
        ],
    },
    "strategy-supply-demand": {
        "name": "Strategy: Supply/Demand",
        "desc": "Supply and demand zone strategy, fresh vs tested zones, rally-base-rally patterns",
        "sources": [
            (
                "Strategy: Supply/Demand",
                (STRATEGIES / "supply_demand.md").read_text(encoding="utf-8")
                if (STRATEGIES / "supply_demand.md").exists()
                else "No data",
            ),
        ],
    },
    "strategy-vwap-rejection": {
        "name": "Strategy: VWAP Rejection",
        "desc": "VWAP rejection strategy, mean reversion from VWAP, intraday levels",
        "sources": [
            (
                "Strategy: VWAP Rejection",
                (STRATEGIES / "vwap_rejection.md").read_text(encoding="utf-8")
                if (STRATEGIES / "vwap_rejection.md").exists()
                else "No data",
            ),
        ],
    },
    # ── BACKTEST NOTEBOOKS (5) ──
    "backtest-xauusd": {
        "name": "Backtest: XAUUSD Analysis",
        "desc": "XAUUSD gold backtest results across all strategies and timeframes",
        "sources": [],
    },
    "backtest-multi-symbol": {
        "name": "Backtest: Multi-Symbol Suite",
        "desc": "Complete backtest suite: XAUUSD, EURUSD, GBPUSD, USDJPY, US30, NAS100, BTCUSD",
        "sources": [],
    },
    "backtest-strategies": {
        "name": "Backtest: Strategy Comparison",
        "desc": "Strategy performance comparison across all symbols and timeframes",
        "sources": [],
    },
    "backtest-mtm-mrb-mlb": {
        "name": "Backtest: MTM/MRB/MLB",
        "desc": "Mean Trend Momentum / Mean Reversion Bias / Mean Linear Bias strategy results",
        "sources": [],
    },
    "backtest-cost-analysis": {
        "name": "Backtest: Cost Analysis",
        "desc": "Transaction cost impact analysis, spread and commission effects on strategy returns",
        "sources": [],
    },
    # ── MACRO NOTEBOOKS (6) ──
    "macro-dashboard": {
        "name": "Macro: Daily Dashboard",
        "desc": "Daily macro overview: VIX, GVZ, DXY, yields, regime detection, key events",
        "sources": [],
    },
    "macro-yields": {
        "name": "Macro: Yield Curve",
        "desc": "US yield curve analysis, real yields, inflation expectations, term premium",
        "sources": [],
    },
    "macro-credit": {
        "name": "Macro: Credit Markets",
        "desc": "Credit spreads, HY OAS, financial stress indicators, corporate bond markets",
        "sources": [],
    },
    "macro-liquidity": {
        "name": "Macro: Liquidity",
        "desc": "Market liquidity: Fed balance sheet, RRP, TGA, net reserves, plumbing",
        "sources": [],
    },
    "macro-cross-market": {
        "name": "Macro: Cross-Market",
        "desc": "Cross-market correlations: equities, bonds, FX, commodities, volatility",
        "sources": [],
    },
    "macro-weekly": {
        "name": "Macro: Weekly Review",
        "desc": "Weekly macro summary, key themes, regime shifts, outlook",
        "sources": [],
    },
    # ── ML/MODEL NOTEBOOKS (4) ──
    "ml-model-registry": {
        "name": "ML: Model Registry",
        "desc": "All ML models: XGBoost, LightGBM, training metrics, feature importance",
        "sources": [],
    },
    "ml-training-results": {
        "name": "ML: Training Results",
        "desc": "Model training history, hyperparameters, validation scores, overfitting analysis",
        "sources": [],
    },
    "ml-feature-importance": {
        "name": "ML: Feature Importance",
        "desc": "Feature importance rankings, SHAP values, feature engineering notes",
        "sources": [],
    },
    "ml-live-performance": {
        "name": "ML: Live Performance",
        "desc": "Live model predictions, accuracy tracking, drift detection, retraining triggers",
        "sources": [],
    },
    # ── TRADING OPS NOTEBOOKS (6) ──
    "trade-journal": {
        "name": "Trade Journal",
        "desc": "Live trade journal: entries, exits, P&L, lessons learned, emotional notes",
        "sources": [],
    },
    "risk-management": {
        "name": "Risk Management",
        "desc": "Risk dashboard: drawdown, circuit breaker, kill switch, position sizing, exposure",
        "sources": [],
    },
    "regime-analysis": {
        "name": "Regime Analysis",
        "desc": "Market regime detection: trending, ranging, volatile, regime transitions",
        "sources": [],
    },
    "signal-quality": {
        "name": "Signal Quality",
        "desc": "Signal quality metrics: hit rate, false positive analysis, signal decay",
        "sources": [],
    },
    "attribution": {
        "name": "P&L Attribution",
        "desc": "P&L attribution by strategy, symbol, timeframe, session, market condition",
        "sources": [],
    },
    "ensemble-optimizer": {
        "name": "Ensemble Optimizer",
        "desc": "Ensemble weight optimization: MTM, MRB, MLB allocation, dynamic rebalancing",
        "sources": [],
    },
    # ── SYSTEM NOTEBOOKS (4) ──
    "system-architecture": {
        "name": "System Architecture",
        "desc": "Trading system architecture: components, data flow, execution pipeline, integration points",
        "sources": [],
    },
    "xauusd-playbook": {
        "name": "XAUUSD Playbook",
        "desc": "Complete XAUUSD trading playbook: all strategies, macro context, regime notes",
        "sources": [],
    },
    "multi-asset-overview": {
        "name": "Multi-Asset Overview",
        "desc": "Cross-asset analysis: correlations, relative strength, sector rotation",
        "sources": [],
    },
    "daily-briefing": {
        "name": "Daily Briefing",
        "desc": "Daily pre-market briefing: overnight moves, key levels, economic calendar, risk events",
        "sources": [],
    },
}


def collect_sources():
    """Collect all available sources for each notebook"""

    # Backtest sources
    backtest_files = list(BACKTEST.glob("*.md"))
    backtest_json = (
        list((QUANT / "results").glob("backtest_*.json"))
        if (QUANT / "results").exists()
        else []
    )

    for f in backtest_files:
        content = f.read_text(encoding="utf-8")
        title = f.stem
        if "xauusd" in f.name.lower():
            NOTEBOOKS["backtest-xauusd"]["sources"].append((title, content))
        NOTEBOOKS["backtest-multi-symbol"]["sources"].append((title, content))
        NOTEBOOKS["backtest-strategies"]["sources"].append((title, content))

    for f in backtest_json:
        content = f.read_text(encoding="utf-8")
        if len(content) > 50000:
            content = content[:50000]
        NOTEBOOKS["backtest-cost-analysis"]["sources"].append((f.stem, content))
        if (
            "mtm" in f.name.lower()
            or "mlb" in f.name.lower()
            or "mrb" in f.name.lower()
        ):
            NOTEBOOKS["backtest-mtm-mrb-mlb"]["sources"].append((f.stem, content))

    # MTM/MRB/MLB specific
    mtm_files = (
        list(BACKTEST.glob("*MTM*"))
        + list(BACKTEST.glob("*MRB*"))
        + list(BACKTEST.glob("*MLB*"))
    )
    for f in mtm_files:
        content = f.read_text(encoding="utf-8")
        NOTEBOOKS["backtest-mtm-mrb-mlb"]["sources"].append((f.stem, content))

    # Macro sources
    for f in MACRO.glob("*.md"):
        content = f.read_text(encoding="utf-8")
        title = f.stem
        if "yield" in f.name.lower():
            NOTEBOOKS["macro-yields"]["sources"].append((title, content))
        if "credit" in f.name.lower():
            NOTEBOOKS["macro-credit"]["sources"].append((title, content))
        if "liquid" in f.name.lower():
            NOTEBOOKS["macro-liquidity"]["sources"].append((title, content))
        if "cross" in f.name.lower():
            NOTEBOOKS["macro-cross-market"]["sources"].append((title, content))
        if "weekly" in f.name.lower():
            NOTEBOOKS["macro-weekly"]["sources"].append((title, content))
        NOTEBOOKS["macro-dashboard"]["sources"].append((title, content))

    # Model sources
    model_files = list(MODELS.glob("*.md"))
    for f in model_files:
        content = f.read_text(encoding="utf-8")
        NOTEBOOKS["ml-model-registry"]["sources"].append((f.stem, content))

    # ML training results
    ml_results = QUANT / "results" / "ml_training_results.json"
    if ml_results.exists():
        content = ml_results.read_text(encoding="utf-8")
        if len(content) > 50000:
            content = content[:50000]
        NOTEBOOKS["ml-training-results"]["sources"].append(
            ("ml_training_results", content)
        )

    # Trade journal
    for f in TRADES.glob("*.md"):
        content = f.read_text(encoding="utf-8")
        NOTEBOOKS["trade-journal"]["sources"].append((f.stem, content))

    # Risk
    risk_files = list((TRADING / "risk").glob("*.md"))
    for f in risk_files:
        content = f.read_text(encoding="utf-8")
        NOTEBOOKS["risk-management"]["sources"].append((f.stem, content))

    # Regime
    regime_files = list((TRADING / "regime").glob("*.md"))
    for f in regime_files:
        content = f.read_text(encoding="utf-8")
        NOTEBOOKS["regime-analysis"]["sources"].append((f.stem, content))

    # Signals
    signal_files = list((TRADING / "signals").glob("*.md"))
    for f in signal_files:
        content = f.read_text(encoding="utf-8")
        NOTEBOOKS["signal-quality"]["sources"].append((f.stem, content))

    # Attribution
    attr_files = list((TRADING / "attribution").glob("*.md"))
    for f in attr_files:
        content = f.read_text(encoding="utf-8")
        NOTEBOOKS["attribution"]["sources"].append((f.stem, content))

    # Ensemble
    ens_files = list((TRADING / "ensemble").glob("*.md"))
    for f in ens_files:
        content = f.read_text(encoding="utf-8")
        NOTEBOOKS["ensemble-optimizer"]["sources"].append((f.stem, content))

    # XAUUSD playbook — gather all XAUUSD-specific content
    xauusd_notes = [f for f in backtest_files if "xauusd" in f.name.lower()]
    for f in xauusd_notes:
        content = f.read_text(encoding="utf-8")
        NOTEBOOKS["xauusd-playbook"]["sources"].append((f.stem, content))

    # Multi-asset overview — gather all strategy notes
    for f in STRATEGIES.glob("*.md"):
        if f.name == "Index.md":
            continue
        content = f.read_text(encoding="utf-8")
        NOTEBOOKS["multi-asset-overview"]["sources"].append((f.stem, content))

    # System architecture — read quant_os structure
    arch_notes = []
    for md_file in (QUANT / "Meta").glob("*.md"):
        content = md_file.read_text(encoding="utf-8")
        NOTEBOOKS["system-architecture"]["sources"].append((md_file.stem, content))

    # Daily briefing — latest macro + regime
    for f in MACRO.glob("*.md"):
        content = f.read_text(encoding="utf-8")
        NOTEBOOKS["daily-briefing"]["sources"].append((f.stem, content))

    for f in regime_files:
        content = f.read_text(encoding="utf-8")
        NOTEBOOKS["daily-briefing"]["sources"].append((f.stem, content))


async def run_mcp():
    """Run MCP operations"""
    collect_sources()

    server_params = StdioServerParameters(
        command="npx",
        args=["-y", "notebooklm-mcp@latest"],
    )

    results = {"created": [], "sources_added": [], "errors": []}

    async with stdio_client(server_params) as (read_stream, write_stream):
        async with ClientSession(read_stream, write_stream) as session:
            await session.initialize()

            # List existing notebooks
            existing = await session.call_tool("list_notebooks", {})
            print(f"Existing notebooks: {existing}")

            # Create all notebooks
            for nb_id, nb in NOTEBOOKS.items():
                try:
                    print(f"\n{'='*60}")
                    print(f"Creating: {nb['name']}")
                    print(f"  Sources: {len(nb['sources'])}")

                    result = await session.call_tool(
                        "add_notebook", {"name": nb["name"], "description": nb["desc"]}
                    )
                    results["created"].append(nb["name"])
                    print("  [OK] Created")

                    # Add sources
                    for source_title, source_text in nb["sources"]:
                        if not source_text or source_text == "No data":
                            continue
                        # Truncate very long sources
                        if len(source_text) > 30000:
                            source_text = (
                                source_text[:30000]
                                + "\n\n[TRUNCATED - content too long]"
                            )

                        try:
                            src_result = await session.call_tool(
                                "add_source",
                                {
                                    "notebook_name": nb["name"],
                                    "source_type": "text",
                                    "text": source_text,
                                    "title": source_title,
                                },
                            )
                            results["sources_added"].append(
                                f"{nb['name']}/{source_title}"
                            )
                            print(f"    [OK] Source: {source_title}")
                        except Exception as e:
                            print(f"    [FAIL] Source failed: {source_title}: {e}")
                            results["errors"].append(
                                f"{nb['name']}/{source_title}: {e}"
                            )

                except Exception as e:
                    print(f"  [FAIL] Failed: {e}")
                    results["errors"].append(f"{nb['name']}: {e}")

    return results


def main():
    print("=" * 60)
    print("  NOTEBOOKLM BATCH NOTEBOOK CREATOR")
    print(f"  Notebooks: {len(NOTEBOOKS)}")
    print("=" * 60)

    results = asyncio.run(run_mcp())

    print("\n" + "=" * 60)
    print("  RESULTS")
    print("=" * 60)
    print(f"  Created: {len(results['created'])}")
    print(f"  Sources: {len(results['sources_added'])}")
    print(f"  Errors:  {len(results['errors'])}")

    if results["errors"]:
        print("\n  ERRORS:")
        for e in results["errors"]:
            print(f"    - {e}")

    # Save results
    output_file = Path(__file__).parent / "notebooklm_registry.json"
    registry = {
        "created_at": str(__import__("datetime").datetime.now()),
        "notebooks": {},
        "results": results,
    }
    for nb_id, nb in NOTEBOOKS.items():
        registry["notebooks"][nb_id] = {
            "name": nb["name"],
            "desc": nb["desc"],
            "source_count": len(nb["sources"]),
            "sources": [s[0] for s in nb["sources"]],
        }

    output_file.write_text(
        json.dumps(registry, indent=2, default=str), encoding="utf-8"
    )
    print(f"\n  Registry saved: {output_file}")

    return results


if __name__ == "__main__":
    main()
