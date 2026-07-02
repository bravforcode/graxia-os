"""Paper trade readiness checklist — validates all prerequisites.

Checks: MT5 connection, data pipeline, models, risk limits, monitoring.
Outputs reports/paper_trade_readiness.json with pass/fail per item.

Usage:
    python scripts/paper_trade_checklist.py
    python scripts/paper_trade_checklist.py --verbose
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import sys
from dataclasses import asdict, dataclass
from datetime import datetime, UTC
from pathlib import Path

# ── Paths ─────────────────────────────────────────────────────────────

SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = SCRIPT_DIR.parent
REPORTS_DIR = PROJECT_ROOT / "reports"
CONFIG_PATH = PROJECT_ROOT / "config" / "paper_trade_config.json"
DATA_DIR = PROJECT_ROOT / "data"
ML_MODELS_DIR = PROJECT_ROOT / "ml" / "models"
ARTIFACTS_DIR = PROJECT_ROOT / "artifacts"

# Ensure project root is on sys.path for imports
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

# Load .env
try:
    from dotenv import load_dotenv
    load_dotenv(PROJECT_ROOT / ".env")
except ImportError:
    pass

logging.basicConfig(level=logging.INFO, format="%(message)s", stream=sys.stdout)
logger = logging.getLogger(__name__)


# ── Checklist item ────────────────────────────────────────────────────

@dataclass
class CheckItem:
    name: str
    passed: bool
    message: str
    category: str
    severity: str = "required"  # required or recommended


@dataclass
class ChecklistResult:
    timestamp: str
    overall_pass: bool
    items: list[dict]
    summary: dict  # {total, passed, failed, required_failed}


# ── Checks ────────────────────────────────────────────────────────────

def check_mt5_connection() -> CheckItem:
    """Verify MT5 terminal is reachable and credentials are set."""
    try:
        import MetaTrader5 as mt5
    except ImportError:
        return CheckItem(
            name="MT5 Connection",
            passed=False,
            message="MetaTrader5 package not installed. Run: pip install MetaTrader5",
            category="mt5",
        )

    mt5_login = os.getenv("MT5_LOGIN", "")
    mt5_server = os.getenv("MT5_SERVER", "")
    mt5_path = os.getenv("MT5_PATH", "")

    if not mt5_login:
        return CheckItem(
            name="MT5 Connection",
            passed=False,
            message="MT5_LOGIN not set in .env",
            category="mt5",
        )

    try:
        init_path = mt5_path or None
        if not mt5.initialize(path=init_path):
            err = mt5.last_error()
            return CheckItem(
                name="MT5 Connection",
                passed=False,
                message=f"MT5 init failed: {err}. Is the terminal running?",
                category="mt5",
            )

        info = mt5.account_info()
        mt5.shutdown()

        if info is None:
            return CheckItem(
                name="MT5 Connection",
                passed=False,
                message="MT5 account_info() returned None",
                category="mt5",
            )

        return CheckItem(
            name="MT5 Connection",
            passed=True,
            message=f"Connected: {info.name} ({info.server}) balance=${info.balance:.2f}",
            category="mt5",
        )
    except Exception as e:
        return CheckItem(
            name="MT5 Connection",
            passed=False,
            message=f"MT5 error: {e}",
            category="mt5",
        )


def check_data_pipeline() -> CheckItem:
    """Check that data pipeline script exists and data files are present."""
    pipeline_path = SCRIPT_DIR / "data_pipeline.py"
    if not pipeline_path.exists():
        return CheckItem(
            name="Data Pipeline",
            passed=False,
            message=f"Data pipeline not found at {pipeline_path}",
            category="data",
        )

    # Check for existing data files
    target_symbols = ["XAUUSD", "EURUSD", "BTCUSD", "ETHUSD"]
    existing = 0
    missing = []
    for sym in target_symbols:
        # Check M15 (primary timeframe) and D1
        for tf in ["M15", "D1"]:
            path = DATA_DIR / f"{sym}_{tf}.csv"
            if path.exists():
                existing += 1
            else:
                missing.append(f"{sym}_{tf}")

    if existing == 0:
        return CheckItem(
            name="Data Pipeline",
            passed=False,
            message=f"No data files found. Missing: {', '.join(missing[:4])}... Run: python scripts/data_pipeline.py pull --all",
            category="data",
        )

    return CheckItem(
        name="Data Pipeline",
        passed=True,
        message=f"Pipeline available, {existing} data files present ({len(missing)} missing)",
        category="data",
        severity="recommended" if existing >= 4 else "required",
    )


def check_models_trained() -> CheckItem:
    """Check that ML models exist and are recent."""
    model_dirs = [
        ML_MODELS_DIR,
        ARTIFACTS_DIR / "strategy_model",
        ARTIFACTS_DIR / "features_v2",
    ]

    found_models = 0
    latest_mtime = 0.0
    for d in model_dirs:
        if d.exists():
            for f in d.iterdir():
                if f.suffix in (".pkl", ".joblib", ".pt", ".onnx", ".h5", ".json"):
                    found_models += 1
                    mt = f.stat().st_mtime
                    if mt > latest_mtime:
                        latest_mtime = mt

    if found_models == 0:
        return CheckItem(
            name="Models Trained",
            passed=False,
            message="No model files found in ml/models/ or artifacts/. Run: python scripts/train_all_models.py",
            category="models",
        )

    age_days = (datetime.now().timestamp() - latest_mtime) / 86400 if latest_mtime > 0 else 999
    severity = "required" if age_days > 30 else "recommended"

    return CheckItem(
        name="Models Trained",
        passed=found_models > 0,
        message=f"{found_models} model files found, newest {age_days:.0f} days old",
        category="models",
        severity=severity,
    )


def check_risk_limits_configured() -> CheckItem:
    """Verify risk limits are configured in config or .env."""
    from core.golden_rules import validate_golden_rules

    golden_checks = validate_golden_rules()
    if not golden_checks["all_checks_passed"]:
        failed = [k for k, v in golden_checks.items() if not v and k != "all_checks_passed"]
        return CheckItem(
            name="Risk Limits",
            passed=False,
            message=f"Golden rules validation failed: {', '.join(failed)}",
            category="risk",
        )

    # Check paper trade config exists
    if CONFIG_PATH.exists():
        with open(CONFIG_PATH) as f:
            config = json.load(f)
        risk = config.get("risk", {})
        return CheckItem(
            name="Risk Limits",
            passed=True,
            message=f"Configured: risk/trade={risk.get('max_risk_per_trade_pct', 1.0)}% "
                    f"daily={risk.get('max_daily_loss_pct', 2.0)}% "
                    f"dd={risk.get('max_drawdown_pct', 10.0)}% "
                    f"capital=${risk.get('initial_capital', 10000):,.0f}",
            category="risk",
        )

    return CheckItem(
        name="Risk Limits",
        passed=False,
        message="paper_trade_config.json not found. Run: python scripts/paper_trade_config.py",
        category="risk",
    )


def check_monitoring_active() -> CheckItem:
    """Check that monitoring scripts and state exist."""
    monitor_script = SCRIPT_DIR / "monitor_paper_trades.py"
    if not monitor_script.exists():
        return CheckItem(
            name="Monitoring",
            passed=False,
            message="monitor_paper_trades.py not found",
            category="monitoring",
        )

    state_path = PROJECT_ROOT / "data" / "monitor_state.json"
    if state_path.exists():
        with open(state_path) as f:
            state = json.load(f)
        last = state.get("last_check", "never")
        return CheckItem(
            name="Monitoring",
            passed=True,
            message=f"Monitor active, last check: {last}",
            category="monitoring",
        )

    return CheckItem(
        name="Monitoring",
        passed=True,
        message="Monitor script available (not yet run)",
        category="monitoring",
    )


def check_news_filter() -> CheckItem:
    """Check that news events module is available."""
    news_dir = PROJECT_ROOT / "news_events"
    if not news_dir.exists():
        return CheckItem(
            name="News Filter",
            passed=False,
            message="news_events/ module not found",
            category="news",
        )

    required_files = ["event_models.py", "event_risk_gate.py", "event_store.py"]
    missing = [f for f in required_files if not (news_dir / f).exists()]
    if missing:
        return CheckItem(
            name="News Filter",
            passed=False,
            message=f"Missing news_events files: {', '.join(missing)}",
            category="news",
        )

    return CheckItem(
        name="News Filter",
        passed=True,
        message="News events module available (event_models, event_risk_gate, event_store)",
        category="news",
    )


def check_trading_hours() -> CheckItem:
    """Verify symbol trading hours are configured."""
    if not CONFIG_PATH.exists():
        return CheckItem(
            name="Trading Hours",
            passed=False,
            message="No paper_trade_config.json with trading hours",
            category="schedule",
        )

    with open(CONFIG_PATH) as f:
        config = json.load(f)
    symbols = config.get("symbols", [])
    if not symbols:
        return CheckItem(
            name="Trading Hours",
            passed=False,
            message="No symbols configured in paper_trade_config.json",
            category="schedule",
        )

    hours_info = [f"{s['symbol']}={s.get('trading_hours_utc', {})}" for s in symbols[:4]]
    return CheckItem(
        name="Trading Hours",
        passed=True,
        message=f"Trading hours for {len(symbols)} symbols: {'; '.join(hours_info)}",
        category="schedule",
    )


def check_telegram_alerts() -> CheckItem:
    """Check Telegram bot configuration."""
    import tomllib as _tomllib
    telegram_config = PROJECT_ROOT / "scripts" / "telegram_config.toml"
    if not telegram_config.exists():
        return CheckItem(
            name="Telegram Alerts",
            passed=False,
            message="telegram_config.toml not found",
            category="alerts",
            severity="recommended",
        )

    try:
        with open(telegram_config, "rb") as f:
            cfg = _tomllib.load(f)
        token = cfg.get("bot_token", "")
        if not token or token == "YOUR_BOT_TOKEN":
            return CheckItem(
                name="Telegram Alerts",
                passed=False,
                message="Telegram bot_token not configured",
                category="alerts",
                severity="recommended",
            )
        return CheckItem(
            name="Telegram Alerts",
            passed=True,
            message="Telegram configured (bot_token present)",
            category="alerts",
        )
    except Exception as e:
        return CheckItem(
            name="Telegram Alerts",
            passed=False,
            message=f"Telegram config error: {e}",
            category="alerts",
            severity="recommended",
        )


def check_environment() -> CheckItem:
    """Check Python environment has required packages."""
    required = ["pandas", "numpy", "requests"]
    missing = []
    for pkg in required:
        try:
            __import__(pkg)
        except ImportError:
            missing.append(pkg)

    if missing:
        return CheckItem(
            name="Python Environment",
            passed=False,
            message=f"Missing packages: {', '.join(missing)}. Run: pip install {' '.join(missing)}",
            category="environment",
        )

    return CheckItem(
        name="Python Environment",
        passed=True,
        message=f"All {len(required)} required packages available",
        category="environment",
    )


# ── Run all checks ───────────────────────────────────────────────────

def run_checklist() -> ChecklistResult:
    """Run all prerequisite checks and return structured result."""
    checks = [
        check_environment(),
        check_mt5_connection(),
        check_data_pipeline(),
        check_models_trained(),
        check_risk_limits_configured(),
        check_monitoring_active(),
        check_news_filter(),
        check_trading_hours(),
        check_telegram_alerts(),
    ]

    items = [asdict(c) for c in checks]
    required_failed = [c for c in checks if not c.passed and c.severity == "required"]
    overall_pass = len(required_failed) == 0

    summary = {
        "total": len(checks),
        "passed": sum(1 for c in checks if c.passed),
        "failed": sum(1 for c in checks if not c.passed),
        "required_failed": len(required_failed),
    }

    return ChecklistResult(
        timestamp=datetime.now(UTC).isoformat(),
        overall_pass=overall_pass,
        items=items,
        summary=summary,
    )


def save_result(result: ChecklistResult) -> Path:
    """Save checklist result to JSON."""
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    out_path = REPORTS_DIR / "paper_trade_readiness.json"
    with open(out_path, "w") as f:
        json.dump(asdict(result), f, indent=2)
    return out_path


def print_result(result: ChecklistResult, verbose: bool = False) -> None:
    """Print human-readable checklist."""
    print(f"\n{'='*60}")
    print("PAPER TRADE READINESS CHECKLIST")
    print(f"{'='*60}")
    print(f"Time: {result.timestamp}")
    print(f"Overall: {'PASS' if result.overall_pass else 'FAIL'}")
    print(f"{'='*60}\n")

    current_cat = ""
    for item in result.items:
        if verbose or not item["passed"]:
            if item["category"] != current_cat:
                current_cat = item["category"]
                print(f"  [{current_cat.upper()}]")
            status = "PASS" if item["passed"] else "FAIL"
            print(f"    {status} {item['name']}: {item['message']}")

    s = result.summary
    print(f"\n{'='*60}")
    print(f"SUMMARY: {s['passed']}/{s['total']} passed, {s['required_failed']} required failures")
    print(f"{'='*60}\n")


# ── CLI ───────────────────────────────────────────────────────────────

def main() -> int:
    parser = argparse.ArgumentParser(description="Paper trade readiness checklist")
    parser.add_argument("--verbose", "-v", action="store_true", help="Show all items including passed")
    args = parser.parse_args()

    result = run_checklist()
    out_path = save_result(result)
    print_result(result, verbose=args.verbose)
    print(f"Report saved: {out_path}")

    return 0 if result.overall_pass else 1


if __name__ == "__main__":
    sys.exit(main())
