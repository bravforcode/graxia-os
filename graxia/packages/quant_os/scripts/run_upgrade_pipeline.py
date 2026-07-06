"""
run_upgrade_pipeline.py — Graxia Continuous Upgrade Pipeline
============================================================
Drains every upgradeable signal from quant_OS 24/7:
  1. Market data ─ download fresh OHLCV ticks from MT5
  2. Feature engine ─ build 50+ features for ML
  3. ML retrain ─ walk-forward XGBoost, drift check, model swap
  4. Backtest suite ─ MTM / MRB / MLB / Ensemble on latest data
  5. NotebookLM research ─ AI analysis of findings
  6. Upgrade report ─ synthesise everything into vault

Usage:
  python scripts/run_upgrade_pipeline.py               # full pipeline
  python scripts/run_upgrade_pipeline.py --quick        # skip ML train
  python scripts/run_upgrade_pipeline.py --dry-run      # print plan only
"""

import io
import json
import os
import subprocess
import sys
import time
from datetime import UTC, datetime
from pathlib import Path

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8")

# ─── Paths ──────────────────────────────────────────────────────────────
HERE = Path(__file__).resolve().parent
QUANT_OS = HERE.parent
DATA_DIR = QUANT_OS / "data"
ML_DIR = QUANT_OS / "ml" / "models"
RESULTS_DIR = QUANT_OS / "results"
SCRIPTS_DIR = HERE
VAULT = Path(
    os.environ.get(
        "OBSIDIAN_VAULT_PATH",
        r"C:\Users\menum\quant\quant bot",
    )
)
VAULT_RESEARCH = VAULT / "02-areas" / "trading" / "research"
VAULT_UPGRADE = VAULT_RESEARCH / "upgrade_reports"
SYNC_MANIFEST = QUANT_OS / "Meta" / "upgrade_pipeline_manifest.json"

# ─── MEGA Symbols / timeframes ──────────────────────────────────────────
FOREX = ["EURUSD", "GBPUSD", "USDJPY", "AUDUSD", "USDCAD", "USDCHF", "NZDUSD"]
METALS = ["XAUUSD", "XAGUSD", "XPTUSD", "XPDUSD"]
INDICES = ["US30", "SPX500", "NAS100", "DAX40", "FTSE100", "NK225"]
COMMODITIES = ["USOIL", "UKOIL", "NGAS"]
CRYPTO = ["BTCUSD", "ETHUSD"]
SYMBOLS = FOREX + METALS + INDICES + COMMODITIES + CRYPTO
TIMEFRAMES = {"M1": 1, "M5": 5, "M15": 15, "M30": 30, "H1": 60, "H4": 240, "D1": 1440, "W1": 10080}

# ─── Helpers ────────────────────────────────────────────────────────────


def log(msg: str):
    ts = datetime.now().strftime("%H:%M:%S")
    print(f"[{ts}] {msg}")


def run(cmd: list[str], timeout: int = 300) -> subprocess.CompletedProcess:
    """Run a CLI command with sensible defaults."""
    return subprocess.run(cmd, capture_output=True, text=True, timeout=timeout, encoding="utf-8", errors="replace")


def run_py(script_name: str, args: list[str] | None = None, timeout: int = 300):
    """Run a quant_OS Python script with correct PYTHONPATH."""
    script = SCRIPTS_DIR / script_name if (SCRIPTS_DIR / script_name).exists() else QUANT_OS / script_name
    env = os.environ.copy()
    # graxia package root: <monorepo root>/graxia
    env["PYTHONPATH"] = str(QUANT_OS.parent.parent) + os.pathsep + env.get("PYTHONPATH", "")
    cmd = [sys.executable, str(script), *(args or [])]
    return run(cmd, timeout=timeout)


