import json

import pytest

from scripts.revenue_os.evidence import (
    EvidenceReceipt,
    EvidenceError,
    hash_file,
    validate_manifest,
    validate_receipt,
    write_receipt,
)


def receipt(**overrides):
    value = {
        "gate": "build",
        "source_sha": "b" * 40,
        "artifact_digest": "sha256:" + "a" * 64,
        "environment": "staging",
        "started_at": "2026-09-16T10:00:00Z",
        "finished_at": "2026-09-16T10:00:01Z",
        "command": "python -m compileall scripts",
        "exit_code": 0,
        "assertions": {"compiled": True},
        "safe_ids": {"run_id": "run_123"},
        "log_sha256": "c" * 64,
        "operator": "controller",
        "result": "passed",
    }
    value.update(overrides)
    return value


def test_valid_receipt_round_trips_without_secret_values(tmp_path):
    target = tmp_path / "receipt.json"

    write_receipt(target, EvidenceReceipt(**receipt()))

    loaded = json.loads(target.read_text(encoding="utf-8"))
    assert validate_receipt(loaded) == loaded
    assert hash_file(target) == hash_file(target)


@pytest.mark.parametrize(
    "unsafe",
    [
        {"safe_ids": {"email": "buyer@example.com"}},
        {"safe_ids": {"card": "4242424242424242"}},
        {"safe_ids": {"secret": "sk_live_not-a-real-key"}},
        {"assertions": {"token": "whsec_not-a-real-secret"}},
    ],
)
def test_receipt_rejects_secret_or_pii(unsafe):
    with pytest.raises(EvidenceError):
        validate_receipt(receipt(**unsafe))


def test_manifest_rejects_failed_required_receipt():
    manifest = {
        "release_id": "2026-09-16-rc1",
        "source_sha": "b" * 40,
        "artifact_digest": "sha256:" + "a" * 64,
        "environment": "staging",
        "receipts": ["build.json"],
        "required_gates": ["build", "migrations"],
        "decision": "go",
        "gates": {"build": "passed", "migrations": "failed"},
    }

    with pytest.raises(EvidenceError, match="migrations"):
        validate_manifest(manifest)


def test_manifest_accepts_explicit_blocked_decision():
    manifest = {
        "release_id": "2026-09-16-rc1",
        "source_sha": "b" * 40,
        "artifact_digest": "sha256:" + "a" * 64,
        "environment": "staging",
        "receipts": [],
        "required_gates": ["build"],
        "decision": "blocked",
        "gates": {"build": "not-run"},
    }

    assert validate_manifest(manifest)["decision"] == "blocked"
