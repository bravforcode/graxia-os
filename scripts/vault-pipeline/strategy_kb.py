"""
Pipeline 3: Strategy Knowledge Base → Vault

Reads gold_bot strategy files, extracts key parameters, and generates
Obsidian vault notes in Second Brain\skills\trading\strategies\.

Usage:
    python scripts/vault-pipeline/strategy_kb.py              # all strategies
    python scripts/vault-pipeline/strategy_kb.py ema_cross rsi_divergence  # specific
"""

import ast
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path

# ── paths ────────────────────────────────────────────────────────────────────
ROOT = Path(r"C:\Users\menum\graxia os")
STRATEGY_DIR = ROOT / "graxia" / "packages" / "quant_os" / "gold_bot" / "strategies"
VAULT_DIR = Path(
    r"C:\Users\menum\Documents\ObsidianVault\Second Brain\skills\trading\strategies"
)

STRATEGY_FILES = [
    "bos_choch.py",
    "ema_cross.py",
    "fair_value_gap.py",
    "fibonacci.py",
    "liquidity_sweep.py",
    "london_breakout.py",
    "multi_tf_align.py",
    "news_fade.py",
    "opening_range.py",
    "order_block.py",
    "rsi_divergence.py",
    "supply_demand.py",
    "vwap_rejection.py",
]

# ── data model ───────────────────────────────────────────────────────────────


@dataclass
class StrategyInfo:
    filename: str
    class_name: str = ""
    name: str = ""
    description: str = ""
    min_timeframe: str = "M15"
    entry_conditions: list[str] = field(default_factory=list)
    exit_conditions: list[str] = field(default_factory=list)
    risk_params: list[str] = field(default_factory=list)
    timeframes_used: list[str] = field(default_factory=list)
    symbols: list[str] = field(default_factory=list)
    indicators: list[str] = field(default_factory=list)
    regime_filters: list[str] = field(default_factory=list)
    best_conditions: str = ""
    weaknesses: str = ""
    related: list[str] = field(default_factory=list)
    docstring: str = ""
    raw_source: str = ""


# ── extraction helpers ───────────────────────────────────────────────────────


def _extract_class_attrs(tree: ast.Module) -> dict:
    """Pull class-level attribute assignments (name, description, min_timeframe)."""
    attrs = {}
    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef):
            for item in node.body:
                if isinstance(item, ast.Assign):
                    for target in item.targets:
                        if isinstance(target, ast.Name) and target.id in (
                            "name",
                            "description",
                            "min_timeframe",
                        ):
                            if isinstance(item.value, ast.Constant):
                                attrs[target.id] = item.value.value
    return attrs


def _extract_docstrings(tree: ast.Module) -> str:
    """Get module docstring."""
    for node in ast.iter_child_nodes(tree):
        if isinstance(node, ast.Expr) and isinstance(node.value, ast.Constant):
            return str(node.value.value)
    return ""


def _find_timeframes_used(source: str) -> list[str]:
    """Find all timeframe strings referenced in source."""
    tfs = set()
    for m in re.finditer(r'"(M1|M5|M15|M30|H1|H4|D1|W1)"', source):
        tfs.add(m.group(1))
    return sorted(tfs)


def _find_indicators(source: str) -> list[str]:
    """Detect which indicators the strategy uses."""
    indicators = []
    patterns = {
        "EMA": r"ema\d+|_calc_ema",
        "RSI": r"rsi|_calc_rsi",
        "ATR": r"atr|_calc_atr",
        "VWAP": r"vwap|VWAP",
        "Volume": r"volume|_get_volume",
        "Fibonacci": r"fib_|fibonacci|Fibonacci",
        "Swing High/Low": r"swing_high|swing_low",
        "Supply/Demand Zones": r"demand.zone|supply.zone|avg_low|avg_high",
        "Order Blocks": r"order.block|ob_top|ob_bottom",
        "FVG": r"fvg_|fair.value.gap|Fair Value Gap",
        "Opening Range": r"or_high|or_low|opening.range",
        "London Range": r"london_range",
    }
    for name, pat in patterns.items():
        if re.search(pat, source, re.IGNORECASE):
            indicators.append(name)
    return indicators


