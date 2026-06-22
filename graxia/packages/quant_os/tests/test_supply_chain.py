import pytest
import tempfile
import os
from pathlib import Path
from graxia.packages.quant_os.repo_intelligence.supply_chain import SupplyChainScanner, SBOMEntry

@pytest.fixture
def project_root():
    return str(Path(__file__).parent.parent)

@pytest.fixture
def scanner(project_root):
    return SupplyChainScanner(project_root)

class TestSupplyChainScanner:
    def test_scan_requirements_finds_file(self, scanner):
        entries = scanner.scan_requirements()
        assert isinstance(entries, list)

    def test_generate_sbom(self, scanner):
        report = scanner.generate_sbom()
        assert report.total_packages >= 0
        assert report.pinned_count >= 0
        assert report.generated_at is not None

    def test_verify_missing_lockfile(self, scanner):
        valid, msg = scanner.verify_lockfile("/nonexistent/lockfile.txt")
        assert valid is False
        assert "MISSING" in msg

    def test_verify_empty_lockfile(self, scanner):
        with tempfile.NamedTemporaryFile(mode='w', suffix='.txt', delete=False) as f:
            f.write("")
            f.flush()
            valid, msg = scanner.verify_lockfile(f.name)
            assert valid is False
            assert "EMPTY" in msg
        os.unlink(f.name)

    def test_verify_valid_lockfile(self, scanner):
        with tempfile.NamedTemporaryFile(mode='w', suffix='.txt', delete=False) as f:
            f.write("package==1.0.0\n")
            f.flush()
            valid, msg = scanner.verify_lockfile(f.name)
            assert valid is True
            assert "VALID" in msg
        os.unlink(f.name)

    def test_import_allowlist_clean(self, scanner):
        with tempfile.NamedTemporaryFile(mode='w', suffix='.py', delete=False) as f:
            f.write("import os\nimport json\n")
            f.flush()
            valid, msg = scanner.check_import_allowlist(f.name, ["os", "json"])
            assert valid is True
        os.unlink(f.name)

    def test_import_allowlist_violation(self, scanner):
        with tempfile.NamedTemporaryFile(mode='w', suffix='.py', delete=False) as f:
            f.write("import subprocess\nimport os\n")
            f.flush()
            valid, msg = scanner.check_import_allowlist(f.name, ["os", "json"])
            assert valid is False
            assert "VIOLATIONS" in msg
        os.unlink(f.name)

    def test_generate_report(self, scanner):
        report = scanner.generate_report()
        assert "total_packages" in report
        assert "pin_rate" in report
