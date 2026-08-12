#!/usr/bin/env python3
"""Pipeline 4: Macro Dashboard → Vault daily sync (enhanced).

Pulls real macro data from FRED CSVs, parquet files, COT positioning,
economic calendars, and XAUUSD regime detection. Generates multiple
Obsidian vault notes covering different macro themes.
"""

import json
from datetime import datetime
from pathlib import Path

import numpy as np
import pandas as pd

# ── Paths ────────────────────────────────────────────────────────────
ROOT = Path(r"C:\Users\menum\graxia os\graxia\packages\quant_os")
MACRO_DIR = ROOT / "data" / "macro"
COT_DIR = ROOT / "data" / "cot"
NEWS_DIR = ROOT / "data" / "news"
FRED_DIR = ROOT / "data" / "fred" / "daily"
DATA_DIR = ROOT / "data"
VAULT_OUT = Path(
    r"C:\Users\menum\Documents\ObsidianVault\Second Brain\03-resources\trading\macro"
)

# ── Helpers ──────────────────────────────────────────────────────────


def load_parquet(path: Path) -> pd.DataFrame:
    """Load parquet, parse date column."""
    df = pd.read_parquet(path)
    if "date" in df.columns:
        df["date"] = pd.to_datetime(df["date"])
        df = df.sort_values("date").reset_index(drop=True)
    return df


def load_fred_csv(series_id: str) -> pd.DataFrame:
    """Load a FRED daily CSV. Returns DataFrame with date + value columns."""
    path = FRED_DIR / f"{series_id}.csv"
    if not path.exists():
        return pd.DataFrame()
    df = pd.read_csv(path, index_col=0, parse_dates=True)
    df.columns = [series_id]
    df = df.dropna()
    df.index.name = "date"
    df = df.reset_index()
    return df


def percentile_rank(series: pd.Series, value: float) -> float:
    """Percentile of value within series (0-100)."""
    if len(series) == 0:
        return 50.0
    return float((series < value).sum() / len(series) * 100)


def trend_label(current: float, ma20: float, ma50: float) -> str:
    if current > ma20 > ma50:
        return "Strong Up"
    elif current > ma20:
        return "Up"
    elif current < ma20 < ma50:
        return "Strong Down"
    elif current < ma20:
        return "Down"
    return "Flat"


def dxy_trend_label(current: float, ma20: float, ma50: float) -> str:
    if current > ma20 > ma50:
        return "Dollar Strength ^"
    elif current > ma20:
        return "Dollar Firming"
    elif current < ma20 < ma50:
        return "Dollar Weakness v"
    elif current < ma50:
        return "Dollar Softening"
    return "Dollar Flat"


def safe_float(series: pd.Series, default: float = 0.0) -> float:
    """Safely get last float value from a series."""
    if series.empty:
        return default
    val = series.iloc[-1]
    if pd.isna(val):
        return default
    return float(val)


# ── Data Loaders ─────────────────────────────────────────────────────


def load_vix() -> dict:
    df = load_parquet(MACRO_DIR / "yf_VIXCLS.parquet")
    current = float(df["value"].iloc[-1])
    pct = percentile_rank(df["value"], current)
    ma20 = float(df["value"].rolling(20).mean().iloc[-1])
    ma50 = float(df["value"].rolling(50).mean().iloc[-1])
    return {
        "current": round(current, 2),
        "pct_52w": round(pct, 1),
        "ma20": round(ma20, 2),
        "ma50": round(ma50, 2),
        "min_52w": round(float(df["value"].min()), 2),
        "max_52w": round(float(df["value"].max()), 2),
        "trend": trend_label(current, ma20, ma50),
    }


def load_gvz() -> dict:
    df = load_parquet(MACRO_DIR / "yf_GVZCLS.parquet")
    current = float(df["value"].iloc[-1])
    pct = percentile_rank(df["value"], current)
    ma20 = float(df["value"].rolling(20).mean().iloc[-1])
    return {
        "current": round(current, 2),
        "pct_52w": round(pct, 1),
        "ma20": round(ma20, 2),
        "min_52w": round(float(df["value"].min()), 2),
        "max_52w": round(float(df["value"].max()), 2),
    }


def load_dxy() -> dict:
    df = load_parquet(MACRO_DIR / "yf_DTWEXBGS.parquet")
    current = float(df["value"].iloc[-1])
    pct = percentile_rank(df["value"], current)
    ma20 = float(df["value"].rolling(20).mean().iloc[-1])
    ma50 = float(df["value"].rolling(50).mean().iloc[-1])
    return {
        "current": round(current, 3),
        "pct_52w": round(pct, 1),
        "ma20": round(ma20, 3),
        "ma50": round(ma50, 3),
        "min_52w": round(float(df["value"].min()), 3),
        "max_52w": round(float(df["value"].max()), 3),
        "trend": dxy_trend_label(current, ma20, ma50),
    }


def load_dfii10() -> dict:
    dated_files = sorted(MACRO_DIR.glob("DFII10_*.parquet"))
    if dated_files:
        df = load_parquet(dated_files[-1])
    else:
        df = load_parquet(MACRO_DIR / "yf_DFII10.parquet")
    current = float(df["value"].iloc[-1])
    pct = percentile_rank(df["value"], current)
    return {
        "current": round(current, 2),
        "pct_window": round(pct, 1),
        "min_window": round(float(df["value"].min()), 2),
        "max_window": round(float(df["value"].max()), 2),
    }


