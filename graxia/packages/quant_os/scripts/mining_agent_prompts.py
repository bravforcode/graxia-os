"""Direction I P1 — subagent mining prompts (spec §P1).

Each source agent (S1-S6) receives a strict prompt with:
  - the source to mine and the target volume
  - the exact JSON contract the runner validates against
  - the no-fabrication / blocked-source rules

The returned payload is fed to research.mining_runner.ingest_mining_output(),
which rejects any entry violating the contract. Agents never write to the
catalog directly — the runner is the only writer.
"""

from __future__ import annotations

# Source table from spec §P1 — authoritative targets.
SOURCES: dict[str, dict] = {
    "S1": {"name": "MQL5 Code Base", "target": "500+ EAs", "split": "categories split x2"},
    "S2": {
        "name": "GitHub",
        "target": "300+ repos",
        "split": "EarnForex, freqtrade, forex-stuff, backtrader collections x2",
    },
    "S3": {"name": "MyFxBook verified", "target": "100+ verified systems", "split": "FX x2: FX + crypto/metals"},
    "S4": {
        "name": "Forex Factory + TradingView Pine",
        "target": "200+ community strategies",
        "split": "community strategies",
    },
    "S5": {
        "name": "Academic",
        "target": "100+ mechanisms",
        "split": "SSRN/JF/NBER/AQR/Man/Alpha Architect/Quantpedia x2: quant-finance + crypto",
    },
    "S6": {
        "name": "Institutional/obscure",
        "target": "150+ entries",
        "split": "QuantConnect Alphas, cTrader cBots, StrategyQuant, Numerai, RU/TH/CN forums x2",
    },
}

OUTPUT_CONTRACT = """\
You MUST return ONLY a JSON object with this exact shape (no prose, no markdown fences):

{"entries": [ { "name": str, "source_url": str, "mechanism": str, "params": {str: str|number}, "claimed_perf": str, "evidence_tier": "LITERATURE"|"MYFXBOOK_VERIFIED"|"PRACTITIONER_LORE", "symbol": str, "timeframe": str } ]}

CONTRACT RULES (violations cause rejection by the runner):
1. source_url is MANDATORY for every entry — real http(s) URL you actually fetched or saw cited. An entry without a URL is REJECTED. NO FABRICATION.
2. mechanism must be a real mechanism name (e.g. "grid_martingale", "rsi_mean_reversion", "breakout_momentum", "tsmom", "donchian_channel", "news_trading", "orderflow_imbalance"). Placeholders like "unknown" are REJECTED.
3. claimed_perf must quote what the source ACTUALLY claims (e.g. "+77.85% over 19 months, 19.99% DD, verified"). "tbd"/"todo"/"placeholder" are REJECTED. If the source states no performance, write "not stated".
4. evidence_tier: LITERATURE = peer-reviewed/SSRN/NBER/AQR paper; MYFXBOOK_VERIFIED = live verified MyFxBook system; PRACTITIONER_LORE = forum/community/vendor claims.
5. params: concrete parameters the source gives (lots, TP/SL, grid spacing, pairs, timeframes, etc). Empty dict is allowed only if the source gives no parameters.
6. symbol/timeframe: the instrument(s) and timeframe the strategy targets. Empty string allowed if the source doesn't say.

BLOCKED SOURCE RULE: if the source is unreachable (Cloudflare, bot-block, geo-block), return {"entries": [], "blocked": {"source": "Sx", "reason": "..."}} and record the workaround you tried. NEVER guess or invent entries to hit the target."""


def build_prompt(source_id: str, extra_instructions: str = "") -> str:
    """Assemble the mining prompt for one source agent."""
    src = SOURCES[source_id]
    lines = [
        f"You are mining source {source_id}: {src['name']} (target {src['target']}, scope: {src['split']}).",
        "This is part of Direction I (EA Deep-Mine Funnel) P1 Massive Mining — a structured catalog.",
        "",
        "WORK:",
        f"1. Use web fetch / browser tools to gather real entries from {src['name']}.",
        "2. Extract up to the target volume of DISTINCT mechanisms/strategies/systems.",
        "3. For each, capture the metadata the contract requires.",
        "",
        OUTPUT_CONTRACT,
        "",
    ]
    if extra_instructions:
        lines.append(extra_instructions)
        lines.append("")
    lines.append(
        "Remember: NO FABRICATION. Every entry needs a real source_url. Unreachable sources are recorded as blocked, never guessed."
    )
    return "\n".join(lines)


def build_all_prompts(extra_per_source: dict[str, str] | None = None) -> dict[str, str]:
    """Return {source_id: prompt} for all six source agents."""
    extra_per_source = extra_per_source or {}
    return {sid: build_prompt(sid, extra_per_source.get(sid, "")) for sid in SOURCES}
