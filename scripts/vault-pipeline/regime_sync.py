"""
Pipeline 6: Regime Intelligence → Vault

Reads regime data from quant_os.regime and syncs to Obsidian vault.
Generates current regime note + historical daily log.
"""

import sys
from pathlib import Path
from datetime import datetime
from dataclasses import dataclass, field

# --- Path setup ---
QUANT_OS_ROOT = Path(r"C:\Users\menum\graxia os\graxia\packages\quant_os")
VAULT_ROOT = Path(r"C:\Users\menum\Documents\ObsidianVault\Second Brain")
REGIME_OUT = VAULT_ROOT / "03-resources" / "trading" / "regime"
INBOX_ALERTS = VAULT_ROOT / "00-Inbox" / "regime-alerts"
HISTORY_DIR = REGIME_OUT / "history"

# Add graxia/ parent so `graxia.packages.quant_os.regime` resolves
sys.path.insert(0, str(QUANT_OS_ROOT.parent.parent.parent))

# --- Strategy mapping ---
STRATEGY_REGIME_MAP = {
    "TREND_UP": {
        "enable": ["ema_crossover", "breakout", "momentum"],
        "disable": ["mean_reversion", "range_scalp"],
        "sizing": 1.0,
    },
    "TREND_DOWN": {
        "enable": ["short_momentum", "breakdown"],
        "disable": ["mean_reversion", "range_scalp"],
        "sizing": 0.8,
    },
    "RANGE": {
        "enable": ["mean_reversion", "range_scalp"],
        "disable": ["breakout", "momentum"],
        "sizing": 0.6,
    },
    "UNCLEAR": {
        "enable": [],
        "disable": ["all"],
        "sizing": 0.3,
    },
    "HIGH_VOL": {
        "enable": ["volatility_play"],
        "disable": ["mean_reversion", "range_scalp"],
        "sizing": 0.5,
    },
    "LOW_VOL": {
        "enable": ["carry", "range_scalp"],
        "disable": ["breakout", "momentum"],
        "sizing": 0.7,
    },
}


@dataclass
class VaultRegimeData:
    """Aggregated regime data for vault output."""

    regime: str
    confidence: float
    adx_value: float
    ema_slope: float
    atr_state: str
    spread_state: str
    reason_code: str
    timestamp: str = ""
    affected_strategies: dict = field(default_factory=dict)
    sizing_adjustment: float = 1.0
    historical_distribution: dict = field(default_factory=dict)
    transitions: list = field(default_factory=list)


def load_sample_regime() -> VaultRegimeData:
    """Generate sample regime data for testing."""
    return VaultRegimeData(
        regime="TREND_UP",
        confidence=0.78,
        adx_value=28.5,
        ema_slope=0.00023,
        atr_state="EXPANDING",
        spread_state="NORMAL",
        reason_code="ADX_HIGH(28) | SLOPE_UP | ATR_EXPAND",
        timestamp=datetime.now().strftime("%Y-%m-%d %H:%M"),
        affected_strategies=STRATEGY_REGIME_MAP["TREND_UP"],
        sizing_adjustment=STRATEGY_REGIME_MAP["TREND_UP"]["sizing"],
        historical_distribution={
            "TREND_UP": 12,
            "TREND_DOWN": 5,
            "RANGE": 10,
            "UNCLEAR": 3,
        },
        transitions=[
            {
                "date": "2026-06-24",
                "from": "RANGE",
                "to": "TREND_UP",
                "confidence": 0.72,
            },
            {
                "date": "2026-06-22",
                "from": "TREND_DOWN",
                "to": "RANGE",
                "confidence": 0.65,
            },
            {"date": "2026-06-20", "from": "RANGE", "to": "RANGE", "confidence": 0.81},
        ],
    )


def regime_to_display(regime: str) -> str:
    """Map internal regime to display name including vol states."""
    mapping = {
        "TREND_UP": "TREND UP",
        "TREND_DOWN": "TREND DOWN",
        "RANGE": "RANGE",
        "UNCLEAR": "UNCLEAR",
    }
    return mapping.get(regime, regime)