def load_cot() -> dict:
    cot_files = sorted(COT_DIR.glob("cot_xauusd_*.parquet"))
    if not cot_files:
        return {}
    df = load_parquet(cot_files[-1])
    latest = df.iloc[-1]
    return {
        "date": str(latest.get("date", ""))[:10],
        "open_interest": int(latest.get("open_interest", 0)),
        "mm_long": int(latest.get("mm_long", 0)),
        "mm_short": int(latest.get("mm_short", 0)),
        "mm_net_long": int(latest.get("mm_net_long", 0)),
        "mm_net_long_pct": round(float(latest.get("mm_net_long_pct", 0)) * 100, 1),
        "cot_index_52w": round(float(latest.get("cot_index_52w", 0)) * 100, 1),
        "mm_trend_3w": int(latest.get("mm_trend_3w", 0)),
        "producer_net_short_pct": round(
            float(latest.get("producer_net_short_pct", 0)) * 100, 1
        ),
    }


def load_calendar() -> list[dict]:
    cal_path = NEWS_DIR / "investing_calendar.json"
    if not cal_path.exists():
        return []
    with open(cal_path, "r", encoding="utf-8") as f:
        data = json.load(f)
    major_fx = {
        "USD",
        "EUR",
        "GBP",
        "JPY",
        "CHF",
        "AUD",
        "NZD",
        "CAD",
        "US",
        "EU",
        "UK",
        "JP",
        "CH",
        "AU",
        "NZ",
        "CA",
        "DE",
        "FR",
        "IT",
        "SG",
        "IN",
        "BR",
    }
    events = []
    for e in data:
        cur = e.get("currency", "")
        if cur in major_fx and e.get("event"):
            importance = e.get("importance", "")
            high_keywords = [
                "rate",
                "nfp",
                "cpi",
                "gdp",
                "fomc",
                "ecb",
                "boj",
                "interest",
                "inflation",
                "retail sales",
                "pmi",
                "employment",
                "unemployment",
                "trade balance",
                "consumer sentiment",
                "michigan",
            ]
            ev_lower = e.get("event", "").lower()
            if not importance and any(kw in ev_lower for kw in high_keywords):
                importance = "High"
            events.append(
                {
                    "currency": cur,
                    "event": e.get("event", ""),
                    "importance": importance or "Low",
                    "actual": e.get("actual", ""),
                    "forecast": e.get("forecast", ""),
                    "previous": e.get("previous", ""),
                }
            )
    return events


# ── FRED Data Loaders (new) ─────────────────────────────────────────


def load_fred_series(series_id: str) -> dict:
    """Load a FRED series and return current value + stats."""
    df = load_fred_csv(series_id)
    if df.empty:
        return {"available": False}
    vals = df[series_id]
    current = safe_float(vals)
    pct = percentile_rank(vals, current)
    return {
        "available": True,
        "current": round(current, 4),
        "pct_5y": round(pct, 1),
        "min_5y": round(float(vals.min()), 4),
        "max_5y": round(float(vals.max()), 4),
        "mean_5y": round(float(vals.mean()), 4),
        "last_date": str(df["date"].iloc[-1])[:10],
    }


def load_yield_curve() -> dict:
    """Load yield curve data: DFF, DGS2, DGS10, T10Y2Y, T5YIE, T5YIFR."""
    series = {
        "DFF": "Fed Funds Rate",
        "DGS2": "2Y Treasury",
        "DGS10": "10Y Treasury",
        "T10Y2Y": "10Y-2Y Spread",
        "T5YIE": "5Y Breakeven Inflation",
        "T5YIFR": "5Y5Y Forward Inflation",
    }
    result = {}
    for sid, desc in series.items():
        data = load_fred_series(sid)
        data["description"] = desc
        result[sid] = data
    return result


def load_credit_stress() -> dict:
    """Load credit stress indicators: BAA10Y, HY OAS, TED spread."""
    series = {
        "BAA10Y": "BAA-10Y Credit Spread",
        "BAMLH0A0HYM2": "HY OAS",
        "T10Y2Y": "10Y-2Y (Recession Proxy)",
    }
    result = {}
    for sid, desc in series.items():
        data = load_fred_series(sid)
        data["description"] = desc
        result[sid] = data
    return result


def load_inflation_data() -> dict:
    """Load inflation indicators: T10YIE, T5YIE, CPIAUCSL, CPILFESL."""
    series = {
        "T10YIE": "10Y Breakeven Inflation",
        "T5YIE": "5Y Breakeven Inflation",
        "T5YIFR": "5Y5Y Forward Inflation",
    }
    result = {}
    for sid, desc in series.items():
        data = load_fred_series(sid)
        data["description"] = desc
        result[sid] = data
    return result


def load_liquidity_data() -> dict:
    """Load liquidity indicators: WALCL, RRPONTSYD, WTREGEN."""
    series = {
        "WALCL": "Fed Balance Sheet",
        "RRPONTSYD": "ON RRP Facility",
        "WTREGEN": "Treasury General Account",
    }
    result = {}
    for sid, desc in series.items():
        data = load_fred_series(sid)
        data["description"] = desc
        result[sid] = data
    return result


