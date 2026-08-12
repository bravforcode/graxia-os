"""Secret scanner v2 — scans tracked files, logs, and artifacts for credentials.

Run before every commit to prevent credential leaks.
v2: Expanded pattern coverage — JWT, PEM keys, AWS keys, Telegram tokens, DB conn strings.
"""

import re
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).parent.parent.parent.parent

# --- CRITICAL patterns (real secrets) ---
SECRET_PATTERNS_CRITICAL = [
    (r'password\s*[=:]\s*["\'][^"\']*(?:muyrw|demo|pepper|mt5)[^"\']*["\']', "real password"),
    (r'password\s*[=:]\s*["\'][A-Za-z0-9!@#$%^&*]{8,}["\']', "long password string"),
    (r"-----BEGIN (RSA |EC )?PRIVATE KEY-----", "PEM private key"),
    (r"AKIA[0-9A-Z]{16}", "AWS access key"),
]

# --- HIGH patterns (likely secrets) ---
SECRET_PATTERNS_HIGH = [
    (r"eyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}", "JWT token"),
    (r"bot[0-9]+:[A-Za-z0-9_-]{35}", "Telegram bot token"),
    (r"://[^:]+:[^@]+@", "DB connection string with password"),
    (r"password=@password", "DB connection password placeholder"),
]

# --- MEDIUM patterns (potential secrets) ---
SECRET_PATTERNS_MEDIUM = [
    (r'secret_key\s*=\s*["\'][A-Za-z0-9+/=]{32,}["\']', "generic base64 secret"),
]

# Patterns that need redaction (account identifiers)
REDACT_PATTERNS = [
    (r"login\s*[=:]\s*(\d{7,})", "MT5 login/account ID"),
    (r"account_login\s*=\s*(\d{7,})", "MT5 account ID"),
    (r"Account:\s*(\d{7,})", "MT5 account in log"),
]

# Files to always skip
SKIP_FILES = {
    ".gitignore",
    "config.template.yaml",
    "secret_scan.py",
}

# Directories to skip
SKIP_DIRS = {".git", "__pycache__", "node_modules", ".pytest_cache"}


def scan_file(filepath: Path) -> list[dict]:
    """Scan a file for secrets."""
    findings = []
    if filepath.name in SKIP_FILES:
        return findings
    # Skip test fixtures — they use fake values
    if filepath.name.startswith("test_"):
        return findings
    if filepath.suffix in {".pyc", ".pyo", ".so", ".dll", ".exe"}:
        return findings

    try:
        content = filepath.read_text(encoding="utf-8", errors="ignore")
    except Exception:
        return findings

    for line_num, line in enumerate(content.splitlines(), 1):
        # Skip comments
        stripped = line.strip()
        if stripped.startswith("#"):
            continue

        # Check CRITICAL patterns
        for pattern, description in SECRET_PATTERNS_CRITICAL:
            if re.search(pattern, line, re.IGNORECASE):
                # Redact the matched secret — do not print actual values
                redacted = re.sub(r'(["\'])[^"\']+(["\'])', r"\1***REDACTED***\2", line.strip())
                findings.append(
                    {
                        "file": str(filepath.relative_to(REPO_ROOT)),
                        "line": line_num,
                        "pattern": description,
                        "redacted": redacted[:120],
                        "severity": "CRITICAL",
                    }
                )

        # Check HIGH patterns
        for pattern, description in SECRET_PATTERNS_HIGH:
            if re.search(pattern, line, re.IGNORECASE):
                redacted = re.sub(r'(["\'])[^"\']+(["\'])', r"\1***REDACTED***\2", line.strip())
                findings.append(
                    {
                        "file": str(filepath.relative_to(REPO_ROOT)),
                        "line": line_num,
                        "pattern": description,
                        "redacted": redacted[:120],
                        "severity": "HIGH",
                    }
                )

        # Check MEDIUM patterns
        for pattern, description in SECRET_PATTERNS_MEDIUM:
            if re.search(pattern, line, re.IGNORECASE):
                redacted = re.sub(r'(["\'])[^"\']+(["\'])', r"\1***REDACTED***\2", line.strip())
                findings.append(
                    {
                        "file": str(filepath.relative_to(REPO_ROOT)),
                        "line": line_num,
                        "pattern": description,
                        "redacted": redacted[:120],
                        "severity": "MEDIUM",
                    }
                )

        # Check for account identifiers needing redaction
        for pattern, description in REDACT_PATTERNS:
            match = re.search(pattern, line)
            if match:
                findings.append(
                    {
                        "file": str(filepath.relative_to(REPO_ROOT)),
                        "line": line_num,
                        "pattern": description,
                        "redacted": f"Account ID found: {match.group(1)[:3]}***",
                        "severity": "MEDIUM",
                    }
                )
    return findings


def scan_git_tracked() -> list[dict]:
    """Scan all git-tracked files."""
    findings = []
    try:
        result = subprocess.run(["git", "ls-files"], capture_output=True, text=True, cwd=str(REPO_ROOT))
        for line in result.stdout.splitlines():
            filepath = REPO_ROOT / line
            if filepath.exists():
                findings.extend(scan_file(filepath))
    except Exception as e:
        print(f"Error scanning git files: {e}")
    return findings


def scan_shadow_results() -> list[dict]:
    """Scan shadow_results directory."""
    findings = []
    results_dir = REPO_ROOT / "graxia" / "packages" / "quant_os" / "shadow_results"
    if not results_dir.exists():
        return findings
    for f in results_dir.glob("*.json"):
        findings.extend(scan_file(f))
    for f in results_dir.glob("*.log"):
        findings.extend(scan_file(f))
    return findings


def main():
    print("=" * 60)
    print("SECRET SCANNER")
    print("=" * 60)

    all_findings = []

    print("\n--- Git tracked files ---")
    git_findings = scan_git_tracked()
    all_findings.extend(git_findings)
    print(f"  {len(git_findings)} findings")

    print("\n--- Shadow results ---")
    results_findings = scan_shadow_results()
    all_findings.extend(results_findings)
    print(f"  {len(results_findings)} findings")

    # Print findings
    if all_findings:
        critical = [f for f in all_findings if f["severity"] == "CRITICAL"]
        high = [f for f in all_findings if f["severity"] == "HIGH"]
        medium = [f for f in all_findings if f["severity"] == "MEDIUM"]
        print(f"\n{'=' * 60}")
        print(f"FINDINGS: {len(critical)} CRITICAL, {len(high)} HIGH, {len(medium)} MEDIUM")
        print(f"{'=' * 60}")
        for f in all_findings:
            print(f"  [{f['severity']}] {f['file']}:{f['line']} [{f['pattern']}]")
            print(f"    {f['redacted']}")
        return 1 if critical else 0
    else:
        print(f"\n{'=' * 60}")
        print("CLEAN — no secrets found")
        print(f"{'=' * 60}")
        return 0


if __name__ == "__main__":
    sys.exit(main())
