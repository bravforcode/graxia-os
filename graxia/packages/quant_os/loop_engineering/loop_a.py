"""
loop_a.py — LOOP A: Research Loop (Spec Part 1, 3).

Entry point for testing a NEW hypothesis. Terminal is "verified report", NEVER
auto-deploy. Sequence (Spec Part 3 safe diagram):

  pre-register -> check zombie (read registry+provenance) -> check is_stopped
    -> backtest -> DK-test
       - fail: log REJECT, update consecutive_fail, maybe is_stopped
       - pass: label-shuffle -> min-trades -> verify 3 layers
           - fail any: log REJECT
           - all pass: log "candidate"  -> HUMAN GATE 7 (holdout) -> [if approved]
               sacred holdout (one-time) -> HUMAN GATE 10 (paper/live)

Hard gates (steps 7 & 10) BLOCK automatically. The loop never opens the holdout
or deploys without an explicit HumanDecision.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from .gates import GateState, HumanDecision, human_gate_step7, human_gate_step10
from .ledger import (
    STATUS_APPROVED_FOR_PAPER,
    STATUS_CANDIDATE,
    STATUS_HOLDOUT_FAIL,
    STATUS_HOLDOUT_PASS,
    STATUS_REJECTED,
    LedgerEntry,
    WorkingLedger,
)
from .pre_register import PreRegistration
from .registry import check_provenance, is_zombie
from .validation import (
    CandidateGates,
    ValidationAdapters,
    VerificationResult,
    VerificationThresholds,
    verify_candidate_gates,
    verify_three_layer,
)


@dataclass
class LoopAResult:
    trial_number: int
    status: str
    gate_reached: str
    gate_state: GateState = GateState.CLEARED
    verification: VerificationResult | None = None
    stopped: bool = False
    zombie: bool = False
    provenance_status: str = ""
    note: str = ""


def _today(today: str | None) -> str:
    return today or datetime.now(UTC).isoformat()[:10]


def run_research_loop(
    pre_reg: PreRegistration,
    adapters: ValidationAdapters,
    ledger: WorkingLedger,
    registry: dict[str, Any],
    provenance_path: str | Path,
    human_decision_step7: HumanDecision | None = None,
    human_decision_step10: HumanDecision | None = None,
    open_holdout: bool = False,
    today: str | None = None,
) -> LoopAResult:
    """Execute one research-loop trial. Fail-closed; hard human gates block progress."""
    adapters.require("run_backtest", "run_dk_test", "run_label_shuffle")
    today_str = _today(today)
    trial_no = ledger.next_trial_number()

    # 0. Stopping rule — DO NOT RUN if stopped (Spec Part 2.7, checklist item 6).
    if ledger.is_stopped():
        return LoopAResult(
            trial_number=trial_no,
            status="STOPPED",
            gate_reached="stopping_rule",
            gate_state=GateState.BLOCKED,
            stopped=True,
            note="is_stopped=True: loop halted. Await human re-examination decision.",
        )

    # 1. Zombie guard — never re-propose a REJECTED hypothesis as "untested".
    if is_zombie(registry, pre_reg.trial_id):
        return LoopAResult(
            trial_number=trial_no,
            status="BLOCKED_ZOMBIE",
            gate_reached="zombie_check",
            gate_state=GateState.BLOCKED,
            zombie=True,
            note=f"Hypothesis '{pre_reg.trial_id}' already REJECTED in registry. Do not resurface.",
        )

    # 2. Backtest (fail-closed: propagate engine errors, do not guess — Spec Part 2.6).
    backtest_out = adapters.run_backtest(pre_reg)
    returns = backtest_out["returns"]
    total_trades = int(backtest_out["total_trades"])
    trade_log = backtest_out.get("trade_log", "")

    # Provenance guard (Spec Part 2.2): timestamp-check the artifact.
    prov = check_provenance(trade_log, provenance_path) if trade_log else None
    prov_status = prov.status if prov else "SKIPPED"

    # 3. DK-test (pooled, multi-asset).
    dk_result = adapters.run_dk_test(returns, total_trades)
    thresholds = VerificationThresholds(
        dk_t_threshold=pre_reg.dk_t_threshold,
        min_positive_sharpe_count=pre_reg.min_positive_sharpe_count,
        label_shuffle_alpha=pre_reg.label_shuffle_alpha,
        min_trades=pre_reg.min_trades,
    )
    dk_pass = (float(dk_result.get("dk_t_stat", 0.0)) > thresholds.dk_t_threshold) and (
        dk_result.get("positive_sharpe_count", 0) >= thresholds.min_positive_sharpe_count
    )

    if not dk_pass:
        entry = LedgerEntry(
            trial_number=trial_no,
            id=pre_reg.trial_id,
            status=STATUS_REJECTED,
            tested_at=today_str,
            dk_t_stat=float(dk_result.get("dk_t_stat", 0.0)),
            pooled_sharpe=float(dk_result.get("pooled_sharpe", 0.0)),
            positive_sharpe_count=dk_result.get("positive_sharpe_count", 0),
            total_trades=total_trades,
            result_artifact=trade_log,
            conclusion="REJECTED at DK-test gate (dk_t / positive_sharpe_count below threshold).",
            validity_note=f"provenance={prov_status}",
            gate_reached="dk",
        )
        ledger.append(entry)  # same-round write
        return LoopAResult(
            trial_number=trial_no,
            status=STATUS_REJECTED,
            gate_reached="dk",
            verification=verify_three_layer(dk_result, 1.0, total_trades, thresholds),
            provenance_status=prov_status,
            note="DK-test failed.",
        )

    # 5. Label-shuffle.
    pvalue = float(adapters.run_label_shuffle(pre_reg, returns))

    # 5b. Cost-stress (SP1b): candidate must survive cost increases.
    #     Holdout may only be opened when dk + label-shuffle + min-trades
    #     + cost-stress ALL pass.
    cost_stress = None
    if adapters.run_cost_stress is not None:
        cost_stress = adapters.run_cost_stress(backtest_out)
    vresult = verify_candidate_gates(dk_result, pvalue, total_trades, cost_stress, thresholds)
    if not vresult.is_candidate:
        failed = vresult.failed()
        entry = LedgerEntry(
            trial_number=trial_no,
            id=pre_reg.trial_id,
            status=STATUS_REJECTED,
            tested_at=today_str,
            dk_t_stat=float(dk_result.get("dk_t_stat", 0.0)),
            pooled_sharpe=float(dk_result.get("pooled_sharpe", 0.0)),
            positive_sharpe_count=dk_result.get("positive_sharpe_count", 0),
            total_trades=total_trades,
            result_artifact=trade_log,
            conclusion=f"REJECTED: failed layers {failed} (not a candidate).",
            validity_note=f"provenance={prov_status}",
            gate_reached="verify",
        )
        ledger.append(entry)  # same-round write
        return LoopAResult(
            trial_number=trial_no,
            status=STATUS_REJECTED,
            gate_reached="verify",
            verification=vresult,
            provenance_status=prov_status,
            note=f"Exploratory gates failed: {failed}.",
        )

    # 7. Candidate survives exploratory gates -> log, then HUMAN GATE 7.
    entry = LedgerEntry(
        trial_number=trial_no,
        id=pre_reg.trial_id,
        status=STATUS_CANDIDATE,
        tested_at=today_str,
        dk_t_stat=float(dk_result.get("dk_t_stat", 0.0)),
        pooled_sharpe=float(dk_result.get("pooled_sharpe", 0.0)),
        positive_sharpe_count=dk_result.get("positive_sharpe_count", 0),
        total_trades=total_trades,
        result_artifact=trade_log,
        conclusion="Candidate survives DK + label-shuffle + min-trades.",
        validity_note=f"provenance={prov_status}",
        gate_reached="step7",
    )
    ledger.append(entry)  # same-round write (checklist item 4)

    gate7 = human_gate_step7(pre_reg.trial_id, human_decision_step7)
    if gate7 != GateState.CLEARED:
        return LoopAResult(
            trial_number=trial_no,
            status=STATUS_CANDIDATE,
            gate_reached="step7",
            gate_state=gate7,
            verification=vresult,
            provenance_status=prov_status,
            note="HUMAN GATE 7 not cleared: holdout NOT opened. Await human sign-off.",
        )

    # 8. Sacred holdout (one-time use).
    if open_holdout:
        if not ledger.sacred_holdout_open():
            return LoopAResult(
                trial_number=trial_no,
                status=STATUS_CANDIDATE,
                gate_reached="holdout",
                gate_state=GateState.BLOCKED,
                verification=vresult,
                note="Sacred holdout already consumed; cannot reopen (Spec Part 5).",
            )
        ledger.sacred_holdout_consume()
        adapters.require("run_holdout")
        holdout_pass = bool(adapters.run_holdout(pre_reg))
        if not holdout_pass:
            fail_entry = LedgerEntry(
                trial_number=trial_no,
                id=pre_reg.trial_id,
                status=STATUS_HOLDOUT_FAIL,
                tested_at=today_str,
                dk_t_stat=float(dk_result.get("dk_t_stat", 0.0)),
                pooled_sharpe=float(dk_result.get("pooled_sharpe", 0.0)),
                positive_sharpe_count=dk_result.get("positive_sharpe_count", 0),
                total_trades=total_trades,
                result_artifact=trade_log,
                conclusion="REJECTED on sacred holdout. Hypothesis dead permanently.",
                validity_note="HOLDOUT FAIL — no retesting allowed.",
                gate_reached="holdout",
            )
            ledger.append(fail_entry)
            return LoopAResult(
                trial_number=trial_no,
                status=STATUS_HOLDOUT_FAIL,
                gate_reached="holdout",
                verification=vresult,
                note="Sacred holdout rejected the candidate. Permanently REJECTED.",
            )
        # holdout pass -> record
        pass_entry = LedgerEntry(
            trial_number=trial_no,
            id=pre_reg.trial_id,
            status=STATUS_HOLDOUT_PASS,
            tested_at=today_str,
            dk_t_stat=float(dk_result.get("dk_t_stat", 0.0)),
            pooled_sharpe=float(dk_result.get("pooled_sharpe", 0.0)),
            positive_sharpe_count=dk_result.get("positive_sharpe_count", 0),
            total_trades=total_trades,
            result_artifact=trade_log,
            conclusion="Sacred holdout confirms edge.",
            validity_note="HOLDOUT PASS.",
            gate_reached="step10",
        )
        ledger.append(pass_entry)

    # 9. HUMAN GATE 10 (paper / live). Loop only ever proposes paper.
    gate10 = human_gate_step10("paper", human_decision_step10)
    if gate10 != GateState.CLEARED:
        return LoopAResult(
            trial_number=trial_no,
            status=STATUS_CANDIDATE if not open_holdout else STATUS_HOLDOUT_PASS,
            gate_reached="step10",
            gate_state=gate10,
            verification=vresult,
            provenance_status=prov_status,
            note="HUMAN GATE 10 not cleared: no paper/live deployment. Await human sign-off.",
        )

    return LoopAResult(
        trial_number=trial_no,
        status=STATUS_APPROVED_FOR_PAPER,
        gate_reached="step10",
        gate_state=GateState.CLEARED,
        verification=vresult,
        provenance_status=prov_status,
        note="Approved for paper trading (>=60d) pending human sign-off. Live requires separate approval.",
    )
