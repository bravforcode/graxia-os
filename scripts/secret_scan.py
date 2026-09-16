"""Run a redacted, read-only secret scan over repository working trees/history.

The scanner reports rule IDs, paths, line numbers, and commit references only.
It never prints or writes matched values. A clean result means no matching
rules were found in the scanned scope; it is not a guarantee that a repository
contains no secrets.
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable


class SecretScanError(ValueError):
    """Raised when a repository cannot be scanned safely."""


MAX_FILE_BYTES = 2 * 1024 * 1024
MAX_HISTORY_ENTRIES = 5000
MAX_HISTORY_COMMITS = 100
_HEX40 = re.compile(r"^[0-9a-f]{40}$")
_SENSITIVE_NAME = re.compile(
    r"(?:^|/)(?:\.env(?:\..*)?|.*\.(?:pem|key|p12|pfx|jks)|"
    r".*(?:credential|token|password)[-_].*|.*\.bak(?:kup)?)$",
    re.IGNORECASE,
)
_RULES: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("stripe-key", re.compile(r"\b(?:sk|rk)_(?:live|test)_[A-Za-z0-9]{8,}\b")),
    ("github-token", re.compile(r"\b(?:ghp|gho|ghu|ghs|ghr)_[A-Za-z0-9]{20,}\b")),
    ("github-pat", re.compile(r"\bgithub_pat_[A-Za-z0-9_]{20,}\b")),
    ("aws-access-key", re.compile(r"\bAKIA[0-9A-Z]{16}\b")),
    ("google-api-key", re.compile(r"\bAIza[0-9A-Za-z_-]{20,}\b")),
    (
        "private-key",
        re.compile(r"-----BEGIN [A-Z0-9 ]+ PRIVATE KEY-----"),
    ),
    (
        "generic-secret-assignment",
        re.compile(
            r"(?i)\b(?:api[_-]?key|client[_-]?secret|secret|token|password)"
            r"\s*[:=]\s*[\"']?[A-Za-z0-9_./+=-]{12,}"
        ),
    ),
)
_GREP_PATTERNS: tuple[tuple[str, str], ...] = (
    ("stripe-key", r"(sk|rk)_(live|test)_[A-Za-z0-9]{8,}"),
    ("github-token", r"(ghp|gho|ghu|ghs|ghr)_[A-Za-z0-9]{20,}"),
    ("github-pat", r"github_pat_[A-Za-z0-9_]{20,}"),
    ("aws-access-key", r"AKIA[0-9A-Z]{16}"),
    ("google-api-key", r"AIza[0-9A-Za-z_-]{20,}"),
    ("private-key", r"BEGIN [A-Z0-9 ]+ PRIVATE KEY"),
    (
        "generic-secret-assignment",
        r"(api[_-]?key|client[_-]?secret|secret|token|password)[[:space:]]*[:=][[:space:]]*[\"']?[A-Za-z0-9_./+=-]{12,}",
    ),
)
_SKIP_IGNORED_PARTS = {
    ".git",
    ".venv",
    "venv",
    "node_modules",
    "__pycache__",
    ".pytest_cache",
    "coverage",
    "dist",
    "build",
}


def _run_git(root: Path, *args: str, timeout: int = 60) -> str:
    try:
        result = subprocess.run(
            ["git", "-C", str(root), *args],
            check=True,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        raise SecretScanError(f"git scan command failed: {args[0]}") from exc
    return result.stdout


def _validate_repo(root: Path) -> Path:
    target = root.expanduser().resolve()
    if not target.is_dir():
        raise SecretScanError(f"repository directory does not exist: {target}")
    _run_git(target, "rev-parse", "--show-toplevel")
    return target


def _is_sensitive_name(relative: str) -> bool:
    normalized = relative.replace("\\", "/")
    return bool(_SENSITIVE_NAME.search(normalized))


def _candidate_paths(
    root: Path,
    *,
    include_untracked: bool = False,
    include_ignored_sensitive: bool = False,
) -> list[tuple[Path, str]]:
    """Return tracked files, optionally adding untracked and ignored candidates."""
    visible_args = ["ls-files", "--cached"]
    if include_untracked:
        visible_args.extend(["--others", "--exclude-standard"])
    visible_args.append("-z")
    visible = _run_git(root, *visible_args)
    candidates: dict[str, str] = {}
    for raw in visible.split("\0"):
        if raw:
            candidates[raw] = "working-tree"
    if include_ignored_sensitive:
        ignored = _run_git(
            root, "ls-files", "--others", "--ignored", "--exclude-standard", "-z"
        )
        for raw in ignored.split("\0"):
            if raw and _is_sensitive_name(raw):
                candidates[raw] = "ignored-sensitive-name"

    result: list[tuple[Path, str]] = []
    for relative, source in sorted(candidates.items()):
        path = (root / relative).resolve()
        try:
            path.relative_to(root)
        except ValueError as exc:
            raise SecretScanError(f"candidate escapes repository: {relative}") from exc
        if any(part in _SKIP_IGNORED_PARTS for part in path.relative_to(root).parts):
            continue
        if path.is_file() and not path.is_symlink():
            result.append((path, source))
    return result


def _decode_text(data: bytes) -> str | None:
    if b"\0" in data[:8192]:
        return None
    try:
        return data.decode("utf-8")
    except UnicodeDecodeError:
        return data.decode("utf-8", errors="replace")


def _scan_text(
    text: str,
    *,
    scope: str,
    path: str,
    reference: str | None,
) -> list[dict[str, Any]]:
    findings: list[dict[str, Any]] = []
    for line_number, line in enumerate(text.splitlines(), start=1):
        for rule, pattern in _RULES:
            if pattern.search(line):
                findings.append(
                    {
                        "scope": scope,
                        "path": path,
                        "reference": reference,
                        "rule": rule,
                        "line": line_number,
                    }
                )
    return findings


def _read_for_scan(path: Path) -> str | None:
    try:
        if path.stat().st_size > MAX_FILE_BYTES:
            return None
        return _decode_text(path.read_bytes())
    except OSError as exc:
        raise SecretScanError(f"cannot read scan candidate: {path}") from exc


def _tracked_findings(root: Path) -> list[dict[str, Any]]:
    """Use the Git index/worktree search without materializing every file in Python."""
    findings: list[dict[str, Any]] = []
    for rule, pattern in _GREP_PATTERNS:
        try:
            result = subprocess.run(
                [
                    "git",
                    "-C",
                    str(root),
                    "grep",
                    "--full-name",
                    "-I",
                    "-n",
                    "-E",
                    pattern,
                    "--",
                    ".",
                ],
                check=False,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=180,
            )
        except (OSError, subprocess.SubprocessError) as exc:
            raise SecretScanError(f"git tracked-file scan failed: {rule}") from exc
        if result.returncode not in (0, 1):
            raise SecretScanError(f"git tracked-file scan failed: {rule}")
        for raw in result.stdout.splitlines():
            path, separator, tail = raw.partition(":")
            line, line_separator, _ = tail.partition(":")
            if not separator or not line_separator or not line.isdigit():
                continue
            findings.append(
                {
                    "scope": "working-tree",
                    "path": path.replace("\\", "/"),
                    "reference": None,
                    "rule": rule,
                    "line": int(line),
                }
            )
    return findings


_OBJECT_ID = re.compile(r"^[0-9a-f]{40,64}$")


def _history_object_paths(root: Path, *, max_commits: int) -> dict[str, str]:
    """Return one safe path for each reachable Git object with a path."""
    output = _run_git(
        root,
        "rev-list",
        "--objects",
        "--max-count",
        str(max_commits),
        "--all",
        timeout=180,
    )
    objects: dict[str, str] = {}
    for line in output.splitlines():
        object_id, separator, relative = line.partition(" ")
        relative = relative.replace("\\", "/")
        if (
            separator
            and _OBJECT_ID.fullmatch(object_id)
            and relative
            and not any(part in _SKIP_IGNORED_PARTS for part in Path(relative).parts)
        ):
            objects.setdefault(object_id, relative)
    return objects


def _batch_blob_sizes(root: Path, object_ids: Iterable[str]) -> dict[str, int]:
    payload = "".join(f"{object_id}\n" for object_id in object_ids)
    try:
        result = subprocess.run(
            ["git", "-C", str(root), "cat-file", "--batch-check"],
            input=payload,
            check=True,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=180,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        raise SecretScanError("git blob metadata scan failed") from exc
    sizes: dict[str, int] = {}
    for line in result.stdout.splitlines():
        parts = line.split()
        if len(parts) != 3 or parts[1] != "blob" or not parts[2].isdigit():
            continue
        sizes[parts[0]] = int(parts[2])
    return sizes


def _history_findings(
    root: Path, *, max_entries: int, max_commits: int
) -> tuple[list[dict[str, Any]], int, bool]:
    """Scan reachable blobs in one batch; references are blob IDs, never values."""
    objects = _history_object_paths(root, max_commits=max_commits)
    sizes = _batch_blob_sizes(root, objects)
    candidates = [
        (object_id, objects[object_id], size)
        for object_id, size in sizes.items()
        if object_id in objects and size <= MAX_FILE_BYTES
    ]
    selected = candidates[:max_entries]
    truncated = len(candidates) > len(selected)
    findings: list[dict[str, Any]] = []
    process = subprocess.Popen(
        ["git", "-C", str(root), "cat-file", "--batch"],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    try:
        if process.stdin is None or process.stdout is None:
            raise SecretScanError("git blob content scan did not open pipes")
        for object_id, relative, expected_size in selected:
            process.stdin.write(f"{object_id}\n".encode("ascii"))
            process.stdin.flush()
            header = process.stdout.readline().decode("ascii", errors="replace").strip()
            parts = header.split()
            if len(parts) != 3 or parts[1] != "blob" or not parts[2].isdigit():
                continue
            size = int(parts[2])
            data = process.stdout.read(size)
            process.stdout.read(1)
            if size != expected_size:
                continue
            text = _decode_text(data)
            if text is not None:
                findings.extend(
                    _scan_text(
                        text,
                        scope="history",
                        path=relative,
                        reference=object_id,
                    )
                )
    finally:
        if process.stdin is not None:
            process.stdin.close()
        try:
            process.wait(timeout=30)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait(timeout=5)
    return findings, len(selected), truncated


def scan_repository(
    root: str | Path,
    *,
    include_history: bool = False,
    max_history_entries: int = MAX_HISTORY_ENTRIES,
    max_history_commits: int = MAX_HISTORY_COMMITS,
    include_untracked: bool = False,
    include_ignored_sensitive: bool = False,
) -> dict[str, Any]:
    target = _validate_repo(Path(root))
    top_level = Path(_run_git(target, "rev-parse", "--show-toplevel").strip()).resolve()
    if include_untracked or include_ignored_sensitive:
        findings: list[dict[str, Any]] = []
        scanned_files = 0
        for path, source in _candidate_paths(
            top_level,
            include_untracked=include_untracked,
            include_ignored_sensitive=include_ignored_sensitive,
        ):
            text = _read_for_scan(path)
            if text is None:
                continue
            scanned_files += 1
            relative = path.relative_to(top_level).as_posix()
            findings.extend(
                _scan_text(text, scope="working-tree", path=relative, reference=None)
            )
    else:
        findings = _tracked_findings(top_level)
        scanned_files = None

    history_entries_scanned = 0
    history_truncated = False
    if include_history:
        history_findings, history_entries_scanned, history_truncated = _history_findings(
            top_level,
            max_entries=max_history_entries,
            max_commits=max_history_commits,
        )
        findings.extend(history_findings)

    unique_findings = sorted(
        {
            (
                finding["scope"],
                finding["path"],
                finding["reference"],
                finding["rule"],
                finding["line"],
            ): finding
            for finding in findings
        }.values(),
        key=lambda finding: (
            finding["scope"],
            finding["path"],
            finding["reference"] or "",
            finding["line"],
            finding["rule"],
        ),
    )
    return {
        "repository": str(top_level),
        "head": _run_git(top_level, "rev-parse", "HEAD").strip(),
        "working_tree_files_scanned": scanned_files,
        "working_tree_scope": "tracked-plus-untracked"
        if include_untracked
        else "tracked-files-only",
        "ignored_sensitive_names_requested": include_ignored_sensitive,
        "history_entries_scanned": history_entries_scanned,
        "history_blob_limit": max_history_entries if include_history else None,
        "history_commit_limit": max_history_commits if include_history else None,
        "history_truncated": history_truncated,
        "history_reference_kind": "reachable Git blob SHA; line=0 means line was not resolved",
        "findings": unique_findings,
        "status": "findings" if unique_findings else "no-findings-in-scanned-scope",
    }


def build_report(
    repositories: Iterable[str | Path],
    *,
    include_history: bool = False,
    max_history_entries: int = MAX_HISTORY_ENTRIES,
    max_history_commits: int = MAX_HISTORY_COMMITS,
    include_untracked: bool = False,
    include_ignored_sensitive: bool = False,
) -> dict[str, Any]:
    reports = [
        scan_repository(
            repository,
            include_history=include_history,
            max_history_entries=max_history_entries,
            max_history_commits=max_history_commits,
            include_untracked=include_untracked,
            include_ignored_sensitive=include_ignored_sensitive,
        )
        for repository in repositories
    ]
    return {
        "schema_version": 1,
        "generated_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
        "history_requested": include_history,
        "repositories": reports,
        "finding_count": sum(len(report["findings"]) for report in reports),
        "status": "findings" if any(report["findings"] for report in reports) else "no-findings-in-scanned-scope",
        "disclaimer": "No findings means no matching rules in the scanned scope; it does not prove secret-free history.",
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", action="append", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--history", action="store_true")
    parser.add_argument("--max-history-entries", type=int, default=MAX_HISTORY_ENTRIES)
    parser.add_argument("--max-history-commits", type=int, default=MAX_HISTORY_COMMITS)
    parser.add_argument("--include-untracked", action="store_true")
    parser.add_argument("--include-ignored-sensitive", action="store_true")
    args = parser.parse_args(argv)
    try:
        if args.max_history_entries < 1 or args.max_history_commits < 1:
            raise SecretScanError("history limits must be positive")
        report = build_report(
            args.repo,
            include_history=args.history,
            max_history_entries=args.max_history_entries,
            max_history_commits=args.max_history_commits,
            include_untracked=args.include_untracked,
            include_ignored_sensitive=args.include_ignored_sensitive,
        )
        output = Path(args.output)
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        print(
            json.dumps(
                {
                    "status": "ok",
                    "finding_count": report["finding_count"],
                    "output": str(output),
                },
                sort_keys=True,
            )
        )
        return 0
    except (SecretScanError, OSError, ValueError) as exc:
        print(json.dumps({"status": "error", "error": str(exc)}), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