def _extract_entry_rules(source: str, name: str) -> list[str]:
    """Generate plain-English entry rules from source logic."""
    rules = []

    # Directional entries
    if "SignalDirection.BUY" in source and "SignalDirection.SELL" in source:
        if "prev_diff <= 0 and curr_diff > 0" in source:
            rules.append("BUY when EMA 9 crosses above EMA 21")
        if "prev_diff >= 0 and curr_diff < 0" in source:
            rules.append("SELL when EMA 9 crosses below EMA 21")
        if "rsi < 35" in source or "rsi < 25" in source:
            rules.append("BUY when RSI drops below 35 (oversold)")
        if "rsi > 65" in source or "rsi > 75" in source:
            rules.append("SELL when RSI rises above 65 (overbought)")
        if "current_price > last_sh" in source:
            rules.append("BUY on break above last swing high (BOS)")
        if "current_price < last_sl" in source:
            rules.append("SELL on break below last swing low (BOS)")
        if "current_price > london_range_high" in source:
            rules.append("BUY on breakout above London range high")
        if "current_price < london_range_low" in source:
            rules.append("SELL on breakdown below London range low")
        if "current_price > or_high" in source:
            rules.append("BUY on breakout above opening range high")
        if "current_price < or_low" in source:
            rules.append("SELL on breakdown below opening range low")
        if (
            "fvg_bottom - 5 <= current_price <= fvg_top + 5" in source
            and "low[i] > high[i+2]" in source
        ):
            rules.append(
                "BUY when price enters bullish FVG zone (candle 1 high < candle 3 low)"
            )
        if (
            "fvg_bottom - 5 <= current_price <= fvg_top + 5" in source
            and "low[i+2] > high[i]" in source
        ):
            rules.append("SELL when price enters bearish FVG zone")
        if "sweep_high > high[i]" in source:
            rules.append(
                "SELL after liquidity sweep above equal highs then price closes back below"
            )
        if "min(sweep_low) < low[i]" in source:
            rules.append(
                "BUY after liquidity sweep below equal lows then price closes back above"
            )
        if "abs(current_price - fib_618)" in source:
            rules.append("Trade at Fibonacci 61.8% retracement level")
        if "abs(current_price - fib_500)" in source:
            rules.append("Trade at Fibonacci 50% retracement level")
        if "abs(current_price - fib_382)" in source:
            rules.append("Trade at Fibonacci 38.2% retracement level")
        if "recent_move > 0.4" in source:
            rules.append("Fade news spikes > 0.4% move (mean reversion)")
        if 'alignment["BUY"] == 3' in source:
            rules.append(
                "BUY when all 3 timeframes (M15, H1, H4) show bullish alignment"
            )
        if 'alignment["SELL"] == 3' in source:
            rules.append("SELL when all 3 timeframes show bearish alignment")
        if 'alignment["BUY"] == 2' in source:
            rules.append("BUY on 2/3 timeframe alignment (reduced confidence)")
        if "(current_price - avg_low) / zone_range < 0.12" in source:
            rules.append("BUY when price is near demand zone (bottom 12% of range)")
        if "(avg_high - current_price) / zone_range < 0.12" in source:
            rules.append("SELL when price is near supply zone (top 12% of range)")
        if "prev_distance > 0.05 and distance <= 0.05" in source:
            rules.append("SELL on VWAP rejection (price was above, returned to VWAP)")
        if "prev_distance < -0.05 and distance >= -0.05" in source:
            rules.append("BUY on VWAP rejection (price was below, returned to VWAP)")
        if "ob_top = h1_high[i]" in source and "h1_close[i] < h1_close[i-1]" in source:
            rules.append(
                "BUY when price near bullish order block (last bearish candle before rally)"
            )
        if (
            "ob_bottom = h1_low[i]" in source
            and "h1_close[i] > h1_close[i-1]" in source
        ):
            rules.append(
                "SELL when price near bearish order block (last bullish candle before drop)"
            )

    # Mandatory confirmations
    if (
        "score += 15" in source
        and "ema50" in source
        and "current_price > ema50" in source
    ):
        rules.append("+15 bonus if price above EMA 50 (trend alignment)")
    if "h4_ema50" in source and "h4_close[-1] > h4_ema50" in source:
        rules.append("+10 bonus if H4 EMA 50 trend confirms")
    if "volume[-1] > avg_vol * 1.3" in source or "volume[-1] > avg_vol * 1.4" in source:
        rules.append("Volume must exceed 1.3x average for confirmation")
    if "rsi > 70" in source and "score += 15" in source and "news" in name.lower():
        rules.append("Mandatory RSI confirmation (> 70 for short, < 30 for long)")

    return rules or ["Check strategy source for entry conditions"]


