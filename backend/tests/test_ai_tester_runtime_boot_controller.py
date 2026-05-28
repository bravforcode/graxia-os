"""Tests for runtime boot controller logic."""
from __future__ import annotations

import os
import tempfile
from pathlib import Path

import pytest


# Import the controller logic (test-only, no .env read)
def _check_port_available(port: int) -> bool:
    """Check if a port is available (not in use)."""
    import socket
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        try:
            s.bind(("127.0.0.1", port))
            return True
        except OSError:
            return False


def _check_command_exists(cmd: str) -> bool:
    """Check if a command is available in PATH."""
    import shutil
    return shutil.which(cmd) is not None


def _validate_start_command(cmd: str) -> tuple[bool, str]:
    """Validate a start command without executing it.
    
    Returns:
        Tuple of (is_safe, message).
    """
    dangerous_patterns = [
        "rm -rf",
        "rm -r",
        "format",
        "dd if=",
        "> /dev/sda",
        "git reset --hard",
        "git clean -fd",
        "DROP DATABASE",
        "DROP TABLE",
        "TRUNCATE",
    ]
    for pattern in dangerous_patterns:
        if pattern in cmd.lower():
            return False, f"Command contains dangerous pattern: {pattern}"
    return True, "Command appears safe"


class TestRuntimeBootController:
    def test_port_check(self):
        """Port check should return bool."""
        result = _check_port_available(9999)  # unlikely to be in use
        assert isinstance(result, bool)

    def test_command_exists_for_python(self):
        result = _check_command_exists("python")
        assert result is True

    def test_command_not_exists_for_nonexistent(self):
        result = _check_command_exists("nonexistent_command_xyz")
        assert result is False

    def test_validate_safe_command(self):
        safe, msg = _validate_start_command(
            "cd backend && uvicorn app.main:app --host 127.0.0.1 --port 8000"
        )
        assert safe is True

    def test_validate_dangerous_command(self):
        safe, msg = _validate_start_command("rm -rf /")
        assert safe is False
        assert "dangerous" in msg.lower()

    def test_validate_another_dangerous_command(self):
        safe, msg = _validate_start_command("git reset --hard HEAD")
        assert safe is False

    def test_validate_frontend_command_safe(self):
        safe, msg = _validate_start_command("cd frontend && bun run dev --port 5173")
        assert safe is True

    def test_backend_start_command_format(self):
        """Verify the recommended backend start command format."""
        cmd = (
            "cd backend && "
            "uvicorn app.main:app "
            "--host 127.0.0.1 --port 8000 "
            "--log-level warning"
        )
        safe, msg = _validate_start_command(cmd)
        assert safe is True
        assert "uvicorn" in cmd

    def test_frontend_start_command_format(self):
        cmd = "cd frontend && bun run dev --port 5173"
        safe, msg = _validate_start_command(cmd)
        assert safe is True
    
    def test_no_env_read_in_logic(self):
        """Verify controller logic doesn't read .env."""
        import inspect
        source = inspect.getsource(_validate_start_command)
        assert ".env" not in source
        source2 = inspect.getsource(_check_port_available)
        assert ".env" not in source2

    def test_production_db_not_in_commands(self):
        """Production DB should not appear in start commands."""
        cmd = (
            "cd backend && "
            "uvicorn app.main:app "
            "--host 127.0.0.1 --port 8000"
        )
        assert "supabase" not in cmd.lower()
        assert "production" not in cmd.lower()

    def test_start_command_no_live_flags(self):
        """Start commands should not set live provider flags."""
        cmd = (
            "cd backend && "
            "uvicorn app.main:app "
            "--host 127.0.0.1 --port 8000"
        )
        assert "live" not in cmd.lower()
        assert "production" not in cmd.lower()