def load_cross_market() -> dict:
    """Load cross-market data: SP500, Brent, WTI, DXY, DEXJPUS, DEXUSEU."""
    series = {
        "SP500": "S&P 500",
        "DCOILBRENTEU": "Brent Crude",
        "DCOILWTICO": "WTI Crude",
        "DEXJPUS": "USD/JPY",
        "DEXUSEU": "EUR/USD",
    }
    result = {}
    for sid, desc in series.items():
        data = load_fred_series(sid)
        data["description"] = desc
        result[sid] = data
    return result


def load_xauusd_regime() -> dict:
    """Compute XAUUSD regime from D1 OHLCV data."""
    csv_path = DATA_DIR / "XAUUSD_D1.csv"
    if not csv_path.exists():
        return {"available": False}
    df = pd.read_csv(csv_path)
    if len(df) < 50:
        return {"available": False}

    closes = df["close"].tolist()
    highs = df["high"].tolist()
    lows = df["low"].tolist()

    # Import regime detector
    try:
        from graxia.packages.quant_os.regime import RegimeDetector

        detector = RegimeDetector()
        result = detector.detect(closes[-200:], highs[-200:], lows[-200:])
        current_price = closes[-1]
        ma20 = np.mean(closes[-20:])
        ma50 = np.mean(closes[-50:])
        ma200 = np.mean(closes[-200:]) if len(closes) >= 200 else ma50
        return {
            "available": True,
            "regime": result.regime,
            "confidence": result.confidence,
            "adx": round(result.adx_value, 1),
            "atr_state": result.atr_state,
            "spread_state": result.spread_state,
            "reason_code": result.reason_code,
            "current_price": round(current_price, 2),
            "ma20": round(ma20, 2),
            "ma50": round(ma50, 2),
            "ma200": round(ma200, 2),
            "price_vs_ma20": round((current_price / ma20 - 1) * 100, 2),
            "price_vs_ma50": round((current_price / ma50 - 1) * 100, 2),
        }
    except Exception as e:
        return {"available": False, "error": str(e)}


# ── Correlation Insights ─────────────────────────────────────────────


def correlation_insights(
    vix: dict, gvz: dict, dxy: dict, dfii: dict, cot: dict
) -> list[str]:
    insights = []
    vix_pct = vix.get("pct_52w", 50)
    gvz_pct = gvz.get("pct_52w", 50)
    if vix_pct > 70 and gvz_pct < 40:
        insights.append("VIX elevated but GVZ subdued — gold vol underpricing risk")
    elif vix_pct < 30 and gvz_pct > 60:
        insights.append("GVZ elevated but VIX low — gold-specific fear event brewing")
    elif gvz_pct > 80 and vix_pct < 70:
        insights.append(
            "GVZ spiking (p95) while VIX moderate — gold vol underpricing, hedging opportunity"
        )
    elif vix_pct > 70 and gvz_pct > 70:
        insights.append("Both VIX and GVZ elevated — broad risk-off environment")
    elif vix_pct < 30 and gvz_pct < 30:
        insights.append("Both VIX and GVZ low — complacency, watch for vol expansion")

    dxy_pct = dxy.get("pct_52w", 50)
    if dxy_pct > 70 and gvz_pct > 60:
        insights.append(
            "Strong dollar + gold vol up — possible safe-haven bid despite USD strength"
        )
    elif dxy_pct < 30 and cot.get("mm_net_long_pct", 50) > 60:
        insights.append("Weak dollar + large spec longs — crowded gold long setup")

    if dfii.get("current", 0) > 2.2:
        insights.append(
            "Real yields elevated (>{:.1f}%) — headwind for gold".format(
                dfii["current"]
            )
        )
    elif dfii.get("current", 0) < 1.5:
        insights.append("Real yields low (<1.5%) — tailwind for gold")

    if cot.get("mm_net_long_pct", 0) > 35:
        insights.append("COT: Managed money heavily net long — crowding risk")
    elif cot.get("mm_net_long_pct", 0) < 10:
        insights.append("COT: Managed money near flat — potential for short squeeze")

    if not insights:
        insights.append("No extreme correlations detected — neutral macro backdrop")

    return insights


def credit_insights(credit: dict) -> list[str]:
    """Generate credit-specific insights."""
    insights = []
    hy = credit.get("BAMLH0A0HYM2", {})
    baaspread = credit.get("BAA10Y", {})

    if hy.get("available"):
        hy_current = hy["current"]
        hy_mean = hy.get("mean_5y", 3.2)
        if hy_current > hy_mean + 0.5:
            insights.append(
                f"HY OAS elevated ({hy_current:.2f}%) vs mean ({hy_mean:.2f}%) — credit stress rising"
            )
        elif hy_current < hy_mean - 0.5:
            insights.append(
                f"HY OAS tight ({hy_current:.2f}%) — risk-on credit environment"
            )
        if hy["pct_5y"] > 80:
            insights.append(
                "HY OAS in top 20% of 5-year range — credit deterioration signal"
            )

    if baaspread.get("available"):
        ba_current = baaspread["current"]
        if ba_current > 2.0:
            insights.append(
                f"BAA-10Y spread ({ba_current:.2f}%) elevated — corporate credit stress"
            )
        elif ba_current < 1.5:
            insights.append(
                f"BAA-10Y spread ({ba_current:.2f}%) tight — accommodative credit"
            )

    if not insights:
        insights.append("Credit conditions neutral")
    return insights


