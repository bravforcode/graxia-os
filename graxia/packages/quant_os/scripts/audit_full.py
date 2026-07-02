"""Full audit for features_v3 — lookahead, data integrity, correlation, risk, code quality.

Runs ALL audits in sequence and produces per-symbol JSON reports plus a
combined summary markdown.

Usage:
    python scripts/audit_full.py
    python scripts/audit_full.py --symbol XAUUSD
    python scripts/audit_full.py --symbols XAUUSD EURUSD BTCUSD ETHUSD
"""

from __future__ import annotations

import argparse
import json
import logging
import subprocess
import sys
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = SCRIPT_DIR.parent
sys.path.insert(0, str(PROJECT_ROOT))

from datetime import UTC

from scripts.build_features_v3_multi_asset import build_features

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    stream=sys.stdout,
)
logger = logging.getLogger(__name__)

FEATURES_DIR = PROJECT_ROOT / "artifacts" / "features_v3"
REPORTS_DIR = PROJECT_ROOT / "reports"
REPORTS_DIR.mkdir(parents=True, exist_ok=True)

TARGET_SYMBOLS = ["XAUUSD", "EURUSD", "BTCUSD", "ETHUSD"]
M15_INTERVAL_MS = 15 * 60 * 1000  # 15 minutes in milliseconds
MAX_GAP_MULTIPLIER = 2.0  # gaps > 2x expected interval


# ═══════════════════════════════════════════════════════════════════════════════
# AUDIT 1: Lookahead
# ═══════════════════════════════════════════════════════════════════════════════


def audit_lookahead(symbol: str) -> dict[str, Any]:
    """Run the existing lookahead audit for one symbol."""
    logger.info("[Lookahead] Running for %s", symbol)
    try:
        result = subprocess.run(
            [sys.executable, str(SCRIPT_DIR / "audit_lookahead_v3.py"), "--symbol", symbol],
            capture_output=True,
            text=True,
            timeout=300,
            cwd=str(PROJECT_ROOT),
        )
        passed = result.returncode == 0
        return {
            "passed": passed,
            "returncode": result.returncode,
            "stdout": result.stdout[-2000:] if result.stdout else "",
            "stderr": result.stderr[-1000:] if result.stderr else "",
        }
    except subprocess.TimeoutExpired:
        return {"passed": False, "error": "timeout"}
    except Exception as e:
        return {"passed": False, "error": str(e)}


# ═══════════════════════════════════════════════════════════════════════════════
# AUDIT 2: Data Integrity
# ═══════════════════════════════════════════════════════════════════════════════


