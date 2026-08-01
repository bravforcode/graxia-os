"""
Tests for loop_engineering — Loop Engineering for quant_os.

Covers the Spec checklist:
  [x] is_stopped halts the loop (does NOT run backtest) — checklist item 6
  [x] human gates (step7, step10) are hard blocks — checklist item 3
  [x] trial-ledger write happens in the same round as the run — checklist item 4
  [x] Loop A and Loop B are separate entry points — checklist item 5
  [x] zombie-hypothesis guard (read registry before proposing) — checklist item 2
  [x] 3-layer verify requires ALL gates (no raw-Sharpe "promising")
  [x] sacred holdout is one-time use
  [x] canonical commit requires human sign-off (CONTRIBUTING.md line 108)
  [x] pre-registration locks thresholds + Optuna ranges

All validation adapters are injected fakes — no real backtest/data required.
"""

import tempfile
from dataclasses import FrozenInstanceError
from pathlib import Path

import pytest

from graxia.packages.quant_os.loop_engineering import (
    STATUS_APPROVED_FOR_PAPER,
    STATUS_CANDIDATE,
    STATUS_REJECTED,
    GateState,
    HumanDecision,
    HumanSignOffRequiredError,
    LedgerEntry,
    PreRegistration,
    SacredHoldout,
    StoppingRule,
    WorkingLedger,
    is_zombie,
    load_hypothesis_registry,
    load_pre_registration,
    run_operational_loop,
    run_research_loop,
    verify_three_layer,
)
from graxia.packages.quant_os.loop_engineering.validation import ValidationAdapters


# ---------------------------------------------------------------------------
# Fakes
# ---------------------------------------------------------------------------
class CallTracker:
    def __init__(self):
        self.calls = []

    def __call__(self, *a, **k):
        self.calls.append((a, k))
        return None


def make_adapters(dk_result, pvalue, total_trades, holdout_pass=True, returns=None):
    tracker = CallTracker()

    def run_backtest(pre_reg):
        tracker(pre_reg)
        return {
            "returns": returns if returns is not None else object(),
            "total_trades": total_trades,
            "trade_log": "reports/fake_20260720_valid.json",  # post-fix date -> VALID
        }

    def run_dk_test(r, tt):
        return dk_result

    def run_label_shuffle(pre_reg, r):
        return pvalue

    def run_holdout(pre_reg):
        return holdout_pass

    adapters = ValidationAdapters(
        run_backtest=run_backtest,
        run_dk_test=run_dk_test,
        run_label_shuffle=run_label_shuffle,
        run_holdout=run_holdout,
    )
    return adapters, tracker


def dk_pass_dict(dk_t=3.0, pos=6):
    return {"dk_t_stat": dk_t, "pooled_sharpe": 1.2, "positive_sharpe_count": pos}


def base_pre_reg(trial_id="T-TEST-1", direction="A", optuna_max_trials=0):
    return PreRegistration(
        trial_id=trial_id,
        direction=direction,
        hypothesis="test hypothesis",
        symbol="XAUUSD",
        timeframe="15m",
        strategy_file="strategies/test.py",
        optuna_max_trials=optuna_max_trials,
    )


def empty_registry():
    return {"hypotheses": []}


# ---------------------------------------------------------------------------
# Checklist item 6: is_stopped halts the loop (backtest NEVER runs)
# ---------------------------------------------------------------------------
def test_is_stopped_halts_loop():
    ledger = WorkingLedger(
        Path(tempfile.mktemp(suffix=".json")),
        direction="A",
        stopping_rule=StoppingRule(is_stopped=True),
    )
    adapters, tracker = make_adapters(dk_pass_dict(), 0.01, 200)
    result = run_research_loop(base_pre_reg(), adapters, ledger, empty_registry(), Path("/nonexistent/prov.md"))
    assert result.stopped is True
    assert result.status == "STOPPED"
    assert result.gate_reached == "stopping_rule"
    assert tracker.calls == [], "backtest must NOT run when is_stopped"


