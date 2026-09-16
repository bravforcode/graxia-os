import json
from pathlib import Path

import pytest

from scripts.revenue_os.evidence_runner import main


def test_record_receipt_is_redacted_and_validated(tmp_path: Path, capsys):
    artifact = tmp_path / "artifact.bin"
    artifact.write_bytes(b"artifact")
    output = tmp_path / "receipt.json"
    assert main(
        [
            "record-receipt",
            "--gate",
            "staging-auth",
            "--environment",
            "staging",
            "--result",
            "passed",
            "--command",
            "pytest staging auth contract",
            "--output",
            str(output),
            "--source-sha",
            "a" * 40,
            "--artifact",
            str(artifact),
            "--assertion",
            "status=passed",
            "--safe-id",
            "run=staging-001",
        ]
    ) == 0
    value = json.loads(output.read_text(encoding="utf-8"))
    assert value["artifact_digest"].startswith("sha256:")
    assert "secret" not in output.read_text(encoding="utf-8").lower()
    assert json.loads(capsys.readouterr().out)["status"] == "ok"


def test_record_receipt_rejects_secret_like_command(tmp_path: Path, capsys):
    assert main(
        [
            "record-receipt",
            "--gate",
            "payment",
            "--environment",
            "staging",
            "--result",
            "passed",
            "--command",
            "stripe sk_test_not-a-real-secret",
            "--output",
            str(tmp_path / "receipt.json"),
            "--source-sha",
            "a" * 40,
            "--artifact-digest",
            "sha256:" + "b" * 64,
        ]
    ) == 2
    assert "unsafe evidence" in capsys.readouterr().err


def test_validate_receipt_command(tmp_path: Path):
    output = tmp_path / "receipt.json"
    output.write_text(
        json.dumps(
            {
                "gate": "rollback",
                "source_sha": "a" * 40,
                "artifact_digest": "sha256:" + "b" * 64,
                "environment": "local",
                "started_at": "2026-09-16T00:00:00+00:00",
                "finished_at": "2026-09-16T00:00:01+00:00",
                "command": "local rollback contract",
                "exit_code": 0,
                "assertions": {"status": "passed"},
                "safe_ids": {},
                "log_sha256": "c" * 64,
                "operator": "local-unverified",
                "result": "passed",
            }
        ),
        encoding="utf-8",
    )
    assert main(["validate-receipt", str(output)]) == 0