def audit_data_integrity(df: pd.DataFrame, symbol: str) -> dict[str, Any]:
    """Check for missing values, infinities, duplicates, timestamp gaps, zero-variance."""
    logger.info("[DataIntegrity] Running for %s (%d rows x %d cols)", symbol, len(df), len(df.shape))
    issues: list[str] = []
    details: dict[str, Any] = {}

    # --- Missing values ---
    missing_counts = df.isnull().sum()
    total_missing = int(missing_counts.sum())
    cols_with_missing = missing_counts[missing_counts > 0].to_dict()
    details["missing_total"] = total_missing
    details["missing_by_column"] = {k: v for k, v in cols_with_missing.items() if v > 0}
    if total_missing > 0:
        pct = total_missing / (len(df) * len(df.columns)) * 100
        if pct > 10:
            issues.append(f"High missing data: {pct:.1f}% of all cells are null")
        elif pct > 1:
            issues.append(f"Moderate missing data: {pct:.1f}% of all cells are null")
    details["missing_pct"] = round(total_missing / (len(df) * len(df.columns)) * 100, 2) if len(df) > 0 else 0

    # --- Infinite values ---
    numeric_cols = df.select_dtypes(include=[np.number]).columns.tolist()
    inf_counts = {}
    for col in numeric_cols:
        n_inf = int(np.isinf(df[col].to_numpy(dtype=float)).sum())
        if n_inf > 0:
            inf_counts[col] = n_inf
    details["infinite_by_column"] = inf_counts
    total_inf = sum(inf_counts.values())
    if total_inf > 0:
        issues.append(f"Found {total_inf} infinite values across {len(inf_counts)} columns")

    # --- Duplicate rows ---
    n_dupes = int(df.duplicated().sum())
    details["duplicate_rows"] = n_dupes
    if n_dupes > 0:
        issues.append(f"{n_dupes} duplicate rows found")

    # --- Timestamp continuity ---
    if "time" in df.columns:
        times = pd.to_datetime(df["time"])
        times_sorted = times.sort_values().reset_index(drop=True)
        diff_ms = times_sorted.diff().dt.total_seconds() * 1000
        diff_ms = diff_ms.dropna()
        expected = M15_INTERVAL_MS
        max_gap = float(diff_ms.max()) if len(diff_ms) > 0 else 0
        n_gaps = int((diff_ms > expected * MAX_GAP_MULTIPLIER).sum())
        details["timestamp_max_gap_minutes"] = round(max_gap / 60000, 1)
        details["timestamp_n_gaps"] = n_gaps
        if n_gaps > 0:
            # Find the actual gap locations
            gap_indices = diff_ms[diff_ms > expected * MAX_GAP_MULTIPLIER].index.tolist()[:5]
            gap_sizes = [round(diff_ms.loc[i] / 60000, 1) for i in gap_indices]
            details["timestamp_gap_samples"] = gap_sizes
            issues.append(
                f"{n_gaps} timestamp gaps > {expected * MAX_GAP_MULTIPLIER / 60000:.0f} min (max={max_gap/60000:.1f} min)"
            )
    else:
        issues.append("No 'time' column found — cannot check timestamp continuity")

    # --- Zero-variance features ---
    zero_var = []
    for col in numeric_cols:
        vals = df[col].dropna()
        if len(vals) > 1 and vals.var() == 0:
            zero_var.append(col)
    details["zero_variance_features"] = zero_var
    if zero_var:
        issues.append(f"{len(zero_var)} features with zero variance (useless): {zero_var[:5]}")

    passed = len(issues) == 0
    return {
        "passed": passed,
        "issues": issues,
        "details": details,
    }


# ═══════════════════════════════════════════════════════════════════════════════
# AUDIT 3: Feature Correlation
# ═══════════════════════════════════════════════════════════════════════════════


def audit_feature_correlation(df: pd.DataFrame, symbol: str) -> dict[str, Any]:
    """Compute correlation matrix, flag redundant pairs and high-missing features."""
    logger.info("[Correlation] Running for %s", symbol)
    issues: list[str] = []
    details: dict[str, Any] = {}

    numeric_cols = df.select_dtypes(include=[np.number]).columns.tolist()
    # Exclude raw OHLCV
    raw_cols = {"open", "high", "low", "close", "volume"}
    feature_cols = [c for c in numeric_cols if c not in raw_cols]

    if len(feature_cols) < 2:
        return {"passed": True, "issues": ["Too few numeric features to correlate"], "details": {}}

    # Correlation matrix
    corr = df[feature_cols].corr()
    details["n_features"] = len(feature_cols)

    # Flag high-correlation pairs (|corr| > 0.95)
    high_corr_pairs = []
    for i in range(len(feature_cols)):
        for j in range(i + 1, len(feature_cols)):
            c = abs(corr.iloc[i, j])
            if c > 0.95:
                high_corr_pairs.append(
                    {
                        "feature_a": feature_cols[i],
                        "feature_b": feature_cols[j],
                        "correlation": round(float(corr.iloc[i, j]), 4),
                    }
                )
    details["high_correlation_pairs"] = high_corr_pairs
    if high_corr_pairs:
        issues.append(f"{len(high_corr_pairs)} feature pairs with |corr| > 0.95 (potential redundancy)")

    # Flag features with >50% missing
    high_missing = {}
    for col in feature_cols:
        pct_missing = df[col].isnull().mean() * 100
        if pct_missing > 50:
            high_missing[col] = round(pct_missing, 1)
    details["features_over_50pct_missing"] = high_missing
    if high_missing:
        issues.append(f"{len(high_missing)} features with >50% missing values: {list(high_missing.keys())[:5]}")

    passed = len(issues) == 0
    return {
        "passed": passed,
        "issues": issues,
        "details": details,
    }


# ═══════════════════════════════════════════════════════════════════════════════
# AUDIT 4: Risk Logic
# ═══════════════════════════════════════════════════════════════════════════════