def liquidity_insights(liq: dict) -> list[str]:
    """Generate liquidity-specific insights."""
    insights = []
    walcl = liq.get("WALCL", {})
    rrp = liq.get("RRPONTSYD", {})
    tga = liq.get("WTREGEN", {})

    if walcl.get("available"):
        if walcl["pct_5y"] < 20:
            insights.append(
                "Fed balance sheet at 5-year lows — QT tightening liquidity"
            )
        elif walcl["pct_5y"] > 80:
            insights.append("Fed balance sheet elevated — ample system liquidity")

    if rrp.get("available"):
        rrp_val = rrp["current"]
        if rrp_val > 1500:
            insights.append(
                f"ON RRP elevated (${rrp_val:.0f}B) — excess cash parked at Fed"
            )
        elif rrp_val < 100:
            insights.append(
                f"ON RRP drained (${rrp_val:.0f}B) — liquidity moving to markets"
            )

    if tga.get("available"):
        tga_val = tga["current"]
        if tga_val > 800:
            insights.append(f"TGA high (${tga_val:.0f}B) — Treasury draining liquidity")
        elif tga_val < 200:
            insights.append(f"TGA low (${tga_val:.0f}B) — Treasury injecting liquidity")

    if not insights:
        insights.append("Liquidity conditions neutral")
    return insights


def inflation_insights(infl: dict) -> list[str]:
    """Generate inflation-specific insights."""
    insights = []
    t10yie = infl.get("T10YIE", {})
    t5yif = infl.get("T5YIFR", {})

    if t10yie.get("available"):
        be = t10yie["current"]
        if be > 2.5:
            insights.append(
                f"10Y breakeven ({be:.2f}%) above 2.5% — inflation expectations elevated"
            )
        elif be < 2.1:
            insights.append(f"10Y breakeven ({be:.2f}%) below 2.1% — deflationary risk")
        if t10yie["pct_5y"] > 80:
            insights.append(
                "Breakeven inflation in top 20% of 5Y range — inflation regime shift"
            )

    if t5yif.get("available"):
        fwd = t5yif["current"]
        if fwd > 2.5:
            insights.append(
                f"5Y5Y forward ({fwd:.2f}%) above 2.5% — long-term inflation unanchored"
            )
        elif fwd < 2.0:
            insights.append(
                f"5Y5Y forward ({fwd:.2f}%) below 2.0% — market pricing deflation"
            )

    if not insights:
        insights.append("Inflation expectations anchored")
    return insights


# ── Markdown Generation: Main Dashboard ──────────────────────────────


def generate_main_dashboard(
    today: str,
    vix: dict,
    gvz: dict,
    dxy: dict,
    dfii: dict,
    cot: dict,
    calendar: list[dict],
    insights: list[str],
    regime: dict,
) -> str:
    lines = [
        "---",
        "type: macro-dashboard",
        f"date: {today}",
        f"vix_level: {vix['current']}",
        f"dxy_trend: \"{dxy['trend']}\"",
        "---",
        "",
        f"# Macro Dashboard — {today}",
        "",
        "---",
        "",
        "## VIX (S&P 500 Volatility)",
        "",
        "| Metric | Value |",
        "|--------|-------|",
        f"| Current | **{vix['current']}** |",
        f"| 52w Percentile | {vix['pct_52w']}th |",
        f"| MA(20) | {vix['ma20']} |",
        f"| MA(50) | {vix['ma50']} |",
        f"| 52w Range | {vix['min_52w']} – {vix['max_52w']} |",
        f"| Trend | {vix['trend']} |",
        "",
    ]

    if vix["current"] > 30:
        lines.append(
            "> **Elevated fear** — risk-off environment, position sizing caution advised"
        )
    elif vix["current"] > 20:
        lines.append("> **Above average** — moderate uncertainty, watch for expansion")
    elif vix["current"] > 15:
        lines.append("> **Normal range** — baseline volatility")
    else:
        lines.append("> **Low vol** — complacency, potential for sharp moves")
    lines.append("")

    lines += [
        "## GVZ (Gold Volatility Index)",
        "",
        "| Metric | Value |",
        "|--------|-------|",
        f"| Current | **{gvz['current']}** |",
        f"| 52w Percentile | {gvz['pct_52w']}th |",
        f"| MA(20) | {gvz['ma20']} |",
        f"| 52w Range | {gvz['min_52w']} – {gvz['max_52w']} |",
        "",
    ]

    lines += [
        "## DXY (US Dollar Index)",
        "",
        "| Metric | Value |",
        "|--------|-------|",
        f"| Current | **{dxy['current']}** |",
        f"| 52w Percentile | {dxy['pct_52w']}th |",
        f"| MA(20) | {dxy['ma20']} |",
        f"| MA(50) | {dxy['ma50']} |",
        f"| 52w Range | {dxy['min_52w']} – {dxy['max_52w']} |",
        f"| Trend | **{dxy['trend']}** |",
        "",
    ]

    lines += [
        "## DFII10 (10Y Real Yield)",
        "",
        "| Metric | Value |",
        "|--------|-------|",
        f"| Current | **{dfii['current']}%** |",
        f"| Window Percentile | {dfii['pct_window']}th |",
        f"| Window Range | {dfii['min_window']}% – {dfii['max_window']}% |",
        "",
    ]

    if cot:
        trend_arrow = "^" if cot["mm_trend_3w"] > 0 else "v"
        lines += [
            "## COT Positioning (Gold Futures)",
            "",
            f"*Data as of: {cot['date']}*",
            "",
            "| Metric | Value |",
            "|--------|-------|",
            f"| Open Interest | {cot['open_interest']:,} |",
            f"| Managed Money Long | {cot['mm_long']:,} |",
            f"| Managed Money Short | {cot['mm_short']:,} |",
            f"| MM Net Long | **{cot['mm_net_long']:,}** ({cot['mm_net_long_pct']}%) |",
            f"| 52w COT Index | {cot['cot_index_52w']}th |",
            f"| 3w Trend | {cot['mm_trend_3w']:+,} {trend_arrow} |",
            f"| Producer Net Short % | {cot['producer_net_short_pct']}% |",
            "",
        ]

    # XAUUSD Regime
    if regime.get("available"):
        lines += [
            "## XAUUSD Regime",
            "",
            "| Metric | Value |",
            "|--------|-------|",
            f"| Regime | **{regime['regime']}** |",
            f"| Confidence | {regime['confidence']:.1%} |",
            f"| ADX | {regime['adx']} |",
            f"| ATR State | {regime['atr_state']} |",
            f"| Price | {regime['current_price']} |",
            f"| vs MA20 | {regime['price_vs_ma20']:+.2f}% |",
            f"| vs MA50 | {regime['price_vs_ma50']:+.2f}% |",
            "",
        ]

    lines += [
        "## Economic Events",
        "",
    ]
    if calendar:
        key_events = [
            e
            for e in calendar
            if e["importance"] == "High" or e["currency"] in ("USD", "US")
        ]
        if key_events:
            lines.append("| Currency | Event | Importance | Forecast | Previous |")
            lines.append("|----------|-------|------------|----------|----------|")
            for e in key_events[:15]:
                lines.append(
                    f"| {e['currency']} | {e['event'][:50]} | {e['importance']} | "
                    f"{e['forecast'] or '—'} | {e['previous'] or '—'} |"
                )
        else:
            lines.append("No high-impact events in current calendar window.")
    else:
        lines.append("Calendar data unavailable.")
    lines.append("")

    lines += [
        "## Correlation Insights",
        "",
    ]
    for ins in insights:
        lines.append(f"- {ins}")
    lines.append("")

    lines += [
        "---",
        f"*Generated: {datetime.now().strftime('%Y-%m-%d %H:%M')} by vault-pipeline/macro_to_vault.py*",
    ]

    return "\n".join(lines)