def _extract_exit_rules(source: str) -> list[str]:
    """Extract exit / TP logic."""
    rules = []

    if "atr or 5) * 3.0" in source:
        rules.append("TP at 3.0x ATR from entry")
    if "atr or 5) * 2.5" in source:
        rules.append("TP at 2.5x ATR from entry")
    if "atr or 5) * 2.0" in source:
        rules.append("TP at 2.0x ATR from entry")
    if "atr or 5) * 4.5" in source:
        rules.append("TP at 4.5x ATR from entry")
    if "sl_distance * 1.5" in source:
        rules.append("TP at 1.5x SL distance")
    if "(current_price - sl) * 2" in source and "ob_" in source:
        rules.append("TP at 2.0x risk from entry")
    if "(sl - current_price) * 2.5" in source:
        rules.append("TP at 2.5x risk (R:R)")
    if "(current_price - sl) * 2.5" in source:
        rules.append("TP at 2.5x risk (R:R)")
    if "range_size * 2.5" in source:
        rules.append("TP at 2.5x opening range size")
    if "range_size * 2.0" in source:
        rules.append("TP at 2.0x opening range size")
    if "tp = fib_500" in source:
        rules.append("TP targets next Fibonacci level (50%)")
    if "fvg_bottom - 10" in source:
        rules.append("SL placed 10pt below FVG bottom (buffer)")
    if "fvg_top + 10" in source:
        rules.append("SL placed 10pt above FVG top (buffer)")
    if "or_high - or_range * 0.3" in source:
        rules.append("SL at 30% of opening range below entry")
    if "or_low + or_range * 0.3" in source:
        rules.append("SL at 30% of opening range above entry")

    return rules or ["ATR-based stop loss and take profit"]


def _extract_risk_params(source: str) -> list[str]:
    """Extract SL/TP sizing rules."""
    params = []

    if "atr or 5) * 1.5" in source:
        params.append("SL = 1.5x ATR (tight)")
    if "atr or 5) * 3.0" in source and "sl" in source:
        params.append("SL = 3.0x ATR (wide, for multi-TF noise)")
    if "(current_price + last_sl) / 2" in source:
        params.append("SL at midpoint between entry and last swing low")
    if "(current_price + last_sh) / 2" in source:
        params.append("SL at midpoint between entry and last swing high")
    if "min_sl = max(atr_val * 1.5" in source:
        params.append("Minimum SL = max(1.5x ATR, symbol-specific minimum)")
    if "MIN_SL_DISTANCE" in source:
        params.append("XAUUSD min SL = $28 (prevents sizing explosion)")
    if "sl_buffer = atr_val * 0.5" in source:
        params.append("SL buffer = 0.5x ATR above/below sweep level")
    if "score < 50" in source:
        params.append("Minimum confidence threshold: 50/100")
    if "score = 85" in source:
        params.append("Max base score: 85 (3/3 TF alignment)")
    if "score = 80" in source:
        params.append("Max base score: 80 (liquidity sweep)")
    if "score = 75" in source:
        params.append("Max base score: 75 (FVG / order block)")

    return params or ["Default risk parameters"]


def _infer_best_conditions(
    name: str, indicators: list[str], timeframes: list[str]
) -> str:
    """Infer best market conditions from strategy type."""
    conditions = {
        "ema_cross": "Trending markets. Works best in strong directional moves. Struggles in ranging/choppy conditions.",
        "rsi_divergence": "Range-bound or exhaustion moves. Best at reversals. Fails in strong trends where RSI can stay extended.",
        "bos_choch": "Trending markets with clear structure. Best after consolidation breakouts. Weak in choppy price action.",
        "fair_value_gap": "Impulsive moves with unfilled gaps. Works in trending and mean-reversion. Struggles in low-volatility grind.",
        "fibonacci": "Swing trading in trending markets. Best at pullback levels. Fails in strong momentum without pullbacks.",
        "liquidity_sweep": "All conditions. Designed to catch institutional stop Hunts. Best around key support/resistance.",
        "london_breakout": "London session (08:00-12:00 UTC). Best on high-impact news days. Weak in quiet Asian session carryover.",
        "multi_tf_align": "Strong trending markets. Highest win rate when all 3 TFs agree. Rare signals — low frequency.",
        "news_fade": "High-volatility news events (NFP, FOMC, CPI). Fades overreactions. Dangerous in genuine regime shifts.",
        "opening_range": "First 4 hours of trading session. Best with volume confirmation. Avoids late-day false breakouts.",
        "order_block": "Institutional reversals on H1/H4. Best at key psychological levels. Requires H4 EMA confirmation.",
        "supply_demand": "Range and reversal trading. Best when zones align with higher TF structure. Needs volume confirmation.",
        "vwap_rejection": "Intraday mean reversion. Best in first half of session when VWAP is established. Weak in trend days.",
    }
    return conditions.get(name, "General gold trading conditions.")


