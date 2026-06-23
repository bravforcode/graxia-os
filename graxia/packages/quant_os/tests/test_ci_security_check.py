"""Unit tests for CI security check script."""
import os
import sys
import tempfile
import importlib.util

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(__file__)), "scripts"))

def _load_ci_script():
    spec = importlib.util.spec_from_file_location(
        "ci_security_check",
        os.path.join(os.path.dirname(os.path.dirname(__file__)), "scripts", "ci_security_check.py"),
    )
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_ci_scan_clean_file():
    mod = _load_ci_script()
    with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False) as f:
        f.write("# clean file\nx = 42\nprint(x)\n")
        fpath = f.name
    try:
        findings = mod.scan_file_for_secrets(fpath)
        assert findings == [], f"Expected 0 findings, got {len(findings)}: {findings}"
    finally:
        os.unlink(fpath)


def test_ci_scan_detects_password():
    mod = _load_ci_script()
    with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False) as f:
        f.write('password = "real_secret"\n')
        fpath = f.name
    try:
        findings = mod.scan_file_for_secrets(fpath)
        assert len(findings) == 1, f"Expected 1 finding, got {len(findings)}"
        assert findings[0]["pattern"] == "password_assignment"
    finally:
        os.unlink(fpath)


def test_ci_scan_forbidden_import():
    mod = _load_ci_script()
    with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False) as f:
        f.write("import metatrader5 as mt5\nmt5.order_send(...)\n")
        fpath = f.name
        fname = os.path.basename(fpath)

    # Temporarily register this temp file as a forbidden-import candidate
    # by creating a temp dir that looks like a regular module
    tmpdir = tempfile.mkdtemp()
    try:
        # Write a stub py file inside the temp dir so os.walk picks it up
        stub = os.path.join(tmpdir, "rogue_module.py")
        with open(stub, "w") as sf:
            sf.write("import metatrader5 as mt5\nmt5.order_send(...)\n")
        orig_root = mod.REPO_ROOT
        mod.REPO_ROOT = tmpdir
        try:
            findings = mod.scan_forbidden_order_imports()
        finally:
            mod.REPO_ROOT = orig_root
        assert len(findings) >= 1, f"Expected at least 1 finding, got {len(findings)}"
        assert any("order_send" in f["forbidden_import"] for f in findings)
    finally:
        import shutil
        shutil.rmtree(tmpdir)
        os.unlink(fpath)