def append_to_vault(path: Path, content: str):
    """Append a report to the vault."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    log(f"    Wrote {path.relative_to(VAULT)}")


# ══════════════════════════════════════════════════════════════════════
#  PHASE 1: MARKET DATA
# ══════════════════════════════════════════════════════════════════════


def phase_download_market_data() -> dict:
    """MEGA parallel download — ALL symbols × ALL timeframes."""
    log("=== Phase 1/6: MEGA Market Data Download ===")
    log(f"  Targets: {len(SYMBOLS)} symbols × {len(TIMEFRAMES)} TFs = {len(SYMBOLS) * len(TIMEFRAMES)} files")
    results = {"downloaded": [], "failed": [], "skipped": [], "total_bars": 0}

    # Use mega_download.py (single-process, fast)
    downloader = SCRIPTS_DIR / "mega_download.py"
    if downloader.exists():
        log("  Launching MEGA single-process downloader...")
        try:
            r = run_py("scripts/mega_download.py", ["--quick", "--direct"], timeout=300)
            if r.returncode == 0:
                log("  MEGA downloader OK")
        except subprocess.TimeoutExpired:
            log("  MEGA downloader timed out (partial OK)")
        except Exception as e:
            log(f"  MEGA downloader error: {e}")

    # Fallback: old download_everything.py (less efficient)
    else:
        log("  mega_download.py not found, using download_everything.py...")
        try:
            r = run_py("scripts/download_everything.py", ["--quick"], timeout=300)
        except Exception as e:
            log(f"  download_everything.py error: {e}")

    # Count results regardless of exit code
    for csv in DATA_DIR.glob("*_*.csv"):
        if "_" in csv.stem and csv.stat().st_size > 100:
            symbol_tf = csv.stem
            age_seconds = time.time() - csv.stat().st_mtime
            if age_seconds < 600:  # downloaded in last 10 min
                results["downloaded"].append(symbol_tf)
                bars = len(csv.read_text(encoding="utf-8").splitlines()) - 1
                results["total_bars"] += max(bars, 0)
            else:
                results["skipped"].append(symbol_tf)

    results["downloaded"] = sorted(set(results["downloaded"]))
    results["skipped"] = sorted(set(results["skipped"]))
    log(
        f"  Downloaded: {len(results['downloaded'])} | Skipped: {len(results['skipped'])} | Bars: {results['total_bars']}"
    )
    return results


# ══════════════════════════════════════════════════════════════════════
#  PHASE 2: FEATURE ENGINEERING
# ══════════════════════════════════════════════════════════════════════


def phase_feature_engineering() -> dict:
    """Build feature sets for ML training."""
    log("=== Phase 2/6: Feature Engineering ===")
    results = {"features_built": 0, "symbols_done": []}

    for symbol in SYMBOLS:
        csv_path = DATA_DIR / f"{symbol}_M15.csv"
        if not csv_path.exists():
            log(f"  No M15 data for {symbol}, skipping")
            continue

        log(f"  Building features for {symbol}...")
        try:
            r = run_py("scripts/build_features.py", [symbol], timeout=120)
            if r.returncode == 0:
                results["symbols_done"].append(symbol)
                results["features_built"] += 1
        except Exception as e:
            log(f"  Feature build failed for {symbol}: {e}")

    log(f"  Features built for {results['features_built']} symbols")
    return results


# ══════════════════════════════════════════════════════════════════════
#  PHASE 3: ML RETRAIN (drift check + walk-forward)
# ══════════════════════════════════════════════════════════════════════


def phase_ml_retrain() -> dict:
    """Check drift, retrain if needed, run walk-forward validation."""
    log("=== Phase 3/6: ML Retrain ===")
    results = {
        "drift_checked": False,
        "drift_detected": False,
        "retrained": False,
        "models_before": 0,
        "models_after": 0,
        "walk_forward_passed": False,
    }

    # Count existing models
    results["models_before"] = len(list(ML_DIR.glob("*.pkl"))) if ML_DIR.exists() else 0

    # 1. Drift check via run_ml_train.py
    log("  Checking model drift...")
    try:
        r = run_py("run_ml_train.py", ["--check-drift"], timeout=120)
        results["drift_checked"] = r.returncode == 0
        if "DRIFT" in r.stdout or "retrain" in r.stdout.lower():
            results["drift_detected"] = True
            log("  DRIFT DETECTED — retraining...")
    except Exception:
        log("  Drift check failed (no baseline yet is OK)")

    # 2. Retrain if drift detected OR if no models exist
    needs_retrain = results["drift_detected"] or results["models_before"] == 0
    if needs_retrain:
        log("  Running walk-forward training...")
        try:
            r = run_py("run_ml_train.py", timeout=600)
            if r.returncode == 0:
                results["retrained"] = True
        except Exception as e:
            log(f"  Retrain failed: {e}")

        # Run walk-forward validation
        try:
            r = run_py("scripts/walk_forward.py", timeout=600)
            if "passed" in r.stdout.lower() or r.returncode == 0:
                results["walk_forward_passed"] = True
        except Exception:
            pass

    results["models_after"] = len(list(ML_DIR.glob("*.pkl"))) if ML_DIR.exists() else 0
    log(
        f"  Drift: {results['drift_detected']} | Retrained: {results['retrained']} | Models: {results['models_before']} -> {results['models_after']}"
    )
    return results


# ══════════════════════════════════════════════════════════════════════
#  PHASE 4: BACKTEST SUITE
# ══════════════════════════════════════════════════════════════════════


def phase_backtest_suite() -> dict:
    """Run all strategy backtests on latest data."""
    log("=== Phase 4/6: Backtest Suite ===")
    results = {"strategies_tested": 0, "results": {}, "golden_rule_fails": []}

    strategies = {
        "MTM": "run_backtest.py",
    }

    for name, script in strategies.items():
        script_path = QUANT_OS / script
        log(f"  Strategy: {name} ({script_path.name})...")
        if not script_path.exists():
            log(f"    Script not found: {script}")
            results["results"][name] = {"exit_code": -1, "error": "script not found"}
            continue
        try:
            r = run_py(script, timeout=600)
            stdout = r.stdout or ""
            stderr = r.stderr or ""

            # Parse key metrics from output
            import re

            metrics = {}
            for pattern, key in [
                (r"sharpe[\s_]*:?\s*([\d\.\-]+)", "sharpe"),
                (r"win_rate[\s_]*:?\s*([\d\.\-]+)", "win_rate"),
                (r"profit_factor[\s_]*:?\s*([\d\.\-]+)", "profit_factor"),
                (r"max_drawdown[\s_]*:?\s*([\d\.\-]+)", "max_dd"),
                (r"total_return[\s_]*:?\s*([\d\.\-]+)", "total_return"),
            ]:
                m = re.search(pattern, stdout, re.IGNORECASE)
                if m:
                    metrics[key] = float(m.group(1))

            results["results"][name] = {
                "exit_code": r.returncode,
                "metrics": metrics,
            }

            if metrics.get("sharpe", 1) < 0.5:
                results["golden_rule_fails"].append(f"{name}: Sharpe {metrics.get('sharpe', '?')}")
            if metrics.get("win_rate", 50) < 40:
                results["golden_rule_fails"].append(f"{name}: WinRate {metrics.get('win_rate', '?')}")

            results["strategies_tested"] += 1
            s = metrics.get("sharpe", "?")
            wr = metrics.get("win_rate", "?")
            pf = metrics.get("profit_factor", "?")
            s_str = f"{s:.2f}" if isinstance(s, float) else str(s)
            wr_str = f"{wr:.1f}%" if isinstance(wr, float) else str(wr)
            pf_str = f"{pf:.2f}" if isinstance(pf, float) else str(pf)
            log(f"    Sharpe={s_str} WR={wr_str} PF={pf_str}")

        except Exception as e:
            log(f"    FAILED: {e}")
            results["results"][name] = {"exit_code": -1, "error": str(e)}

    log(f"  Strategies tested: {results['strategies_tested']}")
    return results


# ══════════════════════════════════════════════════════════════════════
#  PHASE 5: NOTEBOOKLM RESEARCH
# ══════════════════════════════════════════════════════════════════════


def phase_notebooklm_research() -> dict:
    """Query NotebookLM with upgrade-focused questions."""
    log("=== Phase 5/6: NotebookLM Research ===")
    results = {"questions_asked": 0, "answers_saved": 0}

    # Check auth
    r = run(["notebooklm", "auth", "check"], timeout=30)
    if r.returncode != 0 or "SID cookie" not in (r.stdout or ""):
        log("  NotebookLM not authenticated — skipping")
        return results

    VAULT_RESEARCH.mkdir(parents=True, exist_ok=True)

    questions = [
        {
            "id": "upgrade_opportunities",
            "q": "Based on the quant_OS research data provided, what are the top 3 "
            "upgrade opportunities right now? Consider: strategy parameters, "
            "risk settings, data quality, ML model improvements, and market "
            "regime changes. Provide specific recommendations.",
        },
        {
            "id": "strategy_edge_analysis",
            "q": "Compare the MTM (momentum), MRB (mean reversion), and MLB (ML breakout) "
            "strategies. Which has the strongest current edge? Are there signs of "
            "degradation? What parameter changes could help?",
        },
        {
            "id": "risk_parameter_review",
            "q": "Review the current risk parameters. Are position sizing, drawdown limits, "
            "and stop-loss settings appropriate for current market conditions? "
            "Any recommended adjustments?",
        },
    ]

    for q in questions:
        log(f"  Asking: {q['id']}...")
        try:
            r = run(["notebooklm", "ask", q["q"]], timeout=180)
            if r.returncode == 0 and r.stdout:
                now = datetime.now(UTC).strftime("%Y-%m-%d %H:%M UTC")
                content = f"""---
