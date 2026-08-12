"""Phase BE-P12 integration tests — guarded micro-live."""
from graxia.packages.quant_os.micro_live.micro_live_policy import MicroLivePolicy
from graxia.packages.quant_os.micro_live.live_preflight import LivePreflight
from graxia.packages.quant_os.micro_live.risk_check import MicroLiveRiskCheck, RiskBudget
from graxia.packages.quant_os.micro_live.evidence_pack import MicroLiveEvidencePack, EvidenceRecord
from graxia.packages.quant_os.micro_live.review_verdict import MicroLiveVerdict


def test_policy_validates():
    p = MicroLivePolicy()
    ok, issues = p.validate()
    assert ok


def test_preflight_all_pass():
    pf = LivePreflight()
    context = {
        "promotion_decision": True, "separate_live_profile": True,
        "separate_live_secrets": True, "independent_risk_ledger": True,
        "operator_enablement": True, "broker_healthy": True,
        "demo_gates_passed": True,
    }
    pf.check_all(context)
    assert pf.all_passed()


def test_risk_check_within():
    rc = MicroLiveRiskCheck()
    ok, issues = rc.check(RiskBudget(daily_pnl_bps=-20, orders_today=1))
    assert ok


def test_risk_check_exceeds():
    rc = MicroLiveRiskCheck()
    ok, issues = rc.check(RiskBudget(daily_pnl_bps=-60))
    assert not ok


def test_evidence_pack():
    pack = MicroLiveEvidencePack()
    pack.add(EvidenceRecord(record_id="R001", category="fill", description="filled"))
    assert pack.count() == 1


def test_verdict_eligible():
    v = MicroLiveVerdict()
    evidence = {
        "critical_incidents": 0, "reconciliation_pct": 100,
        "cost_gap_pct": 20, "safety_incidents": 0, "days_run": 60,
    }
    verdict = v.evaluate(evidence)
    assert verdict == "ELIGIBLE_FOR_EXPANSION"
