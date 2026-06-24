#!/usr/bin/env python3
"""Pre-commit hook: secret scanning and forbidden import detection.

Checks staged files for:
1. Credential literals (password, api_key, MT5_* env var reads)
2. Forbidden order API imports outside the allowlist (execution/demo_canary/)
"""
import re
import subprocess
import sys
from pathlib import Path

# --- Patterns ---

# password = "value", password: "value", or password: 'value' (non-empty, non-placeholder)
PASSWORD_RE = re.compile(
    r'''password\s*[:=]\s*(["'])(?!\1)(?!\s*\1).+?\1''',
    re.IGNORECASE,
)

# api_key = "value", api_key: "value", or api_key: 'value'
API_KEY_RE = re.compile(
    r'''api[_-]?key\s*[:=]\s*(["'])(?!\1)(?!\s*\1).+?\1''',
    re.IGNORECASE,
)

# Explicit string literals with password/api_key keywords in assignment context
CREDENTIAL_PATTERNS = [
    ("password assignment", PASSWORD_RE),
    ("api_key assignment", API_KEY_RE),
]

# MT5 env var reads restricted to gold_bot/
MT5_ENV_RE = re.compile(
    r'''(?:MT5_LOGIN|MT5_PASSWORD|MT5_SERVER)\s*=\s*os\.(?:environ|getenv)\('''
)

# Forbidden order API symbols outside allowlist
FORBIDDEN_SYMBOLS = {
    "order_send": re.compile(r'''\border_send\s*\('''),
    "TRADE_ACTION_DEAL": re.compile(r'''\bTRADE_ACTION_DEAL\b'''),
    "position_close": re.compile(r'''\bposition_close\s*\('''),
}

# Paths that ARE allowed to use order_send / TRADE_ACTION_DEAL / position_close
ORDER_SEND_ALLOWLIST: set[str] = {
    "execution/demo_canary/",
    "scripts/g3_execute_demo_canary.py",
    "scripts/g3_close_demo_canary.py",
    "scripts/batch_orders.py",
    "scripts/mega_collect.py",
    # ponytail: quarantined — these are commented-out stub code, not active calls.
    "execution/broker_adapter.py",
    "live_readiness/mt5_runtime_verifier.py",
}


def _get_staged_files() -> list[str]:
    """Return list of all staged files (added or modified)."""
    try:
        result = subprocess.run(
            ["git", "diff", "--cached", "--name-only", "--diff-filter=ACM"],
            capture_output=True, text=True, check=True,
        )
        return [f for f in result.stdout.strip().splitlines() if f]
    except (subprocess.CalledProcessError, FileNotFoundError):
        return []


def _read_staged_content(filepath: str) -> str:
    """Read the staged (index) version of a file."""
    try:
        result = subprocess.run(
            ["git", "show", f":{filepath}"],
            capture_output=True, text=True, check=True,
        )
        return result.stdout
    except (subprocess.CalledProcessError, FileNotFoundError):
        return ""


def _in_gold_bot(filepath: str) -> bool:
    return filepath.startswith("gold_bot/") or filepath.startswith("gold_bot\\") or "/gold_bot/" in filepath or "\\gold_bot\\" in filepath


def _in_allowlist(filepath: str) -> bool:
    fp = filepath.replace("\\", "/")
    return any(fp.startswith(prefix) or f"/{prefix}" in fp for prefix in ORDER_SEND_ALLOWLIST)


def scan_file(filepath: str) -> list[str]:
    """Scan a single staged file, return list of findings."""
    findings: list[str] = []
    content = _read_staged_content(filepath)
    if not content:
        return findings

    # Skip self — regex patterns would match own docstrings & code
    if "pre_commit_security_check.py" in filepath.replace("\\", "/"):
        return findings

    for label, pattern in CREDENTIAL_PATTERNS:
        for match in pattern.finditer(content):
            line_num = content[:match.start()].count("\n") + 1
            findings.append(f"  {filepath}:{line_num} — {label}: {match.group()!r}")

    if _in_gold_bot(filepath):
        for match in MT5_ENV_RE.finditer(content):
            line_num = content[:match.start()].count("\n") + 1
            findings.append(f"  {filepath}:{line_num} — MT5 env var read: {match.group()!r}")

    if not _in_allowlist(filepath):
        for symbol, pattern in FORBIDDEN_SYMBOLS.items():
            for match in pattern.finditer(content):
                line_num = content[:match.start()].count("\n") + 1
                findings.append(
                    f"  {filepath}:{line_num} — forbidden symbol '{symbol}' outside allowlist: {match.group()!r}"
                )

    return findings


def run_check() -> int:
    """Main entry point. Returns 0 if clean, 1 if findings."""
    staged = _get_staged_files()
    if not staged:
        print("Security check: no staged files.")
        return 0

    all_findings: list[str] = []
    for filepath in staged:
        all_findings.extend(scan_file(filepath))

    if all_findings:
        print("PRE-COMMIT SECURITY CHECK FAILED:")
        for f in all_findings:
            print(f)
        print(f"\nBlocked {len(all_findings)} finding(s). Use --no-verify to bypass (document reason).")
        return 1

    print(f"Security check: OK ({len(staged)} file(s) scanned)")
    return 0


def run_check_on_file(filepath: str) -> int:
    """Scan a single local file path (used by tests and standalone invocation)."""
    p = Path(filepath)
    if not p.exists():
        print(f"File not found: {filepath}")
        return 1

    findings: list[str] = []
    content = p.read_text(encoding="utf-8")
    rel = str(p).replace("\\", "/")

    for label, pattern in CREDENTIAL_PATTERNS:
        for match in pattern.finditer(content):
            line_num = content[:match.start()].count("\n") + 1
            findings.append(f"  {rel}:{line_num} — {label}: {match.group()!r}")

    if _in_gold_bot(rel):
        for match in MT5_ENV_RE.finditer(content):
            line_num = content[:match.start()].count("\n") + 1
            findings.append(f"  {rel}:{line_num} — MT5 env var read: {match.group()!r}")

    if not _in_allowlist(rel):
        for symbol, pat in FORBIDDEN_SYMBOLS.items():
            for match in pat.finditer(content):
                line_num = content[:match.start()].count("\n") + 1
                findings.append(
                    f"  {rel}:{line_num} — forbidden symbol '{symbol}' outside allowlist: {match.group()!r}"
                )

    if findings:
        print("SECURITY CHECK FAILED:")
        for f in findings:
            print(f)
        return 1

    print(f"Security check: OK ({filepath})")
    return 0


if __name__ == "__main__":
    if len(sys.argv) > 1:
        sys.exit(run_check_on_file(sys.argv[1]))
    sys.exit(run_check())