def test_consecutive_fails_trigger_stopped():
    path = Path(tempfile.mktemp(suffix=".json"))
    ledger = WorkingLedger(path, direction="A")
    adapters, _ = make_adapters({"dk_t_stat": 0.5, "positive_sharpe_count": 1}, 0.9, 50)
    for i in range(3):
        pre = base_pre_reg(trial_id=f"FAIL-{i}")
        res = run_research_loop(pre, adapters, ledger, empty_registry(), Path("/nonexistent/prov.md"))
        assert res.status == STATUS_REJECTED
    assert ledger.is_stopped() is True
    # 4th trial must not run
    tracker2 = CallTracker()
    adapters2 = ValidationAdapters(
        run_backtest=lambda p: tracker2(p)
        or {"returns": object(), "total_trades": 50, "trade_log": "reports/fake_20260720_valid.json"},
        run_dk_test=lambda r, t: dk_pass_dict(),
        run_label_shuffle=lambda p, r: 0.01,
    )
    res = run_research_loop(base_pre_reg("FAIL-3"), adapters2, ledger, empty_registry(), Path("/nonexistent/prov.md"))
    assert res.stopped is True
    assert tracker2.calls == []


# ---------------------------------------------------------------------------
# Checklist item 3: human gates are hard blocks
# ---------------------------------------------------------------------------
def test_human_gate_step7_blocks_without_signoff():
    ledger = WorkingLedger(Path(tempfile.mktemp(suffix=".json")), direction="A")
    adapters, _ = make_adapters(dk_pass_dict(), 0.01, 200)
    res = run_research_loop(base_pre_reg(), adapters, ledger, empty_registry(), Path("/nonexistent/prov.md"))
    assert res.status == STATUS_CANDIDATE
    assert res.gate_reached == "step7"
    assert res.gate_state == GateState.REQUIRES_HUMAN
    assert ledger.sacred_holdout.use_count == 0, "holdout must NOT open without sign-off"


def test_human_gate_step10_blocks_auto_deploy():
    ledger = WorkingLedger(Path(tempfile.mktemp(suffix=".json")), direction="A")
    adapters, _ = make_adapters(dk_pass_dict(), 0.01, 200)
    decision7 = HumanDecision(approved=True, reviewer="human", token="tok-7")
    res = run_research_loop(
        base_pre_reg(),
        adapters,
        ledger,
        empty_registry(),
        Path("/nonexistent/prov.md"),
        human_decision_step7=decision7,
    )
    assert res.gate_reached == "step10"
    assert res.gate_state == GateState.REQUIRES_HUMAN
    assert res.status != STATUS_APPROVED_FOR_PAPER


def test_full_candidate_flow_with_signoff_and_holdout():
    ledger = WorkingLedger(Path(tempfile.mktemp(suffix=".json")), direction="A")
    adapters, _ = make_adapters(dk_pass_dict(), 0.01, 200, holdout_pass=True)
    d7 = HumanDecision(approved=True, reviewer="human", token="tok-7")
    d10 = HumanDecision(approved=True, reviewer="human", token="tok-10")
    res = run_research_loop(
        base_pre_reg(),
        adapters,
        ledger,
        empty_registry(),
        Path("/nonexistent/prov.md"),
        human_decision_step7=d7,
        human_decision_step10=d10,
        open_holdout=True,
    )
    assert res.status == STATUS_APPROVED_FOR_PAPER
    assert res.gate_state == GateState.CLEARED
    assert ledger.sacred_holdout.use_count == 1


# ---------------------------------------------------------------------------
# 3-layer verify requires ALL gates
# ---------------------------------------------------------------------------
def test_label_shuffle_failure_is_not_candidate():
    ledger = WorkingLedger(Path(tempfile.mktemp(suffix=".json")), direction="A")
    # good raw Sharpe (dk passes) but label-shuffle p >= 0.05
    adapters, _ = make_adapters(dk_pass_dict(), 0.30, 200)
    res = run_research_loop(base_pre_reg(), adapters, ledger, empty_registry(), Path("/nonexistent/prov.md"))
    assert res.status == STATUS_REJECTED
    assert res.verification is not None
    assert res.verification.is_candidate is False
    assert res.verification.label_shuffle_pass is False


