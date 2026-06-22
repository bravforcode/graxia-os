from pathlib import Path
import subprocess

from graxia.packages.quant_os.scripts import secret_scan


def test_secret_scan_repo_root_matches_git_toplevel() -> None:
    result = subprocess.run(
        ["git", "rev-parse", "--show-toplevel"],
        cwd=Path(secret_scan.__file__).resolve().parent,
        capture_output=True,
        text=True,
        check=True,
    )

    assert secret_scan.REPO_ROOT == Path(result.stdout.strip())


def test_scan_artifacts_reads_package_artifacts(tmp_path, monkeypatch) -> None:
    repo_root = tmp_path
    package_root = repo_root / "graxia" / "packages" / "quant_os"
    artifacts_dir = package_root / "artifacts"
    artifacts_dir.mkdir(parents=True)
    (artifacts_dir / "sample.log").write_text("Account: 1234567", encoding="utf-8")

    monkeypatch.setattr(secret_scan, "REPO_ROOT", repo_root)
    monkeypatch.setattr(secret_scan, "PACKAGE_ROOT", package_root)
    monkeypatch.setattr(secret_scan, "ARTIFACTS_DIR", artifacts_dir)

    findings = secret_scan.scan_artifacts()

    assert findings
    assert findings[0]["file"].endswith("sample.log")