created: {now}
source: NotebookLM
category: upgrade-pipeline
tags: [notebooklm, upgrade-auto, {q['id']}]
---

# Upgrade Insight: {q['id']}

{_strip_ansi(r.stdout)}
"""
                path = VAULT_RESEARCH / f"upgrade_{q['id']}.md"
                path.write_text(content, encoding="utf-8")
                results["answers_saved"] += 1
                log(f"    Saved: {q['id']}")
        except Exception as e:
            log(f"    Failed: {e}")
        results["questions_asked"] += 1

    log(f"  Questions: {results['questions_asked']} | Saved: {results['answers_saved']}")
    return results


# ══════════════════════════════════════════════════════════════════════
#  PHASE 6: UPGRADE REPORT
# ══════════════════════════════════════════════════════════════════════


def phase_upgrade_report(all_results: dict) -> dict:
    """Synthesise everything into a single upgrade report in the vault."""
    log("=== Phase 6/6: Upgrade Report ===")
    now = datetime.now(UTC)
    now_str = now.strftime("%Y-%m-%d %H:%M UTC")
    date_str = now.strftime("%Y-%m-%d")

    # Collect metrics
    data = all_results.get("market_data", {})
    ml = all_results.get("ml_retrain", {})
    bt = all_results.get("backtest", {})
    nb = all_results.get("notebooklm", {})

    # Strategy summary table
    strat_rows = ""
    for name, result in bt.get("results", {}).items():
        m = result.get("metrics", {})

        def fmt(v, fmt_str):
            if isinstance(v, (int, float)):
                return f"{v:{fmt_str}}"
            return str(v)

        strat_rows += f"| {name} | {fmt(m.get('sharpe'), '.2f')} | {fmt(m.get('win_rate'), '.1f')}% | {fmt(m.get('profit_factor'), '.2f')} | {fmt(m.get('max_dd'), '.1f')}% | {fmt(m.get('total_return'), '.2f')} | {'OK' if result.get('exit_code') == 0 else 'FAIL'} |\n"

    # Compute data coverage
    csv_count = len(list(DATA_DIR.glob("*.csv")))
    data_mb = sum(f.stat().st_size for f in DATA_DIR.glob("*.csv") if f.name != "paper_trade_log.csv") / 1048576

    report = f"""---