# ── Markdown Generation: Yield Curve ─────────────────────────────────


def generate_yields_note(today: str, yields: dict, dfii: dict) -> str:
    lines = [
        "---",
        "type: macro-yields",
        f"date: {today}",
        "---",
        "",
        f"# Yield Curve & Rates — {today}",
        "",
        "---",
        "",
    ]

    # Summary table
    lines += [
        "## Current Rates",
        "",
        "| Series | Current | 5Y Percentile | 5Y Range |",
        "|--------|---------|---------------|----------|",
    ]
    for sid in ["DFF", "DGS2", "DGS10", "T10Y2Y", "T5YIE", "T5YIFR"]:
        data = yields.get(sid, {})
        if data.get("available"):
            lines.append(
                f"| {data['description']} | **{data['current']:.2f}%** | "
                f"{data['pct_5y']}th | {data['min_5y']:.2f} – {data['max_5y']:.2f} |"
            )
    lines.append("")

    # Yield curve shape
    dgs2 = yields.get("DGS2", {}).get("current", 0)
    dgs10 = yields.get("DGS10", {}).get("current", 0)
    dff = yields.get("DFF", {}).get("current", 0)
    t10y2y = yields.get("T10Y2Y", {}).get("current", 0)

    lines += [
        "## Curve Analysis",
        "",
    ]

    if t10y2y != 0:
        if t10y2y < 0:
            lines.append(
                f"- **Inverted curve** (10Y-2Y = {t10y2y:.2f}%) — recession signal"
            )
        elif t10y2y < 0.25:
            lines.append(
                f"- **Flat curve** (10Y-2Y = {t10y2y:.2f}%) — late cycle, watch for inversion"
            )
        elif t10y2y > 1.0:
            lines.append(
                f"- **Steep curve** (10Y-2Y = {t10y2y:.2f}%) — early cycle or steepening trade"
            )
        else:
            lines.append(f"- **Normal curve** (10Y-2Y = {t10y2y:.2f}%)")

    if dff > 0 and dgs2 > 0:
        spread_2y_ff = dgs2 - dff
        if spread_2y_ff < 0:
            lines.append(
                f"- 2Y below Fed Funds ({spread_2y_ff:+.2f}%) — market pricing rate cuts"
            )
        elif spread_2y_ff > 0.5:
            lines.append(
                f"- 2Y above Fed Funds ({spread_2y_ff:+.2f}%) — market expects tightening"
            )
    lines.append("")

    # Real yields section
    lines += [
        "## Real Yields (DFII10)",
        "",
        "| Metric | Value |",
        "|--------|-------|",
        f"| Current | **{dfii['current']}%** |",
        f"| Percentile | {dfii['pct_window']}th |",
        f"| Range | {dfii['min_window']}% – {dfii['max_window']}% |",
        "",
    ]

    if dfii["current"] > 2.0:
        lines.append("> Real yields elevated — headwind for gold, risk assets")
    elif dfii["current"] < 1.0:
        lines.append("> Real yields low — tailwind for gold")
    lines.append("")

    # Forward inflation
    t5yif = yields.get("T5YIFR", {})
    if t5yif.get("available"):
        lines += [
            "## Forward Inflation Expectations",
            "",
            f"- 5Y Breakeven: **{yields.get('T5YIE', {}).get('current', 'N/A')}%**",
            f"- 5Y5Y Forward: **{t5yif['current']:.2f}%**",
            "",
        ]
        if t5yif["current"] > 2.5:
            lines.append(
                "> Long-term inflation expectations elevated — gold supportive"
            )
        elif t5yif["current"] < 2.0:
            lines.append("> Long-term inflation expectations low — gold headwind")
        lines.append("")

    lines += [
        "---",
        f"*Generated: {datetime.now().strftime('%Y-%m-%d %H:%M')} by vault-pipeline/macro_to_vault.py*",
    ]
    return "\n".join(lines)