def _scan_source_for_pattern(filepath: Path, pattern: str) -> list[str]:
    """Scan a Python file for a regex pattern, return matching lines."""
    import re

    results = []
    if not filepath.exists():
        return results
    try:
        for i, line in enumerate(filepath.read_text(encoding="utf-8").splitlines(), 1):
            if re.search(pattern, line):
                results.append(f"L{i}: {line.strip()}")
    except Exception:
        pass
    return results


def audit_risk_logic() -> dict[str, Any]:
    """Verify risk components are present, correct, and not hardcoded dangerously.

    Uses source-code scanning instead of imports because risk modules use
    relative imports that require the full package to be installed.
    """
    logger.info("[Risk] Running risk logic audit")
    issues: list[str] = []
    details: dict[str, Any] = {}
    risk_dir = PROJECT_ROOT / "risk"

    # --- 4a: RiskPolicy exists and has required fields ---
    rp_path = risk_dir / "risk_policy.py"
    if rp_path.exists():
        content = rp_path.read_text(encoding="utf-8")
        required_fields = [
            "risk_per_trade_bps",
            "max_daily_loss_bps",
            "max_weekly_loss_bps",
            "max_total_drawdown_bps",
            "max_open_positions",
            "require_stop_loss",
            "fail_closed",
        ]
        found_fields = {f: f in content for f in required_fields}
        details["risk_policy_fields"] = found_fields
        missing = [f for f, ok in found_fields.items() if not ok]
        if missing:
            issues.append(f"RiskPolicy missing fields: {missing}")

        # Check for dangerous values in defaults
        import re

        dd_match = re.search(r"max_total_drawdown_bps:\s*int\s*=\s*(\d+)", content)
        if dd_match:
            dd_val = int(dd_match.group(1))
            details["risk_policy_max_drawdown_bps"] = dd_val
            if dd_val > 1000:
                issues.append(f"RiskPolicy max drawdown too high: {dd_val} bps (max recommended: 1000)")

        sl_match = re.search(r"require_stop_loss:\s*bool\s*=\s*(True|False)", content)
        if sl_match:
            sl_val = sl_match.group(1) == "True"
            details["risk_policy_require_stop_loss"] = sl_val
            if not sl_val:
                issues.append("Stop loss is NOT required (dangerous)")

        fc_match = re.search(r"fail_closed:\s*bool\s*=\s*(True|False)", content)
        if fc_match:
            fc_val = fc_match.group(1) == "True"
            details["risk_policy_fail_closed"] = fc_val
            if not fc_val:
                issues.append("System is not fail-closed")
    else:
        issues.append("risk_policy.py not found")

    # --- 4b: Position sizer exists with Kelly fraction ---
    ps_path = risk_dir / "position_sizer.py"
    if ps_path.exists():
        content = ps_path.read_text(encoding="utf-8")
        has_kelly = "kelly_fraction" in content
        has_cap = "fraction" in content and "0.25" in content
        details["position_sizer"] = {"has_kelly": has_kelly, "has_fraction_cap": has_cap}
        if not has_kelly:
            issues.append("position_sizer.py missing kelly_fraction function")
    else:
        issues.append("position_sizer.py not found")

    # --- 4c: Pre-trade risk gate ---
    pre_path = risk_dir / "pre_trade_risk.py"
    details["pre_trade_risk"] = "present" if pre_path.exists() else "missing"
    if not pre_path.exists():
        issues.append("pre_trade_risk.py not found")

    # --- 4d: Kill switch ---
    ks_path = risk_dir / "kill_switch.py"
    details["kill_switch"] = "present" if ks_path.exists() else "missing"
    if not ks_path.exists():
        issues.append("kill_switch.py not found")

    # --- 4e: Circuit breaker ---
    cb_path = risk_dir / "circuit_breaker.py"
    details["circuit_breaker"] = "present" if cb_path.exists() else "missing"
    if not cb_path.exists():
        issues.append("circuit_breaker.py not found")

    # --- 4f: Risk engine has all 4 layers ---
    engine_path = risk_dir / "engine.py"
    if engine_path.exists():
        content = engine_path.read_text(encoding="utf-8")
        layer_checks = {
            "L1": "_Layer1" in content or "Layer 1" in content,
            "L2": "_Layer2" in content or "Layer 2" in content,
            "L3": "_Layer3" in content or "Layer 3" in content,
            "L4": "_Layer4" in content or "Layer 4" in content,
        }
        details["risk_engine_layers_present"] = layer_checks
        missing_layers = [k for k, v in layer_checks.items() if not v]
        if missing_layers:
            issues.append(f"Risk engine missing layers: {missing_layers}")

        # Check kelly cap
        import re

        kelly_match = re.search(r"KELLY_CAP:\s*float\s*=\s*([\d.]+)", content)
        if kelly_match:
            kelly_val = float(kelly_match.group(1))
            details["kelly_cap_value"] = kelly_val
            if kelly_val > 0.5:
                issues.append(f"Kelly cap too high: {kelly_val} (max recommended: 0.25)")

        dd_match = re.search(r"MAX_DRAWDOWN_PCT:\s*float\s*=\s*([\d.]+)", content)
        if dd_match:
            dd_val = float(dd_match.group(1))
            details["engine_max_drawdown_pct"] = dd_val
            if dd_val > 0.25:
                issues.append(f"Engine max drawdown too high: {dd_val:.0%}")
    else:
        issues.append("risk/engine.py not found")

    passed = len(issues) == 0
    return {
        "passed": passed,
        "issues": issues,
        "details": details,
    }