def test_min_trades_failure_is_not_candidate():
    ledger = WorkingLedger(Path(tempfile.mktemp(suffix=".json")), direction="A")
    adapters, _ = make_adapters(dk_pass_dict(), 0.01, 50)  # only 50 trades
    res = run_research_loop(base_pre_reg(), adapters, ledger, empty_registry(), Path("/nonexistent/prov.md"))
    assert res.status == STATUS_REJECTED
    assert res.verification.min_trades_pass is False


def test_dk_failure_is_rejected():
    ledger = WorkingLedger(Path(tempfile.mktemp(suffix=".json")), direction="A")
    adapters, _ = make_adapters({"dk_t_stat": 0.8, "positive_sharpe_count": 2}, 0.01, 200)
    res = run_research_loop(base_pre_reg(), adapters, ledger, empty_registry(), Path("/nonexistent/prov.md"))
    assert res.status == STATUS_REJECTED
    assert res.gate_reached == "dk"


# ---------------------------------------------------------------------------
# Checklist item 2: zombie-hypothesis guard
# ---------------------------------------------------------------------------
def test_zombie_hypothesis_blocked():
    registry = {"hypotheses": [{"id": "ZOMBIE-1", "status": STATUS_REJECTED}]}
    ledger = WorkingLedger(Path(tempfile.mktemp(suffix=".json")), direction="A")
    adapters, tracker = make_adapters(dk_pass_dict(), 0.01, 200)
    res = run_research_loop(base_pre_reg("ZOMBIE-1"), adapters, ledger, registry, Path("/nonexistent/prov.md"))
    assert res.zombie is True
    assert res.status == "BLOCKED_ZOMBIE"
    assert tracker.calls == [], "zombie must not be (re)tested"


# ---------------------------------------------------------------------------
# Checklist item 4: same-round ledger write
# ---------------------------------------------------------------------------
def test_same_round_ledger_write():
    path = Path(tempfile.mktemp(suffix=".json"))
    ledger = WorkingLedger(path, direction="A")
    before = len(ledger.lineage)
    adapters, _ = make_adapters(dk_pass_dict(), 0.01, 200)
    run_research_loop(base_pre_reg("WRITE-1"), adapters, ledger, empty_registry(), Path("/nonexistent/prov.md"))
    # entry written in the same call as the run
    assert len(ledger.lineage) == before + 1
    assert ledger.lineage[-1].id == "WRITE-1"
    assert ledger.lineage[-1].status == STATUS_CANDIDATE


# ---------------------------------------------------------------------------
# Sacred holdout one-time use
# ---------------------------------------------------------------------------
def test_sacred_holdout_one_time():
    ledger = WorkingLedger(
        Path(tempfile.mktemp(suffix=".json")),
        direction="A",
        sacred_holdout=SacredHoldout(max_use_count=1, use_count=0),
    )
    assert ledger.sacred_holdout_open() is True
    ledger.sacred_holdout_consume()
    assert ledger.sacred_holdout_open() is False
    with pytest.raises(RuntimeError):
        ledger.sacred_holdout_consume()


def test_loop_blocks_if_holdout_already_consumed():
    ledger = WorkingLedger(
        Path(tempfile.mktemp(suffix=".json")),
        direction="A",
        sacred_holdout=SacredHoldout(max_use_count=1, use_count=1, status="CONSUMED"),
    )
    adapters, _ = make_adapters(dk_pass_dict(), 0.01, 200, holdout_pass=True)
    d7 = HumanDecision(approved=True, reviewer="human", token="tok-7")
    res = run_research_loop(
        base_pre_reg(),
        adapters,
        ledger,
        empty_registry(),
        Path("/nonexistent/prov.md"),
        human_decision_step7=d7,
        open_holdout=True,
    )
    assert res.gate_reached == "holdout"
    assert res.gate_state == GateState.BLOCKED


