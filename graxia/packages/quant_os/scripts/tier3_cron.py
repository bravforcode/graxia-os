"""
Tier 3 Cron Job — Gemini Deep Strategist (every 4 hours).

Runs the CascadeRouter Tier 3 (Gemini) to produce a deep macro analysis
and writes the result to MacroRegimeCache.

Usage:
  python scripts/tier3_cron.py                    # one-shot
  python scripts/tier3_cron.py --force            # force run (ignore 4h timer)
  python scripts/tier3_cron.py --report PATH      # custom research report
"""

from __future__ import annotations

import asyncio
import os
import sys
import time
from datetime import UTC, datetime
from pathlib import Path

import structlog

sys.path.insert(0, str(Path(__file__).parent.parent))

from core.agents.llm_router import get_router
from core.canonical.macro_regime import MacroRegimeCache, RegimeBias

logger = structlog.get_logger(__name__)

# Load .env
ENV_PATH = Path(__file__).parent.parent / ".env"
if ENV_PATH.exists():
    for line in ENV_PATH.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, v = line.split("=", 1)
            os.environ.setdefault(k.strip(), v.strip())

# Default research report paths (ordered by priority)
DEFAULT_REPORTS = [
    Path(__file__).parent.parent / "research_xauusd_report.md",
    Path(__file__).parent.parent / "Meta" / "states" / "researcher_xauusd.md",
    Path(__file__).parent.parent / "Meta" / "states" / "researcher.md",
]


def find_report(custom_path: str | None = None) -> str:
    """Find the best available research report."""
    if custom_path:
        p = Path(custom_path)
        if p.exists():
            return str(p)
        logger.warning("tier3.report_not_found", path=custom_path)

    for report_path in DEFAULT_REPORTS:
        if report_path.exists():
            return str(report_path)

    return ""


async def run_tier3(force: bool = False, report_path: str | None = None) -> dict:
    """
    Run Tier 3 Gemini deep strategist.

    Returns the Tier 3 result dict or error dict.
    """
    router = get_router()

    if not force and not await router.should_run_tier3():
        logger.info("tier3.skip", reason="last_run_recent")
        return {"skipped": True, "reason": "last_run_recent"}

    report = find_report(report_path)
    logger.info("tier3.start", report_path=report or "none")

    start = time.monotonic()
    result = await router.run_tier3(report)
    latency = (time.monotonic() - start) * 1000

    if "error" in result:
        logger.warning("tier3.failed", error=result["error"], latency_ms=latency)
        return result

    # Parse and validate result
    bias_str = result.get("bias", "NEUTRAL").upper()
    bias_map = {
        "BULLISH": RegimeBias.BULLISH,
        "BEARISH": RegimeBias.BEARISH,
        "NEUTRAL": RegimeBias.NEUTRAL,
        "PANIC": RegimeBias.PANIC,
    }
    bias = bias_map.get(bias_str, RegimeBias.NEUTRAL)
    confidence = float(result.get("confidence", 0.5))
    pos_mult = float(result.get("position_multiplier", 1.0))
    regime_label = result.get("regime_label", "NORMAL")
    reasoning = result.get("reasoning", "")

    # Write to MacroRegimeCache
    cache = MacroRegimeCache()
    cache.update_from_sentiment(
        bias=bias,
        confidence=confidence,
        position_multiplier=pos_mult,
        regime_label=regime_label,
        source="gemini_tier3",
        headline=f"Deep macro analysis {datetime.now(UTC).strftime('%Y-%m-%d %H:%M')}",
    )

    logger.info(
        "tier3.complete",
        bias=bias.value,
        confidence=confidence,
        pos_mult=pos_mult,
        regime=regime_label,
        latency_ms=round(latency, 1),
        provider=result.get("provider", "unknown"),
    )

    return {
        "success": True,
        "bias": bias.value,
        "confidence": confidence,
        "position_multiplier": pos_mult,
        "regime_label": regime_label,
        "reasoning": reasoning,
        "latency_ms": round(latency, 1),
        "provider": result.get("provider", "unknown"),
    }


async def main():
    import argparse

    parser = argparse.ArgumentParser(description="Tier 3 Cron — Gemini Deep Strategist")
    parser.add_argument("--force", action="store_true", help="Force run (ignore 4h timer)")
    parser.add_argument("--report", type=str, help="Custom research report path")
    args = parser.parse_args()

    result = await run_tier3(force=args.force, report_path=args.report)

    if result.get("success"):
        print(f"\n{'='*60}")
        print("  Tier 3 Deep Strategist — Complete")
        print(f"  Bias: {result['bias']}")
        print(f"  Confidence: {result['confidence']:.2f}")
        print(f"  Position Mult: {result['position_multiplier']:.2f}")
        print(f"  Regime: {result['regime_label']}")
        print(f"  Provider: {result['provider']}")
        print(f"  Latency: {result['latency_ms']:.0f}ms")
        print(f"{'='*60}\n")
    elif result.get("skipped"):
        print(f"Tier 3 skipped: {result['reason']}")
    else:
        print(f"Tier 3 failed: {result.get('error', 'unknown')}")


if __name__ == "__main__":
    asyncio.run(main())