# ── Markdown Generation: Credit Stress ───────────────────────────────


def generate_credit_note(today: str, credit: dict, insights: list[str]) -> str:
    lines = [
        "---",
        "type: macro-credit",
        f"date: {today}",
        "---",
        "",
        f"# Credit Stress Monitor — {today}",
        "",
        "---",
        "",
        "## Credit Indicators",
        "",
        "| Series | Current | 5Y Percentile | 5Y Mean | 5Y Range |",
        "|--------|---------|---------------|---------|----------|",
    ]

    for sid in ["BAA10Y", "BAMLH0A0HYM2", "T10Y2Y"]:
        data = credit.get(sid, {})
        if data.get("available"):
            lines.append(
                f"| {data['description']} | **{data['current']:.2f}%** | "
                f"{data['pct_5y']}th | {data['mean_5y']:.2f}% | "
                f"{data['min_5y']:.2f} – {data['max_5y']:.2f} |"
            )
    lines.append("")

    lines += [
        "## Credit Assessment",
        "",
    ]
    for ins in insights:
        lines.append(f"- {ins}")
    lines.append("")

    # HY OAS detail
    hy = credit.get("BAMLH0A0HYM2", {})
    if hy.get("available"):
        lines += [
            "## High Yield OAS Detail",
            "",
            "| Metric | Value |",
            "|--------|-------|",
            f"| Current | **{hy['current']:.2f}%** |",
            f"| 5Y Percentile | {hy['pct_5y']}th |",
            f"| 5Y Mean | {hy['mean_5y']:.2f}% |",
            f"| 5Y Range | {hy['min_5y']:.2f}% – {hy['max_5y']:.2f}% |",
            f"| Last Updated | {hy['last_date']} |",
            "",
        ]

        if hy["current"] > 4.0:
            lines.append(
                "> HY OAS > 4% — significant credit stress, risk-off environment"
            )
        elif hy["current"] < 3.0:
            lines.append("> HY OAS < 3% — tight credit, risk-on environment")
        lines.append("")

    lines += [
        "---",
        f"*Generated: {datetime.now().strftime('%Y-%m-%d %H:%M')} by vault-pipeline/macro_to_vault.py*",
    ]
    return "\n".join(lines)


# ── Markdown Generation: Liquidity ───────────────────────────────────


def generate_liquidity_note(today: str, liq: dict, insights: list[str]) -> str:
    lines = [
        "---",
        "type: macro-liquidity",
        f"date: {today}",
        "---",
        "",
        f"# System Liquidity — {today}",
        "",
        "---",
        "",
        "## Liquidity Indicators",
        "",
        "| Series | Current | 5Y Percentile | 5Y Mean | Last Updated |",
        "|--------|---------|---------------|---------|--------------|",
    ]

    for sid in ["WALCL", "RRPONTSYD", "WTREGEN", "BOGMBASE"]:
        data = liq.get(sid, {})
        if data.get("available"):
            lines.append(
                f"| {data['description']} | **{data['current']:,.0f}** | "
                f"{data['pct_5y']}th | {data['mean_5y']:,.0f} | {data['last_date']} |"
            )
    lines.append("")

    lines += [
        "## Liquidity Assessment",
        "",
    ]
    for ins in insights:
        lines.append(f"- {ins}")
    lines.append("")

    # Net liquidity estimate
    walcl = liq.get("WALCL", {})
    rrp = liq.get("RRPONTSYD", {})
    tga = liq.get("WTREGEN", {})
    if all(d.get("available") for d in [walcl, rrp, tga]):
        net_liq = walcl["current"] - rrp["current"] - tga["current"]
        lines += [
            "## Net Liquidity Estimate",
            "",
            f"- Fed Balance Sheet: ${walcl['current']:,.0f}B",
            f"- ON RRP (drain): -${rrp['current']:,.0f}B",
            f"- TGA (drain): -${tga['current']:,.0f}B",
            f"- **Net System Liquidity: ${net_liq:,.0f}B**",
            "",
        ]
        if net_liq < 6000:
            lines.append(
                "> Net liquidity below $6T — tight conditions, risk assets under pressure"
            )
        elif net_liq > 7500:
            lines.append(
                "> Net liquidity above $7.5T — ample, supportive for risk assets"
            )
        lines.append("")

    lines += [
        "---",
        f"*Generated: {datetime.now().strftime('%Y-%m-%d %H:%M')} by vault-pipeline/macro_to_vault.py*",
    ]
    return "\n".join(lines)


# ── Markdown Generation: Cross-Market ────────────────────────────────


