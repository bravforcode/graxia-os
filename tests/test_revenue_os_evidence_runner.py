import hashlib
import json
from pathlib import Path

from scripts.revenue_os.evidence import EvidenceReceipt, write_receipt
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


def _write_receipt(
    path: Path,
    *,
    gate: str,
    source_sha: str,
    artifact_digest: str,
    environment: str = "staging",
    result: str = "passed",
) -> None:
    write_receipt(
        path,
        EvidenceReceipt(
            gate=gate,
            source_sha=source_sha,
            artifact_digest=artifact_digest,
            environment=environment,
            started_at="2026-09-17T00:00:00+00:00",
            finished_at="2026-09-17T00:00:01+00:00",
            command=f"local {gate} contract",
            exit_code=0 if result == "passed" else 1,
            assertions={"result": result},
            safe_ids={"run": f"{gate}-001"},
            log_sha256="c" * 64,
            operator="local-unverified",
            result=result,
        ),
    )


def test_build_manifest_binds_receipts_to_release_identity(tmp_path: Path):
    release_dir = tmp_path / "2026-09-17-rc1"
    receipt_dir = release_dir / "receipts"
    artifact = tmp_path / "artifact.bin"
    artifact.write_bytes(b"artifact")
    source_sha = "a" * 40
    artifact_digest = "sha256:" + hashlib.sha256(b"artifact").hexdigest()
    _write_receipt(
        receipt_dir / "staging-auth.json",
        gate="staging-auth",
        source_sha=source_sha,
        artifact_digest=artifact_digest,
    )

    assert main(
        [
            "build-manifest",
            "--release-id",
            "2026-09-17-rc1",
            "--environment",
            "staging",
            "--receipt-dir",
            str(receipt_dir),
            "--output",
            str(release_dir / "manifest.json"),
            "--source-sha",
            source_sha,
            "--artifact",
            str(artifact),
            "--required-gate",
            "staging-auth",
        ]
    ) == 0
    manifest = json.loads((release_dir / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["decision"] == "blocked"
    assert manifest["gates"] == {"staging-auth": "passed"}
    assert manifest["receipts"] == ["receipts/staging-auth.json"]


def test_build_manifest_rejects_mismatched_receipt(tmp_path: Path, capsys):
    release_dir = tmp_path / "2026-09-17-rc1"
    artifact = tmp_path / "artifact.bin"
    artifact.write_bytes(b"artifact")
    _write_receipt(
        release_dir / "receipts" / "staging-auth.json",
        gate="staging-auth",
        source_sha="b" * 40,
        artifact_digest="sha256:" + hashlib.sha256(b"artifact").hexdigest(),
    )

    assert main(
        [
            "build-manifest",
            "--release-id",
            "2026-09-17-rc1",
            "--environment",
            "staging",
            "--receipt-dir",
            str(release_dir / "receipts"),
            "--output",
            str(release_dir / "manifest.json"),
            "--source-sha",
            "a" * 40,
            "--artifact",
            str(artifact),
            "--required-gate",
            "staging-auth",
        ]
    ) == 2
    assert "receipt identity mismatch" in capsys.readouterr().err


def test_build_manifest_go_requires_every_required_gate(tmp_path: Path, capsys):
    release_dir = tmp_path / "2026-09-17-rc1"
    artifact = tmp_path / "artifact.bin"
    artifact.write_bytes(b"artifact")
    source_sha = "a" * 40
    artifact_digest = "sha256:" + hashlib.sha256(b"artifact").hexdigest()
    _write_receipt(
        release_dir / "receipts" / "staging-auth.json",
        gate="staging-auth",
        source_sha=source_sha,
        artifact_digest=artifact_digest,
        result="blocked",
    )

    assert main(
        [
            "build-manifest",
            "--release-id",
            "2026-09-17-rc1",
            "--environment",
            "staging",
            "--receipt-dir",
            str(release_dir / "receipts"),
            "--output",
            str(release_dir / "manifest.json"),
            "--source-sha",
            source_sha,
            "--artifact-digest",
            artifact_digest,
            "--required-gate",
            "staging-auth",
            "--decision",
            "go",
        ]
    ) == 2
    assert "cannot mark manifest go" in capsys.readouterr().err
