"""Record and validate redacted Revenue OS evidence without provider calls.

This command intentionally records gate results supplied by an operator or CI;
it does not deploy, charge, publish, call Stripe, or call a hosting provider.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .evidence import EvidenceError, EvidenceReceipt, hash_file, validate_receipt, write_receipt


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
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        if args.operation == "record-receipt":
            record_receipt(args)
        else:
            validate_json(args.path)
    except (EvidenceError, OSError, subprocess.SubprocessError, json.JSONDecodeError) as exc:
        print(json.dumps({"status": "error", "error": str(exc)}), file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

