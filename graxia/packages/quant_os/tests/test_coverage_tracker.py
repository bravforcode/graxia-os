"""Unit tests for market_data/coverage_tracker.py (Phase 1 promotion bar)."""

from __future__ import annotations

import os
from datetime import UTC, date, datetime, time, timedelta

import pytest

from market_data.coverage_tracker import (
    DEFAULT_SESSION_WINDOWS,
    MIN_VALID_TICKS_PER_SESSION_DAY,
    QUALIFYING_DAYS,
    SESSION_NAMES,
    CoverageTracker,
    SessionClassifier,
)


def _fill_qualifying_day(tracker: CoverageTracker, d: date) -> None:
    for name in SESSION_NAMES:
        tracker.record_session_day(d, name, MIN_VALID_TICKS_PER_SESSION_DAY, had_gap=False)


def test_classifier_weekend_returns_none():
    clf = SessionClassifier()
    saturday = datetime(2026, 8, 8, 12, 0, tzinfo=UTC)  # Saturday
    assert clf.classify(saturday) is None


def test_classifier_maps_sessions():
    clf = SessionClassifier()
    assert clf.classify(datetime(2026, 8, 3, 2, 0, tzinfo=UTC)) == "asian"
    assert clf.classify(datetime(2026, 8, 3, 9, 0, tzinfo=UTC)) == "london"
    assert clf.classify(datetime(2026, 8, 3, 14, 0, tzinfo=UTC)) == "london_ny_overlap"
    assert clf.classify(datetime(2026, 8, 3, 18, 0, tzinfo=UTC)) == "ny"
    assert clf.classify(datetime(2026, 8, 3, 22, 0, tzinfo=UTC)) == "rollover"


def test_classifier_respects_per_symbol_windows():
    clf = SessionClassifier(session_windows={**DEFAULT_SESSION_WINDOWS, "london": (time(6, 0), time(13, 0))})
    # 10:00 is inside the overridden london window and outside every default window.
    assert clf.classify(datetime(2026, 8, 3, 10, 0, tzinfo=UTC)) == "london"
    # 06:30 overlaps asian (00:00-07:00) and the overridden london (06:00-13:00);
    # first-match iteration order wins -> asian (documented behavior).
    assert clf.classify(datetime(2026, 8, 3, 6, 30, tzinfo=UTC)) == "asian"


def test_session_day_needs_tick_floor(tmp_path):
    tracker = CoverageTracker("XAUUSD", tmp_path / "cov.json")
    tracker.record_session_day(date(2026, 8, 3), "asian", MIN_VALID_TICKS_PER_SESSION_DAY - 1, had_gap=False)
    assert tracker.qualifying_day_count() == 0


def test_gap_invalidates_session_day(tmp_path):
    tracker = CoverageTracker("XAUUSD", tmp_path / "cov.json")
    tracker.record_session_day(date(2026, 8, 3), "asian", MIN_VALID_TICKS_PER_SESSION_DAY, had_gap=True)
    assert tracker.qualifying_day_count() == 0


def test_qualifying_day_requires_all_five_sessions(tmp_path):
    tracker = CoverageTracker("XAUUSD", tmp_path / "cov.json")
    for name in SESSION_NAMES[:4]:
        tracker.record_session_day(date(2026, 8, 3), name, MIN_VALID_TICKS_PER_SESSION_DAY, had_gap=False)
    assert tracker.qualifying_day_count() == 0


def test_seven_qualifying_days_completes_first_pass(tmp_path):
    tracker = CoverageTracker("XAUUSD", tmp_path / "cov.json")
    start = date(2026, 8, 3)  # Monday
    for i in range(QUALIFYING_DAYS):
        _fill_qualifying_day(tracker, start + timedelta(days=i))
    assert tracker.qualifying_day_count() == QUALIFYING_DAYS
    assert tracker.first_pass_complete()
    assert not tracker.verification_pass_complete()


def test_non_consecutive_days_count(tmp_path):
    tracker = CoverageTracker("XAUUSD", tmp_path / "cov.json")
    days = [date(2026, 8, 3), date(2026, 8, 10), date(2026, 8, 17)]  # three Mondays
    for d in days:
        _fill_qualifying_day(tracker, d)
    assert tracker.qualifying_day_count() == 3


def test_second_pass_requires_fresh_window(tmp_path):
    tracker = CoverageTracker("XAUUSD", tmp_path / "cov.json")
    start = date(2026, 8, 3)
    for i in range(QUALIFYING_DAYS * 2):
        _fill_qualifying_day(tracker, start + timedelta(days=i))
    assert tracker.first_pass_complete()
    assert tracker.verification_pass_complete()


def test_state_survives_reload(tmp_path):
    state_file = tmp_path / "cov.json"
    tracker = CoverageTracker("XAUUSD", state_file)
    _fill_qualifying_day(tracker, date(2026, 8, 3))
    tracker.save()

    reloaded = CoverageTracker("XAUUSD", state_file)
    assert reloaded.qualifying_day_count() == 1


def test_state_is_per_symbol(tmp_path):
    a = CoverageTracker("XAUUSD", tmp_path / "cov_a.json")
    b = CoverageTracker("USOIL", tmp_path / "cov_b.json")
    _fill_qualifying_day(a, date(2026, 8, 3))
    a.save()
    b.save()
    assert CoverageTracker("USOIL", tmp_path / "cov_b.json").qualifying_day_count() == 0


def test_corrupt_state_file_falls_back_to_empty(tmp_path):
    state_file = tmp_path / "cov.json"
    state_file.write_text("{not json")
    tracker = CoverageTracker("XAUUSD", state_file)
    assert tracker.qualifying_day_count() == 0


def test_save_retries_when_replace_blocked(tmp_path, monkeypatch):
    """Windows file-lock race: os.replace can transiently raise PermissionError
    (WinError 5). save() must retry instead of failing the daemon tick."""
    state_file = tmp_path / "cov.json"
    tracker = CoverageTracker("XAUUSD", state_file)
    _fill_qualifying_day(tracker, date(2026, 8, 3))

    real_replace = os.replace
    calls = {"n": 0}

    def flaky_replace(src, dst):
        calls["n"] += 1
        if calls["n"] <= 2:
            raise PermissionError(5, "Access is denied", src, dst)
        return real_replace(src, dst)

    monkeypatch.setattr(os, "replace", flaky_replace)
    tracker.save()
    assert calls["n"] == 3
    assert CoverageTracker("XAUUSD", state_file).qualifying_day_count() == 1


def test_save_raises_after_retries_exhausted(tmp_path, monkeypatch):
    """If the lock never clears, save() must clean up the tmp file and raise."""
    state_file = tmp_path / "cov.json"
    tracker = CoverageTracker("XAUUSD", state_file)
    _fill_qualifying_day(tracker, date(2026, 8, 3))

    def always_blocked(src, dst):
        raise PermissionError(5, "Access is denied", src, dst)

    monkeypatch.setattr(os, "replace", always_blocked)
    with pytest.raises(PermissionError):
        tracker.save()
    assert not list(tmp_path.glob(".coverage_*.tmp"))