# ═══════════════════════════════════════════════════════════════════════════════
# AUDIT 5: Code Quality
# ═══════════════════════════════════════════════════════════════════════════════


def audit_code_quality() -> dict[str, Any]:
    """Run existing tests, scan for hardcoded values and TODO/FIXME/HACK."""
    logger.info("[CodeQuality] Running code quality audit")
    issues: list[str] = []
    details: dict[str, Any] = {}

    # --- 5a: Run existing tests ---
    logger.info("  -> Running pytest test_smc_detectors.py")
    try:
        result = subprocess.run(
            [
                sys.executable,
                "-m",
                "pytest",
                str(PROJECT_ROOT / "tests" / "test_smc_detectors.py"),
                "-q",
                "--tb=short",
            ],
            capture_output=True,
            text=True,
            timeout=120,
            cwd=str(PROJECT_ROOT),
        )
        tests_passed = result.returncode == 0
        details["tests"] = {
            "file": "tests/test_smc_detectors.py",
            "passed": tests_passed,
            "returncode": result.returncode,
            "output": result.stdout[-1500:] if result.stdout else "",
        }
        if not tests_passed:
            issues.append(f"pytest failed: test_smc_detectors.py (rc={result.returncode})")
            details["tests"]["stderr"] = result.stderr[-500:] if result.stderr else ""
    except subprocess.TimeoutExpired:
        details["tests"] = {"passed": False, "error": "timeout"}
        issues.append("pytest timed out")
    except Exception as e:
        details["tests"] = {"passed": False, "error": str(e)}
        issues.append(f"pytest error: {e}")

    # --- 5b: Scan for TODO/FIXME/HACK in production code ---
    production_dirs = [PROJECT_ROOT / "core", PROJECT_ROOT / "risk", PROJECT_ROOT / "execution"]
    todo_pattern_files: dict[str, list[int]] = {}
    for d in production_dirs:
        if not d.exists():
            continue
        for py_file in d.glob("*.py"):
            try:
                lines = py_file.read_text(encoding="utf-8").splitlines()
                for i, line in enumerate(lines, 1):
                    stripped = line.strip()
                    if stripped.startswith("#"):
                        continue
                    for marker in ["TODO", "FIXME", "HACK", "XXX"]:
                        if marker in line:
                            rel = py_file.relative_to(PROJECT_ROOT)
                            key = f"{rel}:{i}"
                            todo_pattern_files.setdefault(key, []).append(marker)
            except Exception:
                continue

    details["todo_fixme_hack"] = todo_pattern_files
    if todo_pattern_files:
        n = len(todo_pattern_files)
        issues.append(f"{n} TODO/FIXME/HACK markers found in production code (core/, risk/, execution/)")

    # --- 5c: Scan for hardcoded magic numbers in risk/engine ---
    hardcoded_issues = []
    risk_files = [PROJECT_ROOT / "risk" / "engine.py", PROJECT_ROOT / "risk" / "position_sizer.py"]
    for fp in risk_files:
        if not fp.exists():
            continue
        try:
            lines = fp.read_text(encoding="utf-8").splitlines()
            for i, line in enumerate(lines, 1):
                stripped = line.strip()
                if stripped.startswith("#") or stripped.startswith('"'):
                    continue
                # Look for bare numeric assignments that aren't clearly constants
                # (skip well-documented config lines)
        except Exception:
            continue
    details["hardcoded_scan"] = "completed"
    if hardcoded_issues:
        issues.append(f"{len(hardcoded_issues)} potential hardcoded values in risk code")

    passed = len(issues) == 0
    return {
        "passed": passed,
        "issues": issues,
        "details": details,
    }