# ---------------------------------------------------------------------------
# Canonical commit requires human sign-off (CONTRIBUTING.md line 108)
# ---------------------------------------------------------------------------
def test_commit_requires_signoff():
    ledger = WorkingLedger(Path(tempfile.mktemp(suffix=".json")), direction="A")
    entry = LedgerEntry(trial_number=1, id="C-1", status=STATUS_CANDIDATE)
    # Canonical files ALWAYS pre-exist in this system (governance-locked). Mirror that.
    canon_ledger = Path(tempfile.mktemp(suffix=".json"))
    canon_ledger.write_text("{}", encoding="utf-8")
    canon_reg = Path(tempfile.mktemp(suffix=".json"))
    canon_reg.write_text('{"hypotheses": []}', encoding="utf-8")
    with pytest.raises(HumanSignOffRequiredError):
        ledger.commit_to_canonical(entry, "", canon_ledger, canon_reg)
    # with token it succeeds
    ledger.commit_to_canonical(entry, "human-signoff-token", canon_ledger, canon_reg)
    assert canon_ledger.exists()
    assert canon_reg.exists()


# ---------------------------------------------------------------------------
# Pre-registration locks thresholds + Optuna ranges
# ---------------------------------------------------------------------------
def test_pre_register_frozen_cannot_mutate():
    pre = base_pre_reg()
    with pytest.raises(FrozenInstanceError):
        pre.dk_t_threshold = 1.0  # type: ignore[misc]


def test_pre_register_optuna_requires_locked_ranges():
    with pytest.raises(ValueError):
        PreRegistration(
            trial_id="X",
            direction="A",
            hypothesis="h",
            symbol="XAUUSD",
            timeframe="15m",
            strategy_file="s.py",
            optuna_max_trials=20,
            optuna_param_ranges=None,  # ranges NOT locked -> must fail
        )
    ok = PreRegistration(
        trial_id="X",
        direction="A",
        hypothesis="h",
        symbol="XAUUSD",
        timeframe="15m",
        strategy_file="s.py",
        optuna_max_trials=20,
        optuna_param_ranges={"period": [10, 30]},
    )
    assert ok.parameter_space_locked is True


# ---------------------------------------------------------------------------
# Checklist item 5: Loop A and Loop B are separate entry points
# ---------------------------------------------------------------------------
def test_loop_b_is_separate_entrypoint_and_alerts_only():
    from graxia.packages.quant_os.loop_engineering import (
        OperationalAlert,
        PerformanceSample,
    )

    # no decay
    sample = PerformanceSample(strategy_id="S1", metric="sharpe", value=1.5, timestamp="t")
    alert = run_operational_loop(sample, decay_threshold=0.5)
    assert isinstance(alert, OperationalAlert)
    assert alert.decay_detected is False
    assert alert.route_to == ""
    # decay, no human -> alert only, no route
    bad = PerformanceSample(strategy_id="S1", metric="sharpe", value=0.1, timestamp="t")
    alert2 = run_operational_loop(bad, decay_threshold=0.5)
    assert alert2.decay_detected is True
    assert alert2.human_action_required is True
    assert alert2.route_to == ""
    # decay + human approval -> route back to Loop A (not retune+deploy)
    human = HumanDecision(approved=True, reviewer="human", token="tok")
    alert3 = run_operational_loop(bad, decay_threshold=0.5, human_decision=human)
    assert alert3.route_to == "LOOP_A_REVALIDATION"


# ---------------------------------------------------------------------------
# verify_three_layer unit
# ---------------------------------------------------------------------------
def test_verify_three_layer_all_pass():
    r = verify_three_layer(dk_pass_dict(), 0.01, 200)
    assert r.is_candidate is True


def test_verify_three_layer_any_fail():
    r = verify_three_layer(dk_pass_dict(), 0.06, 200)  # label-shuffle fails
    assert r.is_candidate is False


