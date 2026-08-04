"""Per-symbol measurement coverage state machine (Phase 1).

Pure logic, no MT5 dependency: classifies ticks into the five named sessions,
counts qualifying days (5/5 sessions covered, >= 50,000 VALID ticks per
session-day, no GAP inside a session), tracks which pass each qualifying day
counts toward, and persists state to disk so daemon restarts never lose
day-6 progress.
"""

from __future__ import annotations

import contextlib
import json
import os
import tempfile
import time as _time
from dataclasses import dataclass
from datetime import date, datetime, time
from pathlib import Path
from typing import Any

SESSION_NAMES: tuple[str, ...] = (
    "asian",
    "london",
    "london_ny_overlap",
    "ny",
    "rollover",
)
SESSIONS_PER_DAY: int = 5
QUALIFYING_DAYS: int = 7
MIN_VALID_TICKS_PER_SESSION_DAY: int = 50_000

# Canonical UTC windows. Per-symbol overrides are supported via the
# SessionClassifier(session_windows=...) constructor argument.
DEFAULT_SESSION_WINDOWS: dict[str, tuple[time, time]] = {
    "asian": (time(0, 0), time(7, 0)),
    "london": (time(7, 0), time(12, 0)),
    "london_ny_overlap": (time(12, 0), time(16, 0)),
    "ny": (time(16, 0), time(21, 0)),
    "rollover": (time(21, 0), time(23, 59, 59)),
}


class SessionClassifier:
    """Classify a UTC timestamp into one of the five sessions, or None."""

    def __init__(self, session_windows: dict[str, tuple[time, time]] | None = None):
        self._windows = dict(DEFAULT_SESSION_WINDOWS if session_windows is None else session_windows)

    def classify(self, timestamp_utc: datetime) -> str | None:
        """Return the session name for the timestamp, or None on weekends or
        outside all windows."""
        if timestamp_utc.weekday() >= 5:  # Saturday=5, Sunday=6
            return None
        t = timestamp_utc.time()
        for name, (start, end) in self._windows.items():
            if start <= t <= end:
                return name
        return None


@dataclass(frozen=True)
class SessionDayState:
    covered: bool = False
    valid_ticks: int = 0
    had_gap: bool = False
    pass_index: int = 0  # 0 = not yet qualifying, 1 = first pass, 2 = verification pass


class CoverageTracker:
    """Disk-durable per-symbol coverage state.

    State file shape (JSON):
    {
      "symbol": "XAUUSD",
      "version": 1,
      "days": {
        "2026-08-03": {
          "asian": {"covered": true, "valid_ticks": 52311, "had_gap": false, "pass_index": 1},
          ...
        }
      }
    }
    """

    def __init__(
        self,
        symbol: str,
        state_file: str | Path,
        session_windows: dict[str, tuple[time, time]] | None = None,
        qualifying_days: int = QUALIFYING_DAYS,
        min_valid_ticks: int = MIN_VALID_TICKS_PER_SESSION_DAY,
    ):
        self._symbol = symbol
        self._state_file = Path(state_file)
        self._classifier = SessionClassifier(session_windows)
        self._qualifying_days = qualifying_days
        self._min_valid_ticks = min_valid_ticks
        self._state: dict[str, dict] = self._load()

    # -- tick classification -------------------------------------------------

    def classify(self, timestamp_utc: datetime) -> str | None:
        return self._classifier.classify(timestamp_utc)

    # -- recording -----------------------------------------------------------

    def record_session_day(
        self,
        trading_day: date,
        session_name: str,
        valid_ticks: int,
        had_gap: bool,
    ) -> bool:
        """Record a session-day observation. Returns True when this session-day
        newly became covered (crossed the VALID-tick floor without a gap)."""
        day_key = trading_day.isoformat()
        day_state = self._state["days"].setdefault(day_key, {})
        prior = day_state.get(session_name, {})
        covered = prior.get("covered", False) or (valid_ticks >= self._min_valid_ticks and not had_gap)
        day_state[session_name] = {
            "covered": covered,
            "valid_ticks": max(prior.get("valid_ticks", 0), valid_ticks),
            "had_gap": prior.get("had_gap", False) or had_gap,
            "pass_index": prior.get("pass_index", 0),
        }
        self._assign_pass(day_key)
        return covered and not prior.get("covered", False)

    def _assign_pass(self, day_key: str) -> None:
        if not self._day_qualifies(day_key):
            return
        day_state = self._state["days"][day_key]
        if any(day_state[s]["pass_index"] for s in SESSION_NAMES if s in day_state):
            return  # already assigned
        pass_index = 2 if self.first_pass_days() >= self._qualifying_days else 1
        for name in SESSION_NAMES:
            if name in day_state:
                day_state[name]["pass_index"] = pass_index

    def _day_qualifies(self, day_key: str) -> bool:
        day_state = self._state["days"].get(day_key, {})
        sessions = [s for s in SESSION_NAMES if s in day_state]
        if len(sessions) < SESSIONS_PER_DAY:
            return False
        return all(day_state[s]["covered"] and not day_state[s]["had_gap"] for s in sessions)

    def qualifying_day_count(self) -> int:
        """Number of distinct qualifying days (5/5 sessions, no gap)."""
        return sum(1 for day_key in self._state["days"] if self._day_qualifies(day_key))

    def first_pass_days(self) -> int:
        return sum(
            1
            for day_state in self._state["days"].values()
            if any(s.get("pass_index") == 1 for s in day_state.values() if isinstance(s, dict))
        )

    def verification_pass_days(self) -> int:
        return sum(
            1
            for day_state in self._state["days"].values()
            if any(s.get("pass_index") == 2 for s in day_state.values() if isinstance(s, dict))
        )

    def first_pass_complete(self) -> bool:
        return self.first_pass_days() >= self._qualifying_days

    def verification_pass_complete(self) -> bool:
        return self.verification_pass_days() >= self._qualifying_days

    def progress(self) -> dict:
        return {
            "symbol": self._symbol,
            "qualifying_day_count": self.qualifying_day_count(),
            "first_pass_days": self.first_pass_days(),
            "verification_pass_days": self.verification_pass_days(),
            "first_pass_complete": self.first_pass_complete(),
            "verification_pass_complete": self.verification_pass_complete(),
        }

    # -- persistence ---------------------------------------------------------

    def _load(self) -> dict[str, Any]:
        default: dict[str, Any] = {"symbol": self._symbol, "version": 1, "days": {}}
        if not self._state_file.exists():
            return default
        try:
            raw = json.loads(self._state_file.read_text(encoding="utf-8"))
            if raw.get("symbol") != self._symbol:
                return default
            return raw
        except (json.JSONDecodeError, OSError):
            return default

    def save(self) -> None:
        self._state_file.parent.mkdir(parents=True, exist_ok=True)
        fd, tmp_path = tempfile.mkstemp(dir=str(self._state_file.parent), prefix=".coverage_", suffix=".tmp")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as fh:
                json.dump(self._state, fh, indent=2)
                fh.flush()
                os.fsync(fh.fileno())
            # Windows file-lock race: antivirus/Defender can briefly hold the
            # tmp file, making os.replace fail with PermissionError (WinError
            # 5) — observed as a flake in gate runs. Retry briefly before
            # giving up; the lock clears within milliseconds in practice.
            for attempt in range(5):
                try:
                    os.replace(tmp_path, str(self._state_file))
                    return
                except PermissionError:
                    if attempt == 4:
                        raise
                    _time.sleep(0.05 * (attempt + 1))
        except Exception:
            with contextlib.suppress(OSError):
                os.unlink(tmp_path)
            raise