def generate_cross_market_note(
    today: str, cross: dict, dxy: dict, vix: dict, gvz: dict
) -> str:
    lines = [
        "---",
        "type: macro-cross-market",
        f"date: {today}",
        "---",
        "",
        f"# Cross-Market Signals — {today}",
        "",
        "---",
        "",
        "## Key Markets",
        "",
        "| Market | Current | 5Y Percentile | 5Y Mean | Trend |",
        "|--------|---------|---------------|---------|-------|",
    ]

    for sid in ["SP500", "DCOILBRENTEU", "DCOILWTICO", "DEXJPUS", "DEXUSEU"]:
        data = cross.get(sid, {})
        if data.get("available"):
            lines.append(
                f"| {data['description']} | **{data['current']:,.2f}** | "
                f"{data['pct_5y']}th | {data['mean_5y']:,.2f} | "
                f"{'High' if data['pct_5y'] > 70 else 'Low' if data['pct_5y'] < 30 else 'Mid'} |"
            )
    lines.append("")

    # DXY and vol summary
    lines += [
        "## Volatility & Dollar",
        "",
        "| Indicator | Value | Percentile |",
        "|-----------|-------|------------|",
        f"| VIX | {vix['current']} | {vix['pct_52w']}th |",
        f"| GVZ | {gvz['current']} | {gvz['pct_52w']}th |",
        f"| DXY | {dxy['current']} | {dxy['pct_52w']}th |",
        f"| DXY Trend | {dxy['trend']} | — |",
        "",
    ]

    # Cross-market correlations
    lines += [
        "## Cross-Market Signals",
        "",
    ]

    sp = cross.get("SP500", {})
    brent = cross.get("DCOILBRENTEU", {})
    usdjpy = cross.get("DEXJPUS", {})

    signals = []
    if sp.get("available"):
        if sp["pct_5y"] > 80:
            signals.append(
                "S&P 500 at multi-year highs — risk-on, potential gold headwind"
            )
        elif sp["pct_5y"] < 20:
            signals.append("S&P 500 at multi-year lows — risk-off, potential gold bid")

    if brent.get("available"):
        if brent["current"] > 100:
            signals.append("Brent >$100 — energy inflation risk, mixed for gold")
        elif brent["current"] < 60:
            signals.append("Brent <$60 — deflationary signal, weak commodity complex")

    if usdjpy.get("available"):
        if usdjpy["current"] > 150:
            signals.append(
                "USD/JPY elevated (>150) — BoJ intervention risk, carry trade unwind potential"
            )
        elif usdjpy["current"] < 115:
            signals.append(
                "USD/JPY low (<115) — risk-off flows to yen, broad dollar weakness"
            )

    if not signals:
        signals.append("No extreme cross-market signals")

    for s in signals:
        lines.append(f"- {s}")
    lines.append("")

    lines += [
        "---",
        f"*Generated: {datetime.now().strftime('%Y-%m-%d %H:%M')} by vault-pipeline/macro_to_vault.py*",
    ]
    return "\n".join(lines)


# ── Markdown Generation: Weekly Macro Summary ────────────────────────


def generate_weekly_summary(
    today: str,
    vix: dict,
    gvz: dict,
    dxy: dict,
    dfii: dict,
    cot: dict,
    yields: dict,
    credit: dict,
    liq: dict,
    regime: dict,
    insights: list[str],
) -> str:
    lines = [
        "---",
        "type: macro-weekly",
        f"date: {today}",
        "---",
        "",
        f"# Weekly Macro Summary — {today}",
        "",
        "---",
        "",
        "## Snapshot",
        "",
        "| Category | Key Reading | Signal |",
        "|----------|-------------|--------|",
        f"| Volatility | VIX {vix['current']} / GVZ {gvz['current']} | "
        f"{'Risk-Off' if vix['current'] > 25 else 'Elevated' if vix['current'] > 18 else 'Calm'} |",
        f"| Dollar | DXY {dxy['current']} ({dxy['trend']}) | "
        f"{'Strong' if dxy['pct_52w'] > 70 else 'Weak' if dxy['pct_52w'] < 30 else 'Neutral'} |",
        f"| Real Yields | DFII10 {dfii['current']}% | "
        f"{'Gold Headwind' if dfii['current'] > 2.0 else 'Gold Tailwind' if dfii['current'] < 1.0 else 'Neutral'} |",
        f"| XAUUSD Regime | {regime.get('regime', 'N/A')} ({regime.get('confidence', 0):.0%}) | "
        f"{'Trending' if 'TREND' in regime.get('regime', '') else 'Ranging' if regime.get('regime') == 'RANGE' else 'Unclear'} |",
        "",
    ]

    # Yield curve status
    t10y2y = yields.get("T10Y2Y", {})
    if t10y2y.get("available"):
        curve_status = (
            "Inverted"
            if t10y2y["current"] < 0
            else "Flat"
            if t10y2y["current"] < 0.25
            else "Normal"
        )
        lines.append(
            f"- Yield curve: **{curve_status}** (10Y-2Y = {t10y2y['current']:.2f}%)"
        )
    lines.append("")

    # Credit status
    hy = credit.get("BAMLH0A0HYM2", {})
    if hy.get("available"):
        credit_status = (
            "Stressed"
            if hy["current"] > 4.0
            else "Tight"
            if hy["current"] < 3.0
            else "Normal"
        )
        lines.append(f"- Credit: **{credit_status}** (HY OAS = {hy['current']:.2f}%)")
    lines.append("")

    # Liquidity
    walcl = liq.get("WALCL", {})
    rrp = liq.get("RRPONTSYD", {})
    tga = liq.get("WTREGEN", {})
    if all(d.get("available") for d in [walcl, rrp, tga]):
        net_liq = walcl["current"] - rrp["current"] - tga["current"]
        liq_status = (
            "Tight" if net_liq < 6000 else "Ample" if net_liq > 7500 else "Normal"
        )
        lines.append(f"- Net liquidity: **{liq_status}** (${net_liq:,.0f}B)")
    lines.append("")

    # COT summary
    if cot:
        lines.append(
            f"- COT: MM net long {cot['mm_net_long']:,} ({cot['mm_net_long_pct']}%), "
            f"52w index {cot['cot_index_52w']}th"
        )
    lines.append("")

    # Key insights
    lines += [
        "## Key Themes",
        "",
    ]
    for ins in insights[:8]:
        lines.append(f"- {ins}")
    lines.append("")

    lines += [
        "---",
        f"*Generated: {datetime.now().strftime('%Y-%m-%d %H:%M')} by vault-pipeline/macro_to_vault.py*",
    ]
    return "\n".join(lines)


