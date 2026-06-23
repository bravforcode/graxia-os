"""Test evidence bundle."""
import tempfile, os, json
from execution.demo_canary.evidence_bundle import EvidenceBundle

class TestEvidenceBundle:
    def test_add_and_seal(self):
        with tempfile.TemporaryDirectory() as tmp:
            bundle = EvidenceBundle("CANARY-TEST", output_dir=tmp)
            h = bundle.add_artifact("plan.json", {"test": True})
            assert len(h) == 64  # SHA-256 hex
            manifest = bundle.seal()
            assert "seal_hash" in manifest
            assert manifest["canary_id"] == "CANARY-TEST"

    def test_verify_passes(self):
        with tempfile.TemporaryDirectory() as tmp:
            bundle = EvidenceBundle("CANARY-VERIFY", output_dir=tmp)
            bundle.add_artifact("test.json", {"data": 1})
            bundle.seal()
            assert bundle.verify()

    def test_verify_fails_on_tamper(self):
        with tempfile.TemporaryDirectory() as tmp:
            bundle = EvidenceBundle("CANARY-TAMPER", output_dir=tmp)
            bundle.add_artifact("test.json", {"data": 1})
            bundle.seal()
            # Tamper with file
            fpath = os.path.join(tmp, "CANARY-TAMPER", "test.json")
            with open(fpath, "w") as f:
                f.write('{"tampered": true}')
            assert not bundle.verify()
