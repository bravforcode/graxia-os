"""Tests for repo_intelligence/hooks/pre_commit_security_check.py"""
import os
import subprocess
import sys
import textwrap
import tempfile

import pytest

HOOK_PATH = os.path.join(
    os.path.dirname(__file__), "..", "repo_intelligence", "hooks", "pre_commit_security_check.py"
)
HOOK_PATH = os.path.normpath(HOOK_PATH)


def _run_hook_on_file(filepath: str) -> tuple[int, str]:
    """Run the hook's run_check_on_file() on a local file, return (exit_code, output)."""
    result = subprocess.run(
        [sys.executable, HOOK_PATH, filepath],
        capture_output=True, text=True,
    )
    return result.returncode, result.stdout + result.stderr


@pytest.fixture
def tmp_py(tmp_path):
    """Create a temporary .py file in tmp_path and return its path."""
    def _make(name: str, content: str) -> str:
        p = tmp_path / name
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(textwrap.dedent(content), encoding="utf-8")
        return str(p)
    return _make


class TestHookCleanFile:
    def test_clean_file_exits_zero(self, tmp_py):
        path = tmp_py("clean.py", """
            x = 1
            y = 2
            def hello():
                return "world"
        """)
        code, output = _run_hook_on_file(path)
        assert code == 0, f"Expected exit 0, got {code}. Output:\n{output}"
        assert "OK" in output


class TestHookCatchesPassword:
    def test_password_with_value(self, tmp_py):
        path = tmp_py("bad.py", """
            password = "hunter2"
        """)
        code, output = _run_hook_on_file(path)
        assert code == 1, f"Expected exit 1, got {code}. Output:\n{output}"
        assert "password assignment" in output.lower() or "FAILED" in output


class TestHookAllowsEmptyPassword:
    def test_empty_password_not_flagged(self, tmp_py):
        path = tmp_py("ok.py", """
            password = ""
            password = ''
        """)
        code, output = _run_hook_on_file(path)
        assert code == 0, f"Expected exit 0, got {code}. Output:\n{output}"


class TestHookCatchesOrderSendOutsideAllowlist:
    def test_order_send_in_random_file(self, tmp_py):
        path = tmp_py("random.py", """
            from somewhere import order_send
            order_send(request)
        """)
        code, output = _run_hook_on_file(path)
        assert code == 1, f"Expected exit 1, got {code}. Output:\n{output}"
        assert "order_send" in output.lower() or "FAILED" in output


class TestHookAllowsOrderSendInAllowlist:
    def test_order_send_in_execution_demo_canary(self, tmp_py):
        path = tmp_py("execution/demo_canary/trade.py", """
            from somewhere import order_send
            order_send(request)
        """)
        code, output = _run_hook_on_file(path)
        assert code == 0, f"Expected exit 0, got {code}. Output:\n{output}"
        assert "OK" in output