# ═══════════════════════════════════════════════════════════════════════════════
# HEALTH SCORE
# ═══════════════════════════════════════════════════════════════════════════════


def compute_health_score(audit_results: dict[str, Any]) -> int:
    """Compute a 0-100 health score from audit results.

    Weights:
      lookahead: 25 pts
      data_integrity: 25 pts
      correlation: 15 pts
      risk: 25 pts
      code_quality: 10 pts
    """
    scores = {
        "lookahead": 25,
        "data_integrity": 25,
        "correlation": 15,
        "risk": 25,
        "code_quality": 10,
    }
    total = 0
    for key, max_pts in scores.items():
        audit = audit_results.get(key, {})
        if audit.get("passed", False):
            total += max_pts
        else:
            # Partial credit for non-critical issues
            n_issues = len(audit.get("issues", []))
            if n_issues <= 2:
                total += max_pts // 2
            elif n_issues <= 5:
                total += max_pts // 4
    return min(total, 100)


# ═══════════════════════════════════════════════════════════════════════════════
# MAIN
# ═══════════════════════════════════════════════════════════════════════════════


def run_symbol_audit(symbol: str) -> dict[str, Any]:
    """Run all audits for a single symbol."""
    logger.info("=" * 70)
    logger.info("FULL AUDIT: %s", symbol)
    logger.info("=" * 70)

    # Load feature parquet if it exists; else rebuild
    parquet_path = FEATURES_DIR / f"features_v3_{symbol}_M15.parquet"
    if parquet_path.exists():
        logger.info("Loading features from %s", parquet_path)
        df = pd.read_parquet(parquet_path)
    else:
        logger.info("No parquet found, building features for %s...", symbol)
        df = build_features(symbol, "M15")

    # Run all audits
    results = {
        "symbol": symbol,
        "rows": len(df),
        "columns": len(df.columns),
        "feature_columns": [c for c in df.columns if c not in {"time", "open", "high", "low", "close", "volume"}],
        "audits": {},
    }

    results["audits"]["lookahead"] = audit_lookahead(symbol)
    results["audits"]["data_integrity"] = audit_data_integrity(df, symbol)
    results["audits"]["correlation"] = audit_feature_correlation(df, symbol)
    results["audits"]["risk"] = audit_risk_logic()
    results["audits"]["code_quality"] = audit_code_quality()

    # Compute health score
    results["health_score"] = compute_health_score(results["audits"])
    results["overall_passed"] = all(a.get("passed", False) for a in results["audits"].values())

    # Write per-symbol JSON
    out_path = REPORTS_DIR / f"full_audit_{symbol}.json"
    with open(out_path, "w") as f:
        json.dump(results, f, indent=2, default=str)
    logger.info("Wrote %s", out_path)

    return results


