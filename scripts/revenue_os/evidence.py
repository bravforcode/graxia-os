"""Fail-closed, redacted release evidence helpers.

Evidence is metadata, not a log archive. Keep receipts small and bind them to
the exact source/artifact state that produced them.
"""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Mapping


class EvidenceError(ValueError):
    """Raised when a receipt or manifest cannot be safely recorded."""


@dataclass(frozen=True)
class EvidenceReceipt:
    """Typed receipt boundary; values remain subject to redaction checks."""

    gate: str
    source_sha: str
    artifact_digest: str
    environment: str
    started_at: str
    finished_at: str
    command: str
    exit_code: int
    assertions: Mapping[str, Any]
    safe_ids: Mapping[str, Any]
    log_sha256: str
    operator: str
    result: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


_HEX40 = re.compile(r"^[0-9a-f]{40}$")
_SHA256 = re.compile(r"^sha256:[0-9a-f]{64}$")
_EMAIL = re.compile(r"\b[^\s@]+@[^\s@]+\.[^\s@]+\b")
_CARD = re.compile(r"\b\d{13,19}\b")
_SECRET = re.compile(
    r"(?:sk_(?:live|test)_|rk_(?:live|test)_|whsec_|ghp_|github_pat_|"
    r"AKIA[0-9A-Z]{16}|AIza[0-9A-Za-z_-]{20,})"
)
_SECRET_KEYS = {
    "api_key",
    "apikey",
    "credential",
    "password",
    "secret",
    "token",
}
_ENVIRONMENTS = {"local", "staging", "production"}
_RESULTS = {"passed", "failed", "blocked", "not-run", "skipped"}
_DECISIONS = {"go", "no-go", "blocked"}


def _reject_unsafe(value: Any, path: str = "receipt") -> None:
    if isinstance(value, Mapping):
        for key, child in value.items():
            key_text = str(key).lower()
            if key_text in _SECRET_KEYS or any(
                marker in key_text
                for marker in ("private_key", "access_token", "refresh_token")
            ):
                raise EvidenceError(f"unsafe evidence field: {path}.{key}")
            _reject_unsafe(child, f"{path}.{key}")
        return
    if isinstance(value, list):
        for index, child in enumerate(value):
            _reject_unsafe(child, f"{path}[{index}]")
        return
    if isinstance(value, str) and (
        _EMAIL.search(value) or _CARD.search(value) or _SECRET.search(value)
    ):
        raise EvidenceError(f"unsafe evidence value at {path}")


def _require_string(data: Mapping[str, Any], key: str) -> str:
    value = data.get(key)
    if not isinstance(value, str) or not value:
        raise EvidenceError(f"missing string field: {key}")
    return value


def validate_receipt(receipt: Mapping[str, Any]) -> dict[str, Any]:
    """Validate and return a copy of one redacted receipt."""
    if not isinstance(receipt, Mapping):
        raise EvidenceError("receipt must be an object")

    value = dict(receipt)
    _reject_unsafe(value)
    for key in (
        "gate",
        "source_sha",
        "artifact_digest",
        "environment",
        "started_at",
        "finished_at",
        "command",
        "operator",
        "result",
    ):
        _require_string(value, key)
    if not _HEX40.fullmatch(value["source_sha"]):
        raise EvidenceError("source_sha must be 40 lowercase hex characters")
    if not _SHA256.fullmatch(value["artifact_digest"]):
        raise EvidenceError("artifact_digest must be sha256:<64 lowercase hex>")
    if value["environment"] not in _ENVIRONMENTS:
        raise EvidenceError("unknown evidence environment")
    if value["result"] not in _RESULTS:
        raise EvidenceError("unknown receipt result")
    if not isinstance(value.get("exit_code"), int):
        raise EvidenceError("exit_code must be an integer")
    if not isinstance(value.get("assertions"), Mapping):
        raise EvidenceError("assertions must be an object")
    if not isinstance(value.get("safe_ids"), Mapping):
        raise EvidenceError("safe_ids must be an object")
    log_hash = _require_string(value, "log_sha256")
    if not re.fullmatch(r"[0-9a-f]{64}", log_hash):
        raise EvidenceError("log_sha256 must be 64 lowercase hex characters")
    return value


def validate_manifest(manifest: Mapping[str, Any]) -> dict[str, Any]:
    """Validate release-level evidence without claiming a release is safe."""
    if not isinstance(manifest, Mapping):
        raise EvidenceError("manifest must be an object")
    value = dict(manifest)
    _reject_unsafe(value, "manifest")
    release_id = _require_string(value, "release_id")
    if not re.fullmatch(r"[0-9]{4}-[0-9]{2}-[0-9]{2}-[a-z0-9-]+", release_id):
        raise EvidenceError("release_id has invalid format")
    source_sha = _require_string(value, "source_sha")
    artifact_digest = _require_string(value, "artifact_digest")
    if not _HEX40.fullmatch(source_sha):
        raise EvidenceError("manifest source_sha is invalid")
    if not _SHA256.fullmatch(artifact_digest):
        raise EvidenceError("manifest artifact_digest is invalid")
    environment = _require_string(value, "environment")
    if environment not in _ENVIRONMENTS:
        raise EvidenceError("unknown manifest environment")
    decision = _require_string(value, "decision")
    if decision not in _DECISIONS:
        raise EvidenceError("unknown manifest decision")
    receipts = value.get("receipts")
    required_gates = value.get("required_gates")
    gates = value.get("gates")
    if not isinstance(receipts, list) or any(
        not isinstance(item, str)
        or Path(item).is_absolute()
        or ".." in Path(item).parts
        for item in receipts
    ):
        raise EvidenceError("receipts must contain safe relative paths")
    if not isinstance(required_gates, list) or any(
        not isinstance(item, str) for item in required_gates
    ):
        raise EvidenceError("required_gates must be a list of strings")
    if not isinstance(gates, Mapping):
        raise EvidenceError("gates must be an object")
    if decision == "go":
        missing = [
            gate for gate in required_gates if gates.get(gate) != "passed"
        ]
        if missing:
            raise EvidenceError(
                f"required gates not passed: {', '.join(missing)}"
            )
    return value


def hash_file(path: str | Path) -> str:
    """Return a lowercase SHA-256 digest for a local evidence file."""
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def write_receipt(
    path: str | Path, receipt: EvidenceReceipt | Mapping[str, Any]
) -> Path:
    """Validate and write one receipt as UTF-8 JSON."""
    value = validate_receipt(
        receipt.to_dict() if isinstance(receipt, EvidenceReceipt) else receipt
    )
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(
        json.dumps(value, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return target
