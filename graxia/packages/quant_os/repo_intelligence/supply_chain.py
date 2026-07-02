import hashlib
from pathlib import Path
from dataclasses import dataclass, field
from datetime import datetime

@dataclass
class SBOMEntry:
    package_name: str
    version: str
    license: str
    hash_sha256: str
    source: str
    pinned_commit: str = ""
    vulnerability_status: str = "UNKNOWN"

@dataclass
class SupplyChainReport:
    generated_at: str
    total_packages: int
    pinned_count: int
    unpinned_packages: list[str] = field(default_factory=list)
    vulnerability_scan_results: dict = field(default_factory=dict)

class SupplyChainScanner:
    def __init__(self, project_root: str):
        self._root = Path(project_root)

    def scan_requirements(self) -> list[SBOMEntry]:
        entries = []
        req_file = self._root / "requirements.txt"
        if req_file.exists():
            for line in req_file.read_text().splitlines():
                line = line.strip()
                if not line or line.startswith("#"):
                    continue
                if "==" in line:
                    name, version = line.split("==", 1)
                    entries.append(SBOMEntry(
                        package_name=name.strip(),
                        version=version.strip(),
                        license="UNKNOWN",
                        hash_sha256=hashlib.sha256(line.encode()).hexdigest(),
                        source="requirements.txt"
                    ))
                else:
                    entries.append(SBOMEntry(
                        package_name=line.strip(),
                        version="UNPINNED",
                        license="UNKNOWN",
                        hash_sha256="",
                        source="requirements.txt"
                    ))
        return entries

    def generate_sbom(self) -> SupplyChainReport:
        entries = self.scan_requirements()
        unpinned = [e.package_name for e in entries if e.version == "UNPINNED"]
        return SupplyChainReport(
            generated_at=datetime.utcnow().isoformat(),
            total_packages=len(entries),
            pinned_count=len(entries) - len(unpinned),
            unpinned_packages=unpinned
        )

    def verify_lockfile(self, lockfile_path: str) -> tuple[bool, str]:
        path = Path(lockfile_path)
        if not path.exists():
            return False, f"LOCKFILE_MISSING:{lockfile_path}"
        content = path.read_text()
        if not content.strip():
            return False, f"LOCKFILE_EMPTY:{lockfile_path}"
        file_hash = hashlib.sha256(content.encode()).hexdigest()
        return True, f"LOCKFILE_VALID:{file_hash[:16]}"

    def check_import_allowlist(self, module_path: str, allowed_modules: list[str]) -> tuple[bool, str]:
        path = Path(module_path)
        if not path.exists():
            return False, f"MODULE_NOT_FOUND:{module_path}"
        content = path.read_text()
        import ast
        try:
            tree = ast.parse(content)
        except SyntaxError:
            return False, f"SYNTAX_ERROR:{module_path}"

        violations = []
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    if not any(alias.name.startswith(m) for m in allowed_modules):
                        violations.append(alias.name)
            elif isinstance(node, ast.ImportFrom):
                if node.module and not any(node.module.startswith(m) for m in allowed_modules):
                    violations.append(node.module)

        if violations:
            return False, f"IMPORT_VIOLATIONS:{','.join(violations[:5])}"
        return True, "ALLOWLIST_OK"

    def generate_report(self) -> dict:
        sbom = self.generate_sbom()
        return {
            "generated_at": sbom.generated_at,
            "total_packages": sbom.total_packages,
            "pinned_count": sbom.pinned_count,
            "unpinned_packages": sbom.unpinned_packages,
            "pin_rate": sbom.pinned_count / sbom.total_packages if sbom.total_packages > 0 else 0,
        }