# ---------------------------------------------------------------------------
# Point 3 — Adversarial: optimizer rejects in-memory PreRegistration (source_path gate)
# ---------------------------------------------------------------------------
def test_optimizer_source_path_gate():
    """Optimizer refuses an ad-hoc PreRegistration (source_path empty) even with locked ranges."""
    from graxia.packages.quant_os.loop_engineering.optimizer import run_constrained_optuna

    # Ad-hoc construction (no committed file) → rejected
    adhoc = PreRegistration(
        trial_id="EVIL-1",
        direction="A",
        hypothesis="adversarial",
        symbol="XAUUSD",
        timeframe="15m",
        strategy_file="s.py",
        optuna_max_trials=5,
        optuna_param_ranges={"period": [5, 50]},
    )
    assert adhoc.source_path == ""  # proves: in-memory construction has no source
    with pytest.raises(RuntimeError, match="not loaded from a committed file"):
        run_constrained_optuna(adhoc, lambda p: 0.0, ValidationAdapters())

    # Loaded from file under allowed root → source_path stamped → passes the source gate
    meta_dir = Path(__file__).resolve().parent.parent / "Meta"
    tmp = meta_dir / "_test_optimizer_source_path_gate.json"
    try:
        adhoc.save(tmp)
        loaded = load_pre_registration(tmp)
        assert loaded.source_path == str(tmp.resolve())
        # (If optuna is not installed, it will raise about optuna — that's the correct
        #  path; the source_path gate is passed. If optuna IS installed, it proceeds.)
    finally:
        if tmp.exists():
            tmp.unlink()


# ---------------------------------------------------------------------------
# Point 1 — Integration: is_zombie against the REAL hypothesis_registry.json
# ---------------------------------------------------------------------------
def test_is_zombie_against_real_registry():
    """Integration: is_zombie flags all REJECTED entries in the real file as zombies."""
    real_path = Path(__file__).resolve().parent.parent / "research" / "hypothesis_registry.json"
    if not real_path.exists():
        pytest.skip("Real hypothesis_registry.json not found")
    reg = load_hypothesis_registry(real_path)
    for h in reg.get("hypotheses", []):
        hid = h.get("id")
        status = h.get("status")
        if status == "REJECTED":
            assert is_zombie(reg, hid), f"REJECTED '{hid}' should be flagged zombie"
        elif status == "INSUFFICIENT_DATA":
            # Not tested → NOT a zombie (untested hypotheses remain open questions)
            assert not is_zombie(reg, hid), f"INSUFFICIENT_DATA '{hid}' must NOT be zombie"
    # Cross-ledger: Direction C IDs are unique — no ID collision
    reg_c = Path(__file__).resolve().parent.parent / "research" / "hypothesis_registry_c.json"
    if reg_c.exists():
        reg_c_data = load_hypothesis_registry(reg_c)
        main_ids = {h["id"] for h in reg.get("hypotheses", [])}
        c_ids = {h["id"] for h in reg_c_data.get("hypotheses", [])}
        overlap = main_ids & c_ids
        assert not overlap, f"Cross-ledger ID collision: {overlap}"


# ---------------------------------------------------------------------------
# Point 4 — Structural proof: the automated loop NEVER calls commit_to_canonical
# ---------------------------------------------------------------------------
def test_loop_never_calls_commit():
    """run_research_loop's code path never reaches commit_to_canonical (human-only)."""
    ledger = WorkingLedger(Path(tempfile.mktemp(suffix=".json")), direction="A")
    adapters, _ = make_adapters(dk_pass_dict(), 0.01, 200)

    # Track calls to commit_to_canonical
    commit_calls = []
    _original = ledger.commit_to_canonical

    def tracking_commit(*args, **kwargs):
        commit_calls.append(True)
        return _original(*args, **kwargs)

    ledger.commit_to_canonical = tracking_commit  # type: ignore[assignment]

    # Run the loop (candidate path — passes all gates)
    res = run_research_loop(
        base_pre_reg(),
        adapters,
        ledger,
        empty_registry(),
        Path("/nonexistent/prov.md"),
    )
    # The loop must NOT have called commit
    assert commit_calls == [], (
        "Automated loop MUST NOT call commit_to_canonical — "
        "it returns REQUIRES_HUMAN and the human performs the commit."
    )
    # Gate state confirms it stopped at step7 (human review required)
    assert res.gate_state == GateState.REQUIRES_HUMAN
