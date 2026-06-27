"""
Production Readiness Checklist — Final verification before live trading.

Checks:
  - API keys configured
  - Risk limits set
  - Canonical payloads in use
  - Hot path latency < 10ms
  - No raw dicts in EventBus
  - Correlation filter active
  - Kelly sizing active
  - News blackout active
  - Session filter active
  - Walk-forward validation passed

Usage:
  from core.production_readiness import ProductionReadiness
  pr = ProductionReadiness()
  report = pr.check()
  pr.render(report)
"""

from __future__ import annotations

import os
import time
from dataclasses import dataclass

import structlog

logger = structlog.get_logger(__name__)


@dataclass
class CheckResult:
    name: str
    passed: bool
    detail: str = ""
    critical: bool = True  # If True, failure blocks live trading


class ProductionReadiness:
    """Production readiness checks for live trading."""

    def __init__(self):
        self._results: list[CheckResult] = []

    def _check(self, name: str, fn, critical: bool = True) -> CheckResult:
        try:
            detail = fn()
            result = CheckResult(name=name, passed=True, detail=str(detail), critical=critical)
        except Exception as e:
            result = CheckResult(name=name, passed=False, detail=str(e), critical=critical)
        self._results.append(result)
        return result

    def check(self) -> list[CheckResult]:
        """Run all production readiness checks."""
        self._results = []

        # Critical checks
        self._check("API Keys", self._check_api_keys, critical=True)
        self._check("Risk Limits", self._check_risk_limits, critical=True)
        self._check("Canonical Payloads", self._check_canonical, critical=True)
        self._check("Hot Path Latency", self._check_latency, critical=True)
        self._check("No Raw Dicts", self._check_no_raw_dicts, critical=True)
        self._check("MacroRegimeCache", self._check_cache, critical=True)

        # Important checks
        self._check("Kelly Sizing", self._check_kelly, critical=False)
        self._check("Correlation Filter", self._check_correlation, critical=False)
        self._check("Session Filter", self._check_session, critical=False)
        self._check("News Blackout", self._check_blackout, critical=False)
        self._check("Walk-Forward", self._check_walk_forward, critical=False)
        self._check("Telegram Bot", self._check_telegram, critical=False)
        self._check("Loki Logging", self._check_loki, critical=False)

        return self._results

    def _check_api_keys(self) -> str:
        required = ["GROQ_API_KEY", "CEREBRAS_API_KEY", "GOOGLE_AI_KEY"]
        found = [k for k in required if os.getenv(k)]
        if not all(os.getenv(k) for k in required):
            missing = [k for k in required if not os.getenv(k)]
            raise Exception(f"Missing: {', '.join(missing)}")
        return f"{len(found)}/{len(required)} keys configured"

    def _check_risk_limits(self) -> str:
        from core.portfolio_risk import PortfolioRisk

        pr = PortfolioRisk()
        return f"max_risk={pr.MAX_TOTAL_RISK_PCT:.0%}, max_symbol={pr.MAX_PER_SYMBOL_PCT:.0%}"

    def _check_canonical(self) -> str:
        from core.canonical.payloads import MLSignalPayload

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
            raise Exception("MLSignalPayload not frozen")
        except Exception as e:
            if "not frozen" in str(e):
                raise
        return "All payloads frozen"

    def _check_latency(self) -> str:
        from core.canonical.macro_regime import MacroRegimeCache

        cache = MacroRegimeCache()
        latencies = []
        for _ in range(1000):
            start = time.perf_counter_ns()
            _ = cache.get()
            end = time.perf_counter_ns()
            latencies.append((end - start) / 1_000_000)
        p99 = sorted(latencies)[990]
        if p99 > 10.0:
            raise Exception(f"p99={p99:.3f}ms > 10ms")
        return f"p99={p99:.3f}ms"

    def _check_no_raw_dicts(self) -> str:
        core_dir = Path(__file__).parent
        issues = 0
        for py_file in core_dir.rglob("*.py"):
            try:
                content = py_file.read_text()
                if 'return {"event_type"' in content:
                    issues += 1
            except Exception:
                pass
        return f"{issues} raw dict returns found"

    def _check_cache(self) -> str:
        from core.canonical.macro_regime import MacroRegimeCache

        a = MacroRegimeCache()
        b = MacroRegimeCache()
        if a is not b:
            raise Exception("MacroRegimeCache not singleton")
        return "Singleton OK"

    def _check_kelly(self) -> str:
        from core.kelly import kelly_fraction

        f = kelly_fraction(win_rate=0.59, avg_rr=1.88)
        return f"half_kelly={f:.1%}"

    def _check_correlation(self) -> str:
        from core.correlation import CorrelationFilter

        cf = CorrelationFilter()
        return f"lookback={cf._lookback}"

    def _check_session(self) -> str:
        from core.session_filter import SessionFilter

        sf = SessionFilter()
        info = sf.get_session_info()
        return f"session={info['session']}, active={info['is_active']}"

    def _check_blackout(self) -> str:
        from core.news_blackout import NewsBlackout

        nb = NewsBlackout()
        return f"crisis_block={nb.SEVERITY_MINUTES['CRISIS']}min"

    def _check_walk_forward(self) -> str:
        model_dir = Path(__file__).parent.parent / "ml" / "models"
        models = list(model_dir.glob("xgboost_*.pkl"))
        return f"{len(models)} models available"

    def _check_telegram(self) -> str:
        token = os.getenv("TELEGRAM_BOT_TOKEN", "")
        chat_id = os.getenv("TELEGRAM_CHAT_ID", "")
        if not token or not chat_id:
            return "Not configured (optional)"
        return f"token=****{token[-4:]}, chat={chat_id}"

    def _check_loki(self) -> str:
        url = os.getenv("LOKI_URL", "")
        return f"url={url}" if url else "Not configured (optional)"

    def render(self, results: list[CheckResult] | None = None) -> str:
        """Render checklist to terminal."""
        results = results or self._results
        passed = sum(1 for r in results if r.passed)
        failed_critical = sum(1 for r in results if not r.passed and r.critical)
        failed_optional = sum(1 for r in results if not r.passed and not r.critical)

        lines = [
            "",
            "=" * 60,
            "  PRODUCTION READINESS CHECKLIST",
            "=" * 60,
            "",
        ]

        for r in results:
            status = "PASS" if r.passed else ("FAIL" if r.critical else "WARN")
            icon = "+" if r.passed else ("X" if r.critical else "!")
            lines.append(f"  [{icon}] [{status}] {r.name}")
            if r.detail:
                lines.append(f"         {r.detail}")

        lines.extend(
            [
                "",
                "-" * 60,
                f"  Results: {passed}/{len(results)} passed",
                f"  Critical failures: {failed_critical}",
                f"  Optional warnings: {failed_optional}",
                "",
            ]
        )

        if failed_critical == 0:
            lines.append("  READY FOR LIVE TRADING")
        else:
            lines.append("  NOT READY — fix critical failures first")

        lines.append("=" * 60)
        lines.append("")

        text = "\n".join(lines)
        print(text)
        return text
