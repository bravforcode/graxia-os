"""Record and validate redacted Revenue OS evidence without provider calls.

This command intentionally records gate results supplied by an operator or CI;
it does not deploy, charge, publish, call Stripe, or call a hosting provider.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .evidence import (
    EvidenceError,
    EvidenceReceipt,
    hash_file,
    validate_manifest,
    validate_receipt,
    write_receipt,
)


_HEX40 = re.compile(r"[0-9a-f]{40}")
_SHA256 = re.compile(r"sha256:[0-9a-f]{64}")


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _git_source_sha(repo_root: Path) -> str:
    result = subprocess.run(
        ["git", "-C", str(repo_root), "rev-parse", "HEAD"],
        check=True,
        capture_output=True,
        text=True,
    )
    value = result.stdout.strip()
    if len(value) != 40 or any(char not in "0123456789abcdef" for char in value):
        raise EvidenceError("git did not return a safe source SHA")
    return value


def _parse_pairs(values: list[str], *, field: str) -> dict[str, str]:
    result: dict[str, str] = {}
    for item in values:
        key, separator, value = item.partition("=")
        if not separator or not key or key in result:
            raise EvidenceError(f"invalid {field} entry")
        result[key] = value
    return result


def _log_hash(path: str | None, explicit: str | None) -> str:
    if path and explicit:
        raise EvidenceError("provide either --log or --log-sha256")
    if path:
        return hash_file(path)
    if explicit:
        if len(explicit) != 64 or any(char not in "0123456789abcdef" for char in explicit):
            raise EvidenceError("log SHA-256 must be lowercase hex")
        return explicit
    return hashlib.sha256(b"").hexdigest()


def record_receipt(args: argparse.Namespace) -> Path:
    repo_root = Path(args.repo_root).resolve()
    source_sha = args.source_sha or _git_source_sha(repo_root)
    artifact_digest = args.artifact_digest
    if args.artifact:
        if artifact_digest:
            raise EvidenceError("provide either --artifact or --artifact-digest")
        artifact_digest = f"sha256:{hash_file(args.artifact)}"
    if not artifact_digest:
        raise EvidenceError("artifact identity is required")
    started_at = args.started_at or _utc_now()
    finished_at = args.finished_at or _utc_now()
    assertions: dict[str, Any] = _parse_pairs(args.assertion, field="assertion")
    safe_ids: dict[str, Any] = _parse_pairs(args.safe_id, field="safe-id")
    receipt = EvidenceReceipt(
        gate=args.gate,
        source_sha=source_sha,
        artifact_digest=artifact_digest,
        environment=args.environment,
        started_at=started_at,
        finished_at=finished_at,
        command=args.command,
        exit_code=args.exit_code,
        assertions=assertions,
        safe_ids=safe_ids,
        log_sha256=_log_hash(args.log, args.log_sha256),
        operator=args.operator,
        result=args.result,
    )
    target = write_receipt(args.output, receipt)
    print(json.dumps({"status": "ok", "gate": args.gate, "result": args.result}))
    return target


def validate_json(path: str) -> None:
    value = json.loads(Path(path).read_text(encoding="utf-8"))
    validate_receipt(value)
    print(json.dumps({"status": "ok", "path": Path(path).name}))


def _artifact_digest(args: argparse.Namespace) -> str:
    if args.artifact and args.artifact_digest:
        raise EvidenceError("provide either --artifact or --artifact-digest")
    if args.artifact:
        return f"sha256:{hash_file(args.artifact)}"
    if args.artifact_digest:
        if not _SHA256.fullmatch(args.artifact_digest):
            raise EvidenceError("artifact digest must be sha256:<64 lowercase hex>")
        return args.artifact_digest
    raise EvidenceError("artifact identity is required")


def _manifest_receipts(
    receipt_dir: Path,
    manifest_dir: Path,
    *,
    source_sha: str,
    artifact_digest: str,
    environment: str,
) -> tuple[list[str], dict[str, str]]:
    if not receipt_dir.is_dir():
        raise EvidenceError(f"receipt directory does not exist: {receipt_dir}")
    paths: list[str] = []
    gates: dict[str, str] = {}
    for path in sorted(receipt_dir.glob("*.json")):
        value = json.loads(path.read_text(encoding="utf-8"))
        validate_receipt(value)
        for key, expected in (
            ("source_sha", source_sha),
            ("artifact_digest", artifact_digest),
            ("environment", environment),
        ):
            if value[key] != expected:
                raise EvidenceError(f"receipt identity mismatch for {path.name}: {key}")
        gate = value["gate"]
        if gate in gates:
            raise EvidenceError(f"duplicate receipt gate: {gate}")
        gates[gate] = value["result"]
        try:
            relative = path.resolve().relative_to(manifest_dir.resolve())
        except ValueError as exc:
            raise EvidenceError("receipt directory must be inside the manifest directory") from exc
        paths.append(relative.as_posix())
    return paths, gates


def build_manifest(args: argparse.Namespace) -> Path:
    repo_root = Path(args.repo_root).resolve()
    source_sha = args.source_sha or _git_source_sha(repo_root)
    if not _HEX40.fullmatch(source_sha):
        raise EvidenceError("source SHA must be 40 lowercase hex characters")
    artifact_digest = _artifact_digest(args)
    output = Path(args.output).resolve()
    receipt_paths, receipt_gates = _manifest_receipts(
        Path(args.receipt_dir).resolve(),
        output.parent,
        source_sha=source_sha,
        artifact_digest=artifact_digest,
        environment=args.environment,
    )
    required_gates = list(dict.fromkeys(args.required_gate))
    if not required_gates:
        raise EvidenceError("at least one --required-gate is required")
    gates = {gate: receipt_gates.get(gate, "not-run") for gate in required_gates}
    for gate, result in receipt_gates.items():
        gates.setdefault(gate, result)
    if args.decision == "go":
        missing = [gate for gate in required_gates if gates[gate] != "passed"]
        if missing:
            raise EvidenceError(f"cannot mark manifest go; gates not passed: {', '.join(missing)}")
    manifest = {
        "release_id": args.release_id,
        "source_sha": source_sha,
        "artifact_digest": artifact_digest,
        "environment": args.environment,
        "receipts": receipt_paths,
        "required_gates": required_gates,
        "gates": gates,
        "decision": args.decision,
        "note": args.note,
    }
    validate_manifest(manifest)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({"status": "ok", "path": str(output), "decision": args.decision}))
    return output


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="operation", required=True)
    record = subparsers.add_parser("record-receipt")
    record.add_argument("--gate", required=True)
    record.add_argument("--environment", choices=("local", "staging", "production"), required=True)
    record.add_argument("--result", choices=("passed", "failed", "blocked", "not-run", "skipped"), required=True)
    record.add_argument("--command", required=True)
    record.add_argument("--output", required=True)
    record.add_argument("--repo-root", default=".")
    record.add_argument("--source-sha")
    record.add_argument("--artifact")
    record.add_argument("--artifact-digest")
    record.add_argument("--log")
    record.add_argument("--log-sha256")
    record.add_argument("--exit-code", type=int, default=0)
    record.add_argument("--operator", default="local-unverified")
    record.add_argument("--started-at")
    record.add_argument("--finished-at")
    record.add_argument("--assertion", action="append", default=[])
    record.add_argument("--safe-id", action="append", default=[])
    validate = subparsers.add_parser("validate-receipt")
    validate.add_argument("path")
    manifest = subparsers.add_parser("build-manifest")
    manifest.add_argument("--release-id", required=True)
    manifest.add_argument("--environment", choices=("local", "staging", "production"), required=True)
    manifest.add_argument("--receipt-dir", required=True)
    manifest.add_argument("--output", required=True)
    manifest.add_argument("--repo-root", default=".")
    manifest.add_argument("--source-sha")
    manifest.add_argument("--artifact")
    manifest.add_argument("--artifact-digest")
    manifest.add_argument("--required-gate", action="append", default=[])
    manifest.add_argument("--decision", choices=("go", "no-go", "blocked"), default="blocked")
    manifest.add_argument("--note", default="Generated from validated redacted receipts.")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        if args.operation == "record-receipt":
            record_receipt(args)
        elif args.operation == "validate-receipt":
            validate_json(args.path)
        else:
            build_manifest(args)
    except (EvidenceError, OSError, subprocess.SubprocessError, json.JSONDecodeError) as exc:
        print(json.dumps({"status": "error", "error": str(exc)}), file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