# ── Main ─────────────────────────────────────────────────────────────


def main():
    today = datetime.now().strftime("%Y-%m-%d")
    print(f"[macro_to_vault] Generating dashboard for {today}")

    # Load core data
    vix = load_vix()
    print(f"  VIX: {vix['current']} (p{vix['pct_52w']})")

    gvz = load_gvz()
    print(f"  GVZ: {gvz['current']} (p{gvz['pct_52w']})")

    dxy = load_dxy()
    print(f"  DXY: {dxy['current']} (p{dxy['pct_52w']}) — {dxy['trend']}")

    dfii = load_dfii10()
    print(f"  DFII10: {dfii['current']}% (p{dfii['pct_window']})")

    cot = load_cot()
    if cot:
        print(f"  COT: MM net long {cot['mm_net_long']:,} ({cot['mm_net_long_pct']}%)")

    calendar = load_calendar()
    print(f"  Calendar: {len(calendar)} events loaded")

    # Load FRED data
    yields = load_yield_curve()
    print(
        f"  Yield curve: {sum(1 for v in yields.values() if v.get('available'))} series loaded"
    )

    credit = load_credit_stress()
    print(
        f"  Credit: {sum(1 for v in credit.values() if v.get('available'))} series loaded"
    )

    inflation = load_inflation_data()
    print(
        f"  Inflation: {sum(1 for v in inflation.values() if v.get('available'))} series loaded"
    )

    liq = load_liquidity_data()
    print(
        f"  Liquidity: {sum(1 for v in liq.values() if v.get('available'))} series loaded"
    )

    cross = load_cross_market()
    print(
        f"  Cross-market: {sum(1 for v in cross.values() if v.get('available'))} series loaded"
    )

    regime = load_xauusd_regime()
    if regime.get("available"):
        print(f"  XAUUSD Regime: {regime['regime']} ({regime['confidence']:.0%})")

    # Generate insights
    insights = correlation_insights(vix, gvz, dxy, dfii, cot)
    credit_insig = credit_insights(credit)
    liq_insig = liquidity_insights(liq)
    infl_insig = inflation_insights(inflation)
    all_insights = insights + credit_insig + liq_insig + infl_insig

    # Write vault notes
    VAULT_OUT.mkdir(parents=True, exist_ok=True)
    notes_written = []

    # 1. Main Dashboard
    md = generate_main_dashboard(
        today, vix, gvz, dxy, dfii, cot, calendar, insights, regime
    )
    out = VAULT_OUT / f"{today}.md"
    out.write_text(md, encoding="utf-8")
    notes_written.append(out)
    print(f"  Written: {out}")

    # 2. Yield Curve
    md = generate_yields_note(today, yields, dfii)
    out = VAULT_OUT / f"{today}-yields.md"
    out.write_text(md, encoding="utf-8")
    notes_written.append(out)
    print(f"  Written: {out}")

    # 3. Credit Stress
    md = generate_credit_note(today, credit, credit_insig)
    out = VAULT_OUT / f"{today}-credit.md"
    out.write_text(md, encoding="utf-8")
    notes_written.append(out)
    print(f"  Written: {out}")

    # 4. Liquidity
    md = generate_liquidity_note(today, liq, liq_insig)
    out = VAULT_OUT / f"{today}-liquidity.md"
    out.write_text(md, encoding="utf-8")
    notes_written.append(out)
    print(f"  Written: {out}")

    # 5. Cross-Market
    md = generate_cross_market_note(today, cross, dxy, vix, gvz)
    out = VAULT_OUT / f"{today}-cross-market.md"
    out.write_text(md, encoding="utf-8")
    notes_written.append(out)
    print(f"  Written: {out}")

    # 6. Weekly Summary
    md = generate_weekly_summary(
        today, vix, gvz, dxy, dfii, cot, yields, credit, liq, regime, all_insights
    )
    out = VAULT_OUT / f"{today}-weekly.md"
    out.write_text(md, encoding="utf-8")
    notes_written.append(out)
    print(f"  Written: {out}")

    print(
        f"\n[macro_to_vault] Done — {len(notes_written)} notes written to {VAULT_OUT}"
    )
    return notes_written


if __name__ == "__main__":
    main()