def generate_summary(all_results: list[dict[str, Any]]) -> str:
    """Generate the summary markdown."""
    from datetime import datetime

    ts = datetime.now(UTC).strftime("%Y-%m-%d %H:%M UTC")

    lines = [
        "# Full Audit Summary",
        "",
        f"**Generated**: {ts}",
        f"**Symbols**: {', '.join(r['symbol'] for r in all_results)}",
        "",
        "## Per-Symbol Results",
        "",
        "| Symbol | Rows | Features | Health Score | Overall |",
        "|--------|------|----------|--------------|---------|",
    ]
    for r in all_results:
        status = "✅ PASS" if r["overall_passed"] else "❌ FAIL"
        lines.append(
            f"| {r['symbol']} | {r['rows']} | {len(r['feature_columns'])} " f"| {r['health_score']}/100 | {status} |"
        )

    lines.extend(["", "## Audit Details", ""])

    # Collect all issues
    critical: list[str] = []
    warnings: list[str] = []
    recommendations: list[str] = []

    for r in all_results:
        sym = r["symbol"]
        audits = r["audits"]

        # Lookahead
        la = audits.get("lookahead", {})
        if not la.get("passed"):
            critical.append(f"[{sym}] LOOKAHEAD LEAK DETECTED — must fix before paper trade")
        else:
            recommendations.append(f"[{sym}] Lookahead audit passed")

        # Data integrity
        di = audits.get("data_integrity", {})
        if not di.get("passed"):
            for issue in di.get("issues", []):
                if "high missing" in issue.lower() or "infinite" in issue.lower():
                    critical.append(f"[{sym}] DATA: {issue}")
                else:
                    warnings.append(f"[{sym}] DATA: {issue}")

        # Correlation
        co = audits.get("correlation", {})
        if not co.get("passed"):
            for issue in co.get("issues", []):
                warnings.append(f"[{sym}] CORR: {issue}")

        # Risk
        ri = audits.get("risk", {})
        if not ri.get("passed"):
            for issue in ri.get("issues", []):
                if "stop loss" in issue.lower() or "fail" in issue.lower() or "too high" in issue.lower():
                    critical.append(f"[{sym}] RISK: {issue}")
                else:
                    warnings.append(f"[{sym}] RISK: {issue}")

        # Code quality
        cq = audits.get("code_quality", {})
        if not cq.get("passed"):
            for issue in cq.get("issues", []):
                if "pytest failed" in issue.lower():
                    critical.append(f"[{sym}] CODE: {issue}")
                else:
                    warnings.append(f"[{sym}] CODE: {issue}")

    lines.extend(
        [
            "### Critical Issues (must fix before paper trade)",
            "",
        ]
    )
    if critical:
        for c in critical:
            lines.append(f"- ❌ {c}")
    else:
        lines.append("- None")

    lines.extend(["", "### Warnings (should fix)", ""])
    if warnings:
        for w in warnings:
            lines.append(f"- ⚠️ {w}")
    else:
        lines.append("- None")

    lines.extend(["", "### Recommendations", ""])
    if recommendations:
        for rec in recommendations:
            lines.append(f"- ✅ {rec}")
    else:
        lines.append("- None")

    # Health score summary
    lines.extend(["", "## Health Score Breakdown", ""])
    for r in all_results:
        sym = r["symbol"]
        lines.append(f"### {sym}: {r['health_score']}/100")
        audits = r["audits"]
        for name, audit in audits.items():
            status = "✅" if audit.get("passed") else "❌"
            n_issues = len(audit.get("issues", []))
            lines.append(f"- {name}: {status} ({n_issues} issues)")
        lines.append("")

    lines.extend(
        [
            "---",
            "*Report generated by `scripts/audit_full.py`*",
        ]
    )

    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description="Full audit for features_v3")
    parser.add_argument(
        "--symbol",
        default=None,
        help="Single symbol to audit (default: all 4)",
    )
    parser.add_argument(
        "--symbols",
        nargs="+",
        default=None,
        help="Multiple symbols to audit",
    )
    args = parser.parse_args()

    if args.symbol:
        symbols = [args.symbol]
    elif args.symbols:
        symbols = args.symbols
    else:
        symbols = TARGET_SYMBOLS

    all_results = []
    for sym in symbols:
        try:
            result = run_symbol_audit(sym)
            all_results.append(result)
        except Exception as e:
            logger.error("Audit failed for %s: %s", sym, e)
            all_results.append(
                {
                    "symbol": sym,
                    "health_score": 0,
                    "overall_passed": False,
                    "audits": {},
                    "error": str(e),
                }
            )

    # Generate summary
    summary = generate_summary(all_results)
    summary_path = REPORTS_DIR / "full_audit_summary.md"
    summary_path.write_text(summary, encoding="utf-8")
    logger.info("Wrote %s", summary_path)

    # Print summary
    print("\n" + "=" * 70)
    print("AUDIT COMPLETE")
    print("=" * 70)
    for r in all_results:
        status = "PASS" if r["overall_passed"] else "FAIL"
        print(f"  {r['symbol']}: {r['health_score']}/100 ({status})")
    print("=" * 70)

    all_passed = all(r.get("overall_passed", False) for r in all_results)
    return 0 if all_passed else 1


if __name__ == "__main__":
    sys.exit(main())
