"""Tests for micro-live evidence pack."""
from graxia.packages.quant_os.micro_live.evidence_pack import MicroLiveEvidencePack, EvidenceRecord


def test_pack_creates():
    pack = MicroLiveEvidencePack()
    assert pack.count() == 0


def test_pack_adds():
    pack = MicroLiveEvidencePack()
    pack.add(EvidenceRecord(record_id="R001", category="fill", description="order filled"))
    assert pack.count() == 1
    assert pack.get_by_category("fill")


def test_pack_summary():
    pack = MicroLiveEvidencePack()
    pack.add(EvidenceRecord(record_id="R001", category="fill", description="filled"))
    pack.add(EvidenceRecord(record_id="R002", category="rejection", description="rejected"))
    s = pack.summary()
    assert s["total"] == 2
    assert s["by_category"]["fill"] == 1
