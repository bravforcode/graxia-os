"""Tests for evidence pack."""

from graxia.packages.quant_os.validation.evidence_pack import EvidencePack


def test_pack_creates():
    pack = EvidencePack()
    assert pack is not None


def test_pack_build_complete():
    pack = EvidencePack()
    evidence = {
        "historical_validation": {"trade_count": 150},
        "oracle_comparison": {"match": True},
        "shadow_report": {"days": 30},
        "demo_report": {"orders": 100},
        "incident_register": {"critical": 0},
        "cost_calibration": {"gap": 20},
        "risk_adherence": {"breaches": 0},
        "contract_evidence": {"locked": True},
        "release_bundle": {"hash": "abc"},
    }
    items = pack.build(evidence)
    assert pack.is_complete()
    assert len(items) == 9


def test_pack_build_incomplete():
    pack = EvidencePack()
    evidence = {"historical_validation": {}}
    pack.build(evidence)
    assert not pack.is_complete()
    assert len(pack.get_missing()) == 8


def test_pack_report():
    pack = EvidencePack()
    evidence = {"historical_validation": {}}
    pack.build(evidence)
    report = pack.to_report()
    assert "Evidence Pack" in report
