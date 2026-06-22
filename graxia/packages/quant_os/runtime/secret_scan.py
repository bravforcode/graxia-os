"""Phase BE-P0 — Secret scan for tracked files."""
import re
import hashlib
from pathlib import Path


SECRET_PATTERNS = [
    (r'(?i)(password|passwd|pwd)\s*[=:]\s*["\']([^"\']+)["\']', 'plaintext_password'),
    (r'(?i)(api_key|apikey|api[-_]?secret)\s*[=:]\s*["\']([^"\']+)["\']', 'api_key'),
    (r'(?i)(token|bearer)\s*[=:]\s*["\']([^"\']+)["\']', 'token'),
    (r'(?i)(login|account)\s*[=:]\s*["\'](\d+)["\']', 'account_number'),
    (r'(?i)(server)\s*[=:]\s*["\']([^"\']+)["\']', 'server_name'),
    (r'sha256:[a-f0-9]{64}', 'possible_hash'),
    (r'MetaQuotes-Demo', 'broker_reference'),
    (r'(?i)(secret|credential|private_key)\s*[=:]\s*["\']([^"\']+)["\']', 'credential'),
]


class SecretScanner:
    def __init__(self, root: str):
        self.root = Path(root)
        self.findings: list[dict] = []

    def scan(self) -> list[dict]:
        """Scan all tracked files for secrets."""
        self.findings = []
        for path in self._get_tracked_files():
            try:
                content = path.read_text(encoding='utf-8', errors='ignore')
                for line_num, line in enumerate(content.splitlines(), 1):
                    self._check_line(path, line_num, line)
            except Exception:
                pass
        return self.findings

    def _get_tracked_files(self) -> list[Path]:
        """Get git tracked files (skip .git)."""
        files = []
        for p in self.root.rglob('*'):
            if '.git' in p.parts or '__pycache__' in p.parts:
                continue
            if p.is_file():
                files.append(p)
        return files

    def _check_line(self, path: Path, line_num: int, line: str) -> None:
        """Check line for secret patterns."""
        for pattern, category in SECRET_PATTERNS:
            if re.search(pattern, line):
                self.findings.append({
                    'file': str(path.relative_to(self.root)),
                    'line': line_num,
                    'category': category,
                    'content': line.strip()[:100],
                })

    def has_findings(self) -> bool:
        return len(self.findings) > 0

    def summary(self) -> dict:
        """Summarize findings by category."""
        summary = {}
        for f in self.findings:
            cat = f['category']
            summary[cat] = summary.get(cat, 0) + 1
        return summary

    def to_report(self) -> str:
        """Generate redacted report."""
        report = ["# Secret Scan Report\n"]
        report.append(f"Files scanned: {len(self._get_tracked_files())}")
        report.append(f"Findings: {len(self.findings)}\n")

        summary = self.summary()
        if summary:
            report.append("## By Category")
            for cat, count in sorted(summary.items()):
                report.append(f"- {cat}: {count}")

        report.append("\n## Details")
        for f in self.findings:
            redacted = f['content'][:20] + '...[REDACTED]'
            report.append(f"- {f['file']}:{f['line']} [{f['category']}] {redacted}")

        return '\n'.join(report)
