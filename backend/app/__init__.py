"""Application package bootstrap."""

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

    # Python 3.12 can resolve platform machine/uname/win32_ver through a
    # slow or hanging WMI query on Windows. SQLAlchemy and asyncpg call these
    # during import, so keep startup deterministic.
    platform.machine = _safe_machine
    platform.win32_ver = _safe_win32_ver
    platform.uname = _safe_uname