def _infer_weaknesses(name: str) -> str:
    """Known weaknesses per strategy."""
    weaknesses = {
        "ema_cross": "Whipsaws in ranging markets. Late entries on slow crossovers. No volume filter.",
        "rsi_divergence": "Divergences can persist for extended periods. No trend filter — catches falling knives.",
        "bos_choch": "Requires sufficient swing structure (3-bar lookback). May miss fast breakouts.",
        "fair_value_gap": "FVGs can be filled partially. False gaps on low-timeframe noise. No trend confirmation.",
        "fibonacci": "Subjective swing high/low selection. Proximity threshold (0.3%) may miss moves.",
        "liquidity_sweep": "Equal highs/lows detection is approximate. Can false-trigger on thin liquidity.",
        "london_breakout": "Session-dependent — no signals outside London hours. Range calculation is approximate.",
        "multi_tf_align": "Very low signal frequency (3/3 alignment rare). 2/3 alignment has higher false-positive rate.",
        "news_fade": "Requires RSI confirmation — misses some valid fades. Dangerous in genuine regime changes.",
        "opening_range": "Time-filtered — stops trading after 12:00 UTC. Opening range is approximate (12 M5 bars).",
        "order_block": "Requires H1 + H4 data. OB detection is simplified (single candle pattern).",
        "supply_demand": "Zone detection is zone-cluster based, not precise. Min SL ($28) may be too wide for small accounts.",
        "vwap_rejection": "VWAP is simplified (no rolling reset). 0.05% proximity threshold is tight.",
    }
    return weaknesses.get(name, "No documented weaknesses yet.")


def _infer_related(name: str) -> list[str]:
    """Suggest related strategies."""
    relations = {
        "ema_cross": ["multi_tf_align", "fibonacci"],
        "rsi_divergence": ["news_fade", "vwap_rejection"],
        "bos_choch": ["order_block", "liquidity_sweep"],
        "fair_value_gap": ["order_block", "supply_demand"],
        "fibonacci": ["supply_demand", "ema_cross"],
        "liquidity_sweep": ["bos_choch", "order_block"],
        "london_breakout": ["opening_range", "news_fade"],
        "multi_tf_align": ["ema_cross", "order_block"],
        "news_fade": ["rsi_divergence", "london_breakout"],
        "opening_range": ["london_breakout", "supply_demand"],
        "order_block": ["bos_choch", "fair_value_gap"],
        "supply_demand": ["order_block", "fibonacci"],
        "vwap_rejection": ["rsi_divergence", "news_fade"],
    }
    return relations.get(name, [])


# ── main extraction ──────────────────────────────────────────────────────────


def extract_strategy(filepath: Path) -> StrategyInfo:
    """Parse a strategy .py file into a StrategyInfo."""
    source = filepath.read_text(encoding="utf-8")
    tree = ast.parse(source, filename=str(filepath))

    attrs = _extract_class_attrs(tree)
    docstring = _extract_docstrings(tree)

    # Find class name
    class_name = ""
    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef):
            class_name = node.name
            break

    name = attrs.get("name", filepath.stem)
    timeframes = _find_timeframes_used(source)
    indicators = _find_indicators(source)

    info = StrategyInfo(
        filename=filepath.name,
        class_name=class_name,
        name=name,
        description=attrs.get("description", ""),
        min_timeframe=attrs.get("min_timeframe", "M15"),
        entry_conditions=_extract_entry_rules(source, name),
        exit_conditions=_extract_exit_rules(source),
        risk_params=_extract_risk_params(source),
        timeframes_used=timeframes,
        symbols=["XAUUSD"],
        indicators=indicators,
        regime_filters=_infer_regime(name, source),
        best_conditions=_infer_best_conditions(name, indicators, timeframes),
        weaknesses=_infer_weaknesses(name),
        related=_infer_related(name),
        docstring=docstring.strip(),
        raw_source=source,
    )
    return info


def _infer_regime(name: str, source: str) -> list[str]:
    """Infer regime filters from code."""
    filters = []
    if "ema50" in source and "current_price > ema50" in source:
        filters.append("EMA 50 trend filter")
    if "h4_ema50" in source:
        filters.append("H4 trend confirmation")
    if "score += 10" in source and "volume" in source.lower():
        filters.append("Volume confirmation")
    if "rsi" in source and ("score += 15" in source or "score = 0" in source):
        filters.append("RSI mandatory confirmation")
    if "alignment" in source:
        filters.append("Multi-timeframe alignment gate")
    if "now.hour >= 12" in source:
        filters.append("Time-of-day filter (first 4h only)")
    if "recent_move > 0.4" in source:
        filters.append("Minimum volatility threshold (0.4% move)")
    return filters