def regime_emoji(regime: str) -> str:
    return {
        "TREND_UP": "[UP]",
        "TREND_DOWN": "[DOWN]",
        "RANGE": "[SIDEWAYS]",
        "UNCLEAR": "[UNKNOWN]",
    }.get(regime, "?")


def sizing_label(sizing: float) -> str:
    if sizing >= 1.0:
        return "FULL"
    elif sizing >= 0.7:
        return "MODERATE"
    elif sizing >= 0.5:
        return "REDUCED"
    else:
        return "MINIMAL"


def format_distribution(dist: dict, total_days: int = 30) -> str:
    lines = []
    for regime, count in sorted(dist.items(), key=lambda x: -x[1]):
        pct = (count / total_days * 100) if total_days > 0 else 0
        bar = "#" * int(pct / 5)
        lines.append(f"| {regime} | {count}d | {pct:.0f}% | {bar} |")
    return "\n".join(lines)


def format_transitions(transitions: list) -> str:
    if not transitions:
        return "_No recent transitions recorded._"
    lines = []
    for t in transitions:
        lines.append(
            f"| {t['date']} | {t['from']} → {t['to']} | {t['confidence']:.0%} |"
        )
    return "\n".join(lines)


def generate_frontmatter(data: VaultRegimeData) -> str:
    strategies_csv = ",".join(data.affected_strategies.get("enable", []))
    return f"""---
type: regime
current_regime: {data.regime}
confidence: {data.confidence}
adx: {data.adx_value}
atr_state: {data.atr_state}
affected_strategies: [{strategies_csv}]
sizing: {data.sizing_adjustment}
synced: {data.timestamp}
---"""


def generate_current_note(data: VaultRegimeData) -> str:
    display = regime_to_display(data.regime)
    emoji = regime_emoji(data.regime)
    sizing = sizing_label(data.sizing_adjustment)

    enable_list = data.affected_strategies.get("enable", [])
    disable_list = data.affected_strategies.get("disable", [])

    enable_md = (
        "\n".join(f"- [x] {s}" for s in enable_list) if enable_list else "- _None_"
    )
    disable_md = (
        "\n".join(f"- [ ] {s}" for s in disable_list) if disable_list else "- _None_"
    )

    dist_total = sum(data.historical_distribution.values()) or 30

    return f"""{generate_frontmatter(data)}

# {emoji} Current Regime: {display}

> **Confidence:** {data.confidence:.0%} | **ADX:** {data.adx_value:.1f} | **ATR:** {data.atr_state}
> **Spread:** {data.spread_state} | **Reason:** `{data.reason_code}`
> **Last sync:** {data.timestamp}

---

## Strategy Recommendations

### Enabled Strategies
{enable_md}

### Disabled Strategies
{disable_md}

---

## Position Sizing

| Level | Adjustment |
|-------|-----------|
| Current | **{sizing}** ({data.sizing_adjustment:.0%} of base) |
| ATR State | {data.atr_state} |
| Spread | {data.spread_state} |

---

## Historical Regime Distribution (Last {dist_total} Days)

| Regime | Days | % | Distribution |
|--------|------|---|-------------|
{format_distribution(data.historical_distribution, dist_total)}

---

## Recent Regime Transitions

| Date | Transition | Confidence |
|------|-----------|------------|
{format_transitions(data.transitions)}

---

## Decision Checklist

- [ ] Confirm regime aligns with timeframe (M15)
- [ ] Check spread state before entry
- [ ] Verify enabled strategies match current regime
- [ ] Apply sizing adjustment to risk calculator
- [ ] Log regime in trade journal
"""


def generate_historical_note(data: VaultRegimeData) -> str:
    today = datetime.now().strftime("%Y-%m-%d")
    display = regime_to_display(data.regime)

    return f"""---
type: regime-daily
date: {today}
regime: {data.regime}
confidence: {data.confidence}
---

# Regime Log: {today}

- **Regime:** {display}
- **Confidence:** {data.confidence:.0%}
- **ADX:** {data.adx_value:.1f}
- **ATR State:** {data.atr_state}
- **Spread:** {data.spread_state}
- **Reason:** `{data.reason_code}`

## Notes

_Daily regime snapshot for historical analysis._
"""