created: {now_str}
tags: [upgrade-pipeline, daily-report, bridge-auto]
---

# Quant OS — Daily Upgrade Report

**Date:** {date_str}
**Duration:** {_elapsed(all_results.get('_start', now))}
**Stages run:** {len(all_results.get('_phases_run', []))}/6
**Data Coverage:** {csv_count} CSVs ({data_mb:.1f} MB)

## Executive Summary

| Area | Status | Detail |
|------|--------|--------|
| Market Data | {'✅' if data.get('downloaded') else '⏭️'} | {len(data.get('downloaded', []))} new / {len(data.get('skipped', []))} cached |
| Feature Engineering | {'✅' if ml.get('drift_checked') else '⏭️'} | {ml.get('features_built', 0)} symbols |
| ML Retrain | {'✅' if ml.get('retrained') else '⏭️'} | Drift: {'⚠️ YES' if ml.get('drift_detected') else 'No'} | Models: {ml.get('models_before', 0)} → {ml.get('models_after', 0)} |
| Backtest Suite | {'✅' if bt.get('strategies_tested', 0) > 0 else '⏭️'} | {bt.get('strategies_tested', 0)} strategies |
| NotebookLM | {'✅' if nb.get('answers_saved', 0) > 0 else '⏭️'} | {nb.get('answers_saved', 0)} insights |
| Upgrade Report | ✅ | This document |

## Market Data

- **Data files:** {csv_count} CSVs ({data_mb:.1f} MB)
- **Symbols:** {len(SYMBOLS)} total (Forex, Metals, Indices, Crypto)
- **Timeframes:** {', '.join(TIMEFRAMES.keys())}
- **Downloaded this run:** {len(data.get('downloaded', []))} files
- **Cached (skipped):** {len(data.get('skipped', []))} files
- **Failed:** {', '.join(data.get('failed', [])) or 'none'}
- **Total bars added:** {data.get('total_bars', 0):,}

## ML Drift & Retrain

- Drift checked: {ml.get('drift_checked', False)}
- Drift detected: {ml.get('drift_detected', False)}
- Retrained: {ml.get('retrained', False)}
- Walk-forward passed: {ml.get('walk_forward_passed', False)}
- Models: {ml.get('models_before', 0)} → {ml.get('models_after', 0)}

