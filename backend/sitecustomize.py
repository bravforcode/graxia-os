"""Interpreter startup guards for local backend commands."""

from __future__ import annotations

import os
import platform


if os.name == "nt":
    def _safe_machine() -> str:
        return os.environ.get("PROCESSOR_ARCHITECTURE") or "AMD64"

    def _safe_win32_ver(*_: object, **__: object) -> tuple[str, str, str, str]:
        return (os.environ.get("OS_VERSION") or "10", "", "", "")

    def _safe_uname() -> platform.uname_result:
        return platform.uname_result(
            "Windows",
            os.environ.get("COMPUTERNAME") or "",
            _safe_win32_ver()[0],
            "",
            _safe_machine(),
        )

    platform.machine = _safe_machine
    platform.win32_ver = _safe_win32_ver
    platform.uname = _safe_uname