def write_vault_files(data: VaultRegimeData) -> dict:
    """Write all vault files. Returns paths written."""
    REGIME_OUT.mkdir(parents=True, exist_ok=True)
    HISTORY_DIR.mkdir(parents=True, exist_ok=True)
    INBOX_ALERTS.mkdir(parents=True, exist_ok=True)

    today = datetime.now().strftime("%Y-%m-%d")
    paths = {}

    # Current regime note
    current_path = REGIME_OUT / "current.md"
    current_path.write_text(generate_current_note(data), encoding="utf-8")
    paths["current"] = str(current_path)

    # Historical daily log
    hist_path = HISTORY_DIR / f"{today}.md"
    hist_path.write_text(generate_historical_note(data), encoding="utf-8")
    paths["historical"] = str(hist_path)

    return paths


def create_alert_note(regime: str, confidence: float, reason: str) -> str:
    """Create real-time regime change alert in inbox."""
    INBOX_ALERTS.mkdir(parents=True, exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    display = regime_to_display(regime)

    alert_path = INBOX_ALERTS / f"{ts}.md"
    content = f"""---
type: regime-alert
regime: {regime}
confidence: {confidence}
timestamp: {datetime.now().isoformat()}
---

# Regime Change Alert

> **New Regime:** {display} ({confidence:.0%})
> **Time:** {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}
> **Reason:** `{reason}`

## Action Required

- [ ] Review affected strategies
- [ ] Adjust position sizing
- [ ] Check open positions against new regime
"""
    alert_path.write_text(content, encoding="utf-8")
    return str(alert_path)


def run_pipeline(sample: bool = False) -> dict:
    """Main pipeline entry point."""
    if sample:
        data = load_sample_regime()
    else:
        # Attempt live import
        try:
            from graxia.packages.quant_os.regime import RegimeDetector

            detector = RegimeDetector()
            # Generate synthetic M15 data for demo
            import random

            base = 2350.0
            closes = [base + random.uniform(-20, 40) for _ in range(200)]
            highs = [c + random.uniform(0, 8) for c in closes]
            lows = [c - random.uniform(0, 8) for c in closes]
            result = detector.detect(closes, highs, lows)

            atr_ext = (
                "HIGH_VOL"
                if result.atr_state == "EXPANDING"
                else ("LOW_VOL" if result.atr_state == "CONTRACTING" else result.regime)
            )
            strat_map = STRATEGY_REGIME_MAP.get(
                result.regime, STRATEGY_REGIME_MAP["UNCLEAR"]
            )

            data = VaultRegimeData(
                regime=result.regime,
                confidence=result.confidence,
                adx_value=result.adx_value,
                ema_slope=result.ema_slope,
                atr_state=result.atr_state,
                spread_state=result.spread_state,
                reason_code=result.reason_code,
                timestamp=datetime.now().strftime("%Y-%m-%d %H:%M"),
                affected_strategies=strat_map,
                sizing_adjustment=strat_map["sizing"],
                historical_distribution={
                    "RANGE": 15,
                    "TREND_UP": 8,
                    "TREND_DOWN": 5,
                    "UNCLEAR": 2,
                },
                transitions=[
                    {
                        "date": datetime.now().strftime("%Y-%m-%d"),
                        "from": "RANGE",
                        "to": result.regime,
                        "confidence": result.confidence,
                    },
                ],
            )
        except ImportError:
            print("WARNING: Could not import RegimeDetector, using sample data")
            data = load_sample_regime()

    paths = write_vault_files(data)
    print(f"[regime_sync] Current regime note: {paths['current']}")
    print(f"[regime_sync] Historical log: {paths['historical']}")
    return {"data": data, "paths": paths}


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Regime Intelligence → Vault pipeline")
    parser.add_argument("--sample", action="store_true", help="Use sample regime data")
    parser.add_argument("--alert", action="store_true", help="Create a test alert note")
    args = parser.parse_args()

    if args.alert:
        path = create_alert_note(
            "TREND_UP", 0.78, "ADX_HIGH(28) | SLOPE_UP | ATR_EXPAND"
        )
        print(f"[regime_alert] Alert created: {path}")
    else:
        run_pipeline(sample=args.sample)