# ── vault note generation ────────────────────────────────────────────────────


def generate_vault_note(info: StrategyInfo) -> str:
    """Render a strategy as an Obsidian vault note."""
    frontmatter_lines = [
        "---",
        "type: strategy",
        "category: gold_bot",
        f"symbols: [{', '.join(info.symbols)}]",
        f"timeframes: [{', '.join(info.timeframes_used)}]",
        f"indicators: [{', '.join(info.indicators)}]",
        f"source: {info.filename}",
        "updated: 2026-06-26",
        "---",
    ]

    sections = [
        "\n".join(frontmatter_lines),
        f"# {info.name.replace('_', ' ').title()}",
        f"> {info.description}",
        "",
        f"**Class:** `{info.class_name}`  ",
        f"**Min Timeframe:** {info.min_timeframe}  ",
        f"**Symbols:** {', '.join(info.symbols)}  ",
        f"**Source:** `gold_bot/strategies/{info.filename}`",
        "",
        "## Entry Conditions",
        *[f"- {rule}" for rule in info.entry_conditions],
        "",
        "## Exit Conditions",
        *[f"- {rule}" for rule in info.exit_conditions],
        "",
        "## Risk Parameters",
        *[f"- {param}" for param in info.risk_params],
        "",
        "## Regime Filters",
        *(
            [f"- {f}" for f in info.regime_filters]
            if info.regime_filters
            else ["- None (always active)"]
        ),
        "",
        "## Best Market Conditions",
        info.best_conditions,
        "",
        "## Known Weaknesses",
        info.weaknesses,
        "",
        "## Related Strategies",
        *[f"- [[{r}]]" for r in info.related],
        "",
    ]

    return "\n".join(sections)


def generate_index(infos: list[StrategyInfo]) -> str:
    """Create the strategy index note."""
    rows = []
    for info in sorted(infos, key=lambda x: x.name):
        rows.append(
            f"| [[{info.name}]] | {info.description} | {', '.join(info.timeframes_used)} | {', '.join(info.indicators)} |"
        )

    table = "\n".join(rows)

    return f"""---
type: moc
category: gold_bot
updated: 2026-06-26
---

# Gold Bot Strategy Index

> Auto-generated by `scripts/vault-pipeline/strategy_kb.py`

| Strategy | Description | Timeframes | Indicators |
|----------|-------------|------------|------------|
{table}

## Quick Reference

- **Trend-following:** [[ema_cross]], [[multi_tf_align]], [[bos_choch]]
- **Mean-reversion:** [[rsi_divergence]], [[vwap_rejection]], [[news_fade]]
- **ICT/Smart Money:** [[order_block]], [[fair_value_gap]], [[liquidity_sweep]], [[supply_demand]]
- **Session-based:** [[london_breakout]], [[opening_range]]
- **Confluence:** [[fibonacci]]

## Usage

These strategies feed into the Gold Bot engine (`gold_bot/core/engine.py`).
Each strategy returns a `StrategySignal` with confidence score ≥ 50.
The engine aggregates signals and applies risk management before execution.
"""


# ── main ─────────────────────────────────────────────────────────────────────


def main():
    filter_names = sys.argv[1:] if len(sys.argv) > 1 else None

    VAULT_DIR.mkdir(parents=True, exist_ok=True)

    files_to_process = STRATEGY_FILES
    if filter_names:
        files_to_process = [
            f for f in STRATEGY_FILES if any(fn in f for fn in filter_names)
        ]

    infos = []
    for fname in files_to_process:
        fpath = STRATEGY_DIR / fname
        if not fpath.exists():
            print(f"[SKIP] {fpath} not found")
            continue

        info = extract_strategy(fpath)
        note = generate_vault_note(info)

        out_path = VAULT_DIR / f"{info.name}.md"
        out_path.write_text(note, encoding="utf-8")
        print(f"[OK] {info.name} -> {out_path.name}")
        infos.append(info)

    # Index
    index = generate_index(infos)
    index_path = VAULT_DIR / "Index.md"
    index_path.write_text(index, encoding="utf-8")
    print(f"\n[Index] {len(infos)} strategies -> {index_path}")


if __name__ == "__main__":
    main()
