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


def test_scan_git_tracked_limits_git_ls_files_to_package_scope(
    tmp_path, monkeypatch
) -> None:
    repo_root = tmp_path
    package_root = repo_root / "graxia" / "packages" / "quant_os"
    tracked_file = package_root / "runtime" / "sample.txt"
    tracked_file.parent.mkdir(parents=True)
    tracked_file.write_text("safe text", encoding="utf-8")

    tracked_scope = package_root.relative_to(repo_root).as_posix()
    calls: dict[str, object] = {}
    scanned_paths: list[Path] = []

    def fake_run(args, capture_output, text, cwd):
        calls["args"] = args
        calls["cwd"] = cwd
        return subprocess.CompletedProcess(
            args=args,
            returncode=0,
            stdout=f"{tracked_file.relative_to(repo_root).as_posix()}\n",
            stderr="",
        )

    def fake_scan_file(filepath: Path) -> list[dict]:
        scanned_paths.append(filepath)
        return [{"file": filepath.relative_to(repo_root).as_posix()}]

    monkeypatch.setattr(secret_scan, "REPO_ROOT", repo_root)
    monkeypatch.setattr(secret_scan, "PACKAGE_ROOT", package_root)
    monkeypatch.setattr(secret_scan, "TRACKED_SCOPE", tracked_scope)
    monkeypatch.setattr(secret_scan.subprocess, "run", fake_run)
    monkeypatch.setattr(secret_scan, "scan_file", fake_scan_file)

    findings = secret_scan.scan_git_tracked()

    assert calls == {
        "args": ["git", "ls-files", "--", tracked_scope],
        "cwd": str(repo_root),
    }
    assert scanned_paths == [tracked_file]
    assert findings == [{"file": tracked_file.relative_to(repo_root).as_posix()}]


def test_scan_shadow_results_reads_only_package_local_json_and_log(
    tmp_path, monkeypatch
) -> None:
    repo_root = tmp_path
    package_root = repo_root / "graxia" / "packages" / "quant_os"
    package_shadow_results = package_root / "shadow_results"
    repo_shadow_results = repo_root / "shadow_results"
    package_shadow_results.mkdir(parents=True)
    repo_shadow_results.mkdir(parents=True)

    (package_shadow_results / "session.json").write_text(
        "Account: 1234567", encoding="utf-8"
    )
    (package_shadow_results / "events.log").write_text(
        "Account: 7654321", encoding="utf-8"
    )
    (package_shadow_results / "ignored.txt").write_text(
        "Account: 9999999", encoding="utf-8"
    )
    (repo_shadow_results / "repo_root.json").write_text(
        "Account: 5555555", encoding="utf-8"
    )

    monkeypatch.setattr(secret_scan, "REPO_ROOT", repo_root)
    monkeypatch.setattr(secret_scan, "PACKAGE_ROOT", package_root)
    monkeypatch.setattr(secret_scan, "SHADOW_RESULTS_DIR", package_shadow_results)

    findings = secret_scan.scan_shadow_results()
    scanned_files = sorted(Path(finding["file"]).as_posix() for finding in findings)

    assert scanned_files == [
        "graxia/packages/quant_os/shadow_results/events.log",
        "graxia/packages/quant_os/shadow_results/session.json",
    ]
    assert all(
        file.startswith("graxia/packages/quant_os/shadow_results/")
        for file in scanned_files
    )
