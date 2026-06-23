"""Demo canary preflight. Read-only. Never submits order."""
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Callable, Optional
import hashlib, json, logging

from execution.demo_canary.preflight_guards import (
    g01_feature_gate_off, g02_terminal_health,
    g03_demo_account, g04_profile_identity,
    g05_terminal_path, g06_symbol_identity,
    g07_contract_freshness, g08_market_status,
    g09_canonical_tick, g10_tick_ordering,
    g11_spread_gate, g12_event_gate,
    g13_session_gate, g14_position_gate,
    g15_pending_order_gate, g16_volume_gate,
    g17_geometry_gate, g18_stops_freeze_level,
    g19_margin_estimate, g20_order_check,
    g21_kill_switch, g22_approval_precondition,
    g23_evidence_writer_available, g24_mutex_available,
    g25_legacy_separation, g26_time_to_submit,
)
from execution.demo_canary.approval_payload import ApprovalPayload
from risk.contract_spec import ContractSpecResolver

logger = logging.getLogger(__name__)

@dataclass(frozen=True)
class PreflightVerdict:
    passed: bool
    guards_passed: int = 0
    guards_total: int = 0
    first_failure_reason: str = ""
    preflight_hash: str = ""
    generated_at_utc: str = ""

class DemoCanaryPreflight:
    def __init__(self, mt5=None, spec_resolver=None, evidence_writer=None):
        self._mt5 = mt5
        self._spec_resolver = spec_resolver or ContractSpecResolver(mt5)
        self._evidence_writer = evidence_writer
        self._guard_results = []

    def run(self, plan, approval: Optional[ApprovalPayload] = None, bundle_created_utc: Optional[datetime] = None) -> PreflightVerdict:
        self._guard_results = []

        def _entry():
            if self._mt5 is None:
                return 0.0
            t = self._mt5.symbol_info_tick("XAUUSD")
            return t.ask if t else 0.0

        vol = float(plan.volume)
        sl = float(plan.stop_loss)
        tp = float(plan.take_profit)
        entry = _entry()

        guards = [
            ("P01_feature_gate_off", lambda: g01_feature_gate_off(self._mt5)),
            ("P02_terminal_health", lambda: g02_terminal_health(self._mt5)),
            ("P03_demo_account", lambda: g03_demo_account(self._mt5)),
            ("P04_profile_identity", lambda: g04_profile_identity(self._mt5)),
            ("P05_terminal_path", lambda: g05_terminal_path(self._mt5)),
            ("P06_symbol_identity", lambda: g06_symbol_identity(self._mt5)),
            ("P07_contract_freshness", lambda: g07_contract_freshness(self._mt5, self._spec_resolver)),
            ("P08_market_status", lambda: g08_market_status(self._mt5)),
            ("P09_canonical_tick", lambda: g09_canonical_tick(self._mt5)),
            ("P10_tick_ordering", lambda: g10_tick_ordering(self._mt5)),
            ("P11_spread_gate", lambda: g11_spread_gate(self._mt5)),
            ("P12_event_gate", lambda: g12_event_gate(self._mt5)),
            ("P13_session_gate", lambda: g13_session_gate(self._mt5)),
            ("P14_position_gate", lambda: g14_position_gate(self._mt5)),
            ("P15_pending_order_gate", lambda: g15_pending_order_gate(self._mt5)),
            ("P16_volume_gate", lambda: g16_volume_gate(self._mt5, vol, self._spec_resolver)),
            ("P17_geometry_gate", lambda: g17_geometry_gate(self._mt5, plan.side, entry, sl, tp, self._spec_resolver)),
            ("P18_stops_freeze_level", lambda: g18_stops_freeze_level(self._mt5, self._spec_resolver)),
            ("P19_margin_estimate", lambda: g19_margin_estimate(self._mt5, vol, entry)),
            ("P20_order_check", lambda: g20_order_check(self._mt5, vol, entry, sl, tp)),
            ("P21_kill_switch", lambda: g21_kill_switch(self._mt5)),
            ("P22_approval_precondition", lambda: g22_approval_precondition(self._mt5, approval)),
            ("P23_evidence_writer_available", lambda: g23_evidence_writer_available(self._mt5, self._evidence_writer)),
            ("P24_mutex_available", lambda: g24_mutex_available(self._mt5)),
            ("P25_legacy_separation", lambda: g25_legacy_separation(self._mt5)),
            ("P26_time_to_submit", lambda: g26_time_to_submit(self._mt5, bundle_created_utc)),
        ]

        passed_count = 0
        first_failure = ""
        for name, fn in guards:
            ok, reason = fn()
            self._guard_results.append((name, ok, reason))
            if ok:
                passed_count += 1
            elif not first_failure:
                first_failure = f"{name}: {reason}"

        return PreflightVerdict(
            passed=not bool(first_failure),
            guards_passed=passed_count,
            guards_total=len(guards),
            first_failure_reason=first_failure,
            preflight_hash=self._compute_hash(),
            generated_at_utc=datetime.now(timezone.utc).isoformat(),
        )

    def _compute_hash(self) -> str:
        raw = json.dumps([(n, p, r) for n, p, r in self._guard_results], sort_keys=True, default=str)
        return hashlib.sha256(raw.encode()).hexdigest()

    def to_artifact(self) -> dict:
        return {
            "guard_results": [
                {"name": n, "passed": p, "reason": r}
                for n, p, r in self._guard_results
            ],
            "verdict": {
                "passed": all(p for _, p, _ in self._guard_results),
                "guards_passed": sum(1 for _, p, _ in self._guard_results if p),
                "guards_total": len(self._guard_results),
            },
        }
