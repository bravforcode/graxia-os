"""Correctness-first quality gate for context packs."""
from __future__ import annotations

from dataclasses import dataclass, field

from app.context_engine.critical_policy import (
    get_critical_reason,
    is_aggressive_content_mode,
)
from app.context_engine.schemas import ContextPack


@dataclass
class QualityGateFinding:
    code: str
    message: str
    path: str | None = None
    severity: str = "error"


@dataclass
class QualityGateResult:
    passed: bool
    findings: list[QualityGateFinding] = field(default_factory=list)
    checked_paths: list[str] = field(default_factory=list)
    critical_paths: list[str] = field(default_factory=list)
    policy_version: str = "2026-05-26"


def evaluate_context_pack(
    pack: ContextPack,
    *,
    required_paths: list[str] | None = None,
    expected_error_text: str | None = None,
    policy_version: str = "2026-05-26",
) -> QualityGateResult:
    findings: list[QualityGateFinding] = []
    included_paths = {file.path for file in pack.included_files}
    diff_paths = {diff.path for diff in pack.diffs}
    checked_paths = sorted(included_paths | diff_paths)
    critical_paths: list[str] = []

    for file in pack.included_files:
        if ".env" in file.path.lower():
            findings.append(
                QualityGateFinding(
                    code="SECRET_PATH_INCLUDED",
                    message="Context pack included an .env path.",
                    path=file.path,
                )
            )
        reason = get_critical_reason(file.path)
        if reason:
            critical_paths.append(file.path)
            if is_aggressive_content_mode(file.content_mode):
                findings.append(
                    QualityGateFinding(
                        code="CRITICAL_FILE_AGGRESSIVE_COMPRESSION",
                        message=f"Critical file used aggressive mode ({file.content_mode}) via {reason}.",
                        path=file.path,
                    )
                )

    for required_path in required_paths or []:
        normalized = required_path.replace("\\", "/")
        if normalized not in included_paths and normalized not in diff_paths:
            findings.append(
                QualityGateFinding(
                    code="MISSING_REQUIRED_PATH",
                    message=f"Required path missing from context pack: {normalized}",
                    path=normalized,
                )
            )

    if expected_error_text:
        haystacks: list[str] = []
        for file in pack.included_files:
            if file.content:
                haystacks.append(file.content)
            if file.summary:
                haystacks.append(file.summary)
        for diff in pack.diffs:
            if diff.diff_text:
                haystacks.append(diff.diff_text)
            if diff.diff_summary:
                haystacks.append(diff.diff_summary)
        if not any(expected_error_text in text for text in haystacks):
            findings.append(
                QualityGateFinding(
                    code="MISSING_ERROR_MESSAGE",
                    message=f"Expected error text not found: {expected_error_text}",
                )
            )

    return QualityGateResult(
        passed=not findings,
        findings=findings,
        checked_paths=checked_paths,
        critical_paths=sorted(set(critical_paths)),
        policy_version=policy_version,
    )
