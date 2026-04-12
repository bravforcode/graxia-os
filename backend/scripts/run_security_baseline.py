#!/usr/bin/env python3
from __future__ import annotations

import json
import shutil
import subprocess
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
REPORTS_DIR = REPO_ROOT / "reports"

TOOLS = {
    "bandit": ["bandit", "-r", "backend", "-f", "json", "-o", "reports/bandit-baseline.json", "--severity-level", "low"],
    "semgrep_python": [
        "semgrep",
        "--config=p/python",
        "--config=p/jwt",
        "--config=p/secrets",
        "--config=p/sqlalchemy",
        "--json",
        "-o",
        "reports/semgrep-baseline.json",
        "backend",
    ],
    "pip_audit": ["pip-audit", "--format", "json", "-o", "reports/pip-audit-baseline.json"],
    "gitleaks": ["gitleaks", "detect", "--source", ".", "--report-format", "json", "--report-path", "reports/gitleaks-baseline.json"],
    "trufflehog": ["trufflehog", "filesystem", ".", "--json"],
    "npm_audit": ["npm", "audit", "--json"],
}


def main() -> int:
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    manifest: dict[str, object] = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "repo_root": str(REPO_ROOT),
        "tools": {},
    }

    for name, command in TOOLS.items():
        binary = command[0]
        if shutil.which(binary) is None:
            manifest["tools"][name] = {
                "status": "missing_tool",
                "command": command,
            }
            continue
        try:
            result = subprocess.run(
                command,
                cwd=REPO_ROOT,
                capture_output=True,
                text=True,
                timeout=1800,
                check=False,
            )
            manifest["tools"][name] = {
                "status": "completed" if result.returncode == 0 else "nonzero_exit",
                "command": command,
                "returncode": result.returncode,
                "stdout_tail": result.stdout[-500:],
                "stderr_tail": result.stderr[-500:],
            }
        except FileNotFoundError:
            manifest["tools"][name] = {
                "status": "missing_tool",
                "command": command,
            }
        except subprocess.TimeoutExpired:
            manifest["tools"][name] = {
                "status": "timeout",
                "command": command,
            }

    (REPORTS_DIR / "security-baseline-manifest.json").write_text(
        json.dumps(manifest, indent=2),
        encoding="utf-8",
    )
    print(f"Wrote {REPORTS_DIR / 'security-baseline-manifest.json'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
