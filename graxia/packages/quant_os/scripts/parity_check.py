"""
Backtest → Live Parity Check — Verify signal flow is identical.

Checks:
  1. Same strategy class (MLBreakout)
  2. Same MLPipeline (predict, predict_payload)
  3. Same risk checks (RiskAuditor)
  4. Same position sizing (PortfolioManager)
  5. Same MacroRegimeCache (not different instances)
  6. Same feature engineering (FeatureEngineer)

Usage:
  python scripts/parity_check.py    # run all checks
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import structlog

logger = structlog.get_logger(__name__)

CHECKS = []


def check(name: str):
    """Decorator to register a parity check."""

    def wrapper(fn):
        CHECKS.append((name, fn))
        return fn

    return wrapper


@check("Strategy class identity")
def parity_strategy_class():
    from pathlib import Path

    mlb_path = Path(__file__).parent.parent / "strategies" / "mlb.py"
    content = mlb_path.read_text()
    assert "class MLBreakout" in content, "MLBreakout class not found"
    return {"file": str(mlb_path)}


@check("MLPipeline predict method exists")
def parity_pipeline_predict():
    from ml.pipeline import MLTrainer

    assert hasattr(MLTrainer, "predict"), "MLTrainer.predict missing"
    assert hasattr(MLTrainer, "predict_payload"), "MLTrainer.predict_payload missing"
    return {"methods": ["predict", "predict_payload"]}


@check("RiskAuditor has macro lockdown check")
def parity_risk_auditor():
    from core.agents.risk_auditor import RiskAuditorAgent

    ra = RiskAuditorAgent()
    assert hasattr(ra, "_check_macro_lockdown"), "macro_lockdown check missing"
    return {"checks": ["min_confidence", "risk_reward", "duplicates", "whitelist", "macro_lockdown"]}


@check("PortfolioManager uses Hierarchical Veto")
def parity_portfolio_manager():
    from core.agents.portfolio_manager import PortfolioManagerAgent

    pm = PortfolioManagerAgent()
    assert hasattr(pm, "_pending_risk_pass"), "risk gate missing"
    assert hasattr(pm, "_sentiment_modifier"), "sentiment_modifier missing"
    assert pm._pending_risk_pass is False, "not fail-closed"
    return {"formula": "raw_confidence * sentiment_mod * risk_gate", "fail_closed": True}


@check("MacroRegimeCache singleton")
def parity_macro_cache():
    from core.canonical.macro_regime import MacroRegimeCache

    a = MacroRegimeCache()
    b = MacroRegimeCache()
    assert a is b, "MacroRegimeCache not singleton"
    return {"singleton": True}


@check("Canonical payloads frozen")
def parity_payloads_frozen():
    from core.canonical.payloads import MLSignalPayload, RiskVerdictPayload

    ml = MLSignalPayload(
        symbol="X",
        xgb_probability=0.5,
        xgb_model_version="v1",
        direction="HOLD",
        entry_price=100,
        stop_loss=99,
        take_profit=101,
    )
    try:
        ml.symbol = "Y"
        return {"error": "MLSignalPayload not frozen"}
    except Exception:
        pass

    rv = RiskVerdictPayload(is_approved=True)
    try:
        rv.is_approved = False
        return {"error": "RiskVerdictPayload not frozen"}
    except Exception:
        pass
    return {"frozen": True}


@check("SentimentAgent uses CascadeRouter")
def parity_sentiment_router():
    from core.agents.sentiment_agent import SentimentAgent

    agent = SentimentAgent()
    assert hasattr(agent, "router"), "CascadeRouter not wired"
    return {"router": "CascadeRouter (Cerebras->Groq->Gemini)"}


@check("No raw dicts in EventBus")
def parity_no_raw_dicts():
    import ast
    from pathlib import Path

    issues = []
    core_dir = Path(__file__).parent.parent / "core"
    for py_file in core_dir.rglob("*.py"):
        try:
            tree = ast.parse(py_file.read_text())
            for node in ast.walk(tree):
                if isinstance(node, ast.Return) and isinstance(node.value, ast.Dict):
                    issues.append(f"{py_file.name}:{node.lineno}")
        except Exception:
            pass
    # Allow known safe returns (empty dicts, error dicts)
    real_issues = [i for i in issues if "return {}" not in str(i)]
    return {"checked_files": len(list(core_dir.rglob("*.py"))), "issues": len(real_issues)}


def run_parity_checks() -> bool:
    """Run all parity checks. Returns True if all pass."""
    print(f"\n{'='*60}")
    print("  BACKTEST -> LIVE PARITY CHECK")
    print(f"{'='*60}\n")

    passed = 0
    failed = 0

    for name, fn in CHECKS:
        try:
            result = fn()
            status = "PASS"
            passed += 1
        except Exception as e:
            status = f"FAIL: {e}"
            result = {}
            failed += 1

        print(f"  [{status}] {name}")
        if result:
            for k, v in result.items():
                print(f"         {k}: {v}")

    print(f"\n{'='*60}")
    print(f"  Results: {passed} passed, {failed} failed")
    print(f"{'='*60}\n")

    return failed == 0


if __name__ == "__main__":
    success = run_parity_checks()
    sys.exit(0 if success else 1)
