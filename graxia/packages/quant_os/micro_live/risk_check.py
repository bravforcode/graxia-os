"""Phase 9 — Risk policy verifier. Checks all risk constraints before micro-live promotion."""
from dataclasses import dataclass, field


@dataclass
class RiskVerification:
    """Result of risk policy verification."""
    micro_live_policy_valid: bool = False
    canary_config_valid: bool = False
    risk_budgets_ok: bool = False
    kill_switch_present: bool = False
    no_auto_resume: bool = False
    single_symbol_only: bool = False
    single_position_only: bool = False
    no_compounding: bool = False
    issues: list = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "micro_live_policy_valid": self.micro_live_policy_valid,
            "canary_config_valid": self.canary_config_valid,
            "risk_budgets_ok": self.risk_budgets_ok,
            "kill_switch_present": self.kill_switch_present,
            "no_auto_resume": self.no_auto_resume,
            "single_symbol_only": self.single_symbol_only,
            "single_position_only": self.single_position_only,
            "no_compounding": self.no_compounding,
            "all_passed": all([
                self.micro_live_policy_valid,
                self.canary_config_valid,
                self.risk_budgets_ok,
                self.kill_switch_present,
                self.no_auto_resume,
                self.single_symbol_only,
                self.single_position_only,
                self.no_compounding,
            ]),
            "issues": self.issues,
        }


class RiskPolicyVerifier:
    """Verifies all risk policies pass before micro-live promotion."""

    def verify(self) -> RiskVerification:
        result = RiskVerification()
        self._check_micro_live_policy(result)
        self._check_canary_config(result)
        self._check_risk_budgets(result)
        return result

    def _check_micro_live_policy(self, result: RiskVerification):
        try:
            import sys
            from pathlib import Path
            sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
            from canary.micro_live_policy import MicroLivePolicy
            ml = MicroLivePolicy()
            valid, issues = ml.validate()
            result.micro_live_policy_valid = valid
            result.kill_switch_present = ml.emergency_kill_switch
            result.no_compounding = ml.no_compounding
            result.single_symbol_only = ml.max_symbols == 1
            result.single_position_only = ml.max_open_positions == 1
            if not valid:
                result.issues.extend([f"MICRO_LIVE_POLICY: {i}" for i in issues])
        except ImportError:
            result.issues.append("MicroLivePolicy not importable")

    def _check_canary_config(self, result: RiskVerification):
        try:
            import sys
            from pathlib import Path
            sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
            from canary.config import CanaryConfig
            cc = CanaryConfig()
            valid, issues = cc.validate()
            result.canary_config_valid = valid
            result.no_auto_resume = not cc.auto_resume_after_kill_switch
            if not valid:
                result.issues.extend([f"CANARY_CONFIG: {i}" for i in issues])
        except ImportError:
            result.issues.append("CanaryConfig not importable")

    def _check_risk_budgets(self, result: RiskVerification):
        try:
            import re
            from pathlib import Path
            rp_path = Path(__file__).resolve().parent.parent / "risk" / "risk_policy.py"
            with open(rp_path) as f:
                content = f.read()
            values = {}
            for field in ["risk_per_trade_bps", "max_daily_loss_bps", "max_weekly_loss_bps", "max_total_drawdown_bps"]:
                m = re.search(rf"{field}:\s*int\s*=\s*(\d+)", content)
                if m:
                    values[field] = int(m.group(1))
            ok = (
                values.get("risk_per_trade_bps", 999) <= 5
                and values.get("max_daily_loss_bps", 999) <= 20
                and values.get("max_weekly_loss_bps", 999) <= 50
                and values.get("max_total_drawdown_bps", 999) <= 100
            )
            result.risk_budgets_ok = ok
            if not ok:
                result.issues.append(
                    f"RISK_BUDGETS: trade={values.get('risk_per_trade_bps')}bps "
                    f"daily={values.get('max_daily_loss_bps')}bps "
                    f"weekly={values.get('max_weekly_loss_bps')}bps "
                    f"dd={values.get('max_total_drawdown_bps')}bps"
                )
        except Exception as e:
            result.issues.append(f"RiskPolicy read error: {e}")
