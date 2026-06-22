"""Phase 9 — Evidence pack builder. Aggregates all pre-live evidence into a single verifiable bundle."""
import json
import os
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path


@dataclass
class EvidencePack:
    """Structured evidence bundle for Phase 9 review."""
    backtest_results: dict = field(default_factory=dict)
    demo_campaign: dict = field(default_factory=dict)
    drill_results: list = field(default_factory=list)
    risk_policy: dict = field(default_factory=dict)
    release_gate: dict = field(default_factory=dict)
    canary_config: dict = field(default_factory=dict)
    micro_live_policy: dict = field(default_factory=dict)
    built_at: str = field(default_factory=lambda: datetime.utcnow().isoformat())

    def to_dict(self) -> dict:
        return {
            "backtest_results": self.backtest_results,
            "demo_campaign": self.demo_campaign,
            "drill_results": self.drill_results,
            "risk_policy": self.risk_policy,
            "release_gate": self.release_gate,
            "canary_config": self.canary_config,
            "micro_live_policy": self.micro_live_policy,
            "built_at": self.built_at,
        }


class EvidencePackBuilder:
    """Builds an evidence pack from existing project artifacts."""
    PROJECT_ROOT = Path(__file__).resolve().parent.parent

    def build(self) -> EvidencePack:
        pack = EvidencePack()
        pack.backtest_results = self._load_json("results/backtest_results.json")
        pack.drill_results = self._load_latest_drills()
        pack.release_gate = self._load_json("artifacts/release_gate/summary.json")
        pack.risk_policy = self._load_risk_policy()
        pack.canary_config = self._load_canary_config()
        pack.micro_live_policy = self._load_micro_live_policy()
        pack.demo_campaign = self._load_demo_campaign()
        return pack

    def _load_json(self, rel_path: str) -> dict:
        path = self.PROJECT_ROOT / rel_path
        if not path.exists():
            return {"error": f"File not found: {rel_path}"}
        with open(path) as f:
            return json.load(f)

    def _load_latest_drills(self) -> list:
        drills_dir = self.PROJECT_ROOT / "shadow_results"
        drill_files = sorted(drills_dir.glob("drills_*.json"), reverse=True)
        if not drill_files:
            return []
        with open(drill_files[0]) as f:
            return json.load(f)

    def _load_risk_policy(self) -> dict:
        try:
            rp_path = self.PROJECT_ROOT / "risk" / "risk_policy.py"
            with open(rp_path) as f:
                content = f.read()
            import re
            values = {}
            for field in ["risk_per_trade_bps", "max_daily_loss_bps", "max_weekly_loss_bps",
                          "max_total_drawdown_bps", "max_open_positions", "max_orders_per_day"]:
                m = re.search(rf"{field}:\s*int\s*=\s*(\d+)", content)
                if m:
                    values[field] = int(m.group(1))
            for field in ["require_stop_loss", "fail_closed"]:
                m = re.search(rf"{field}:\s*bool\s*=\s*(True|False)", content)
                if m:
                    values[field] = m.group(1) == "True"
            return values
        except Exception as e:
            return {"error": str(e)}

    def _load_canary_config(self) -> dict:
        try:
            from canary.config import CanaryConfig
            cc = CanaryConfig()
            valid, issues = cc.validate()
            return {
                "execution_enabled": cc.execution_enabled,
                "account_mode_required": cc.account_mode_required,
                "allowed_symbols": cc.allowed_symbols,
                "allowed_strategies": cc.allowed_strategies,
                "max_open_positions": cc.max_open_positions,
                "risk_per_trade_bps": cc.risk_per_trade_bps,
                "auto_resume_after_kill_switch": cc.auto_resume_after_kill_switch,
                "validate_passed": valid,
                "validate_issues": issues,
            }
        except ImportError:
            return {"error": "CanaryConfig not importable"}

    def _load_micro_live_policy(self) -> dict:
        try:
            from canary.micro_live_policy import MicroLivePolicy
            ml = MicroLivePolicy()
            valid, issues = ml.validate()
            return {
                "max_symbols": ml.max_symbols,
                "max_open_positions": ml.max_open_positions,
                "max_orders_per_day": ml.max_orders_per_day,
                "risk_per_trade_bps": ml.risk_per_trade_bps,
                "max_daily_loss_bps": ml.max_daily_loss_bps,
                "max_weekly_loss_bps": ml.max_weekly_loss_bps,
                "max_total_drawdown_bps": ml.max_total_drawdown_bps,
                "no_compounding": ml.no_compounding,
                "emergency_kill_switch": ml.emergency_kill_switch,
                "validate_passed": valid,
                "validate_issues": issues,
            }
        except ImportError:
            return {"error": "MicroLivePolicy not importable"}

    def _load_demo_campaign(self) -> dict:
        results_dir = self.PROJECT_ROOT / "shadow_results"
        campaign_files = sorted(results_dir.glob("campaign_*.json"), reverse=True)
        if campaign_files:
            with open(campaign_files[0]) as f:
                return json.load(f)
        sessions = sorted(results_dir.glob("session_*.json"), reverse=True)
        if sessions:
            with open(sessions[0]) as f:
                return json.load(f)
        return {"status": "no_campaign_data"}