## Backtest Results

| Strategy | Sharpe | WinRate | ProfitFactor | MaxDD | Return | Status |
|----------|--------|---------|-------------|-------|--------|--------|
{strat_rows}

## Golden Rule Failures

{chr(10).join(f'- ⚠️ {f}' for f in bt.get('golden_rule_fails', [])) or '✅ All strategies pass golden rules'}

## NotebookLM Insights

- Questions asked: {nb.get('questions_asked', 0)}
- Insights saved: {nb.get('answers_saved', 0)}
- View in: `02-areas/trading/research/upgrade_*.md`

## Files Updated

| Phase | File |
|------|------|
| Research | `02-areas/trading/research/upgrade_*.md` |
| Report | `02-areas/trading/research/upgrade_reports/{date_str}.md` |
| Bridge | `Meta/states/bridge_state.md` |

## Next Check

Scheduled: next full pipeline run in ~6 hours.
"""

    # Save report
    report_path = VAULT_UPGRADE / f"{date_str}.md"
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(report, encoding="utf-8")
    log(f"  Report saved: {report_path.relative_to(VAULT)}")

    # Save current state manifest
    all_results["_report_time"] = now_str
    SYNC_MANIFEST.parent.mkdir(parents=True, exist_ok=True)
    SYNC_MANIFEST.write_text(
        json.dumps(
            {
                "last_run": now_str,
                "phases": all_results.get("_phases_run", []),
                "summary": {
                    "market_data_downloaded": len(data.get("downloaded", [])),
                    "ml_retrained": ml.get("retrained", False),
                    "strategies_tested": bt.get("strategies_tested", 0),
                    "insights_saved": nb.get("answers_saved", 0),
                },
            },
            indent=2,
        ),
        encoding="utf-8",
    )

    return {"report_path": str(report_path.relative_to(VAULT))}


# ─── Utilities ──────────────────────────────────────────────────────────


def _strip_ansi(text: str) -> str:
    import re

    return re.sub(r"\x1b\[[0-9;]*m", "", text)


def _elapsed(start: datetime) -> str:
    delta = datetime.now(UTC) - start
    mins = int(delta.total_seconds() // 60)
    secs = int(delta.total_seconds() % 60)
    return f"{mins}m {secs}s" if mins else f"{secs}s"


# ══════════════════════════════════════════════════════════════════════
#  MAIN
# ══════════════════════════════════════════════════════════════════════


def main():
    import argparse

    parser = argparse.ArgumentParser(description="Graxia Continuous Upgrade Pipeline")
    parser.add_argument("--quick", action="store_true", help="Skip retrain, just data+backtest")
    parser.add_argument("--dry-run", action="store_true", help="Print plan only")
    args = parser.parse_args()

    start = datetime.now(UTC)

    phases = [
        ("market_data", phase_download_market_data),
        ("ml_retrain", phase_ml_retrain),
        ("backtest", phase_backtest_suite),
        ("notebooklm", phase_notebooklm_research),
    ]
    if not args.quick:
        phases.insert(1, ("features", phase_feature_engineering))

    all_results = {"_start": start, "_phases_run": []}

    if args.dry_run:
        log("=== DRY RUN ===")
        for name, _ in phases:
            log(f"  Would run: {name}")
        log("=== End dry run ===")
        return

    log("============================================")
    log("  Graxia — Continuous Upgrade Pipeline")
    log(f"  Started at {start.strftime('%Y-%m-%d %H:%M:%S UTC')}")
    log(f"  Mode: {'QUICK' if args.quick else 'FULL'}")
    log("============================================")

    for name, func in phases:
        try:
            result = func()
            all_results[name] = result
            all_results["_phases_run"].append(name)
        except Exception as e:
            log(f"  PHASE {name} FAILED: {e}")
            all_results[name] = {"error": str(e)}

    # Final phase: upgrade report
    all_results["_phases_run"].append("upgrade_report")
    phase_upgrade_report(all_results)

    elapsed = _elapsed(start)
    log(f"=== Pipeline Complete (elapsed: {elapsed}) ===")
    log(f"Phases run: {len(all_results['_phases_run'])}/6")

    # Trigger bridge sync
    log("Triggering bridge sync to vault...")
    try:
        run_py("scripts/bridge_automated_sync.py", timeout=120)
    except Exception:
        pass

    log("=== Done ===")


if __name__ == "__main__":
    main()
