"""Tests for archive reasons."""
from graxia.packages.quant_os.validation.archive_reasons import ArchiveRecorder


def test_recorder_creates():
    recorder = ArchiveRecorder()
    assert recorder.count() == 0


def test_recorder_records():
    recorder = ArchiveRecorder()
    record = recorder.record("XAU_LIQSWEEP", "ARCHIVE_NO_EDGE", "negative expectancy")
    assert recorder.count() == 1
    assert record.strategy_id == "XAU_LIQSWEEP"
    assert record.verdict == "ARCHIVE_NO_EDGE"


def test_recorder_has_archive():
    recorder = ArchiveRecorder()
    recorder.record("XAU_LIQSWEEP", "ARCHIVE_NO_EDGE", "no edge")
    assert recorder.has_archive("XAU_LIQSWEEP")
    assert not recorder.has_archive("EURUSD")


def test_recorder_multiple():
    recorder = ArchiveRecorder()
    recorder.record("XAU_LIQSWEEP", "ARCHIVE_NO_EDGE", "reason1")
    recorder.record("XAU_LIQSWEEP", "INSUFFICIENT_SAMPLE", "reason2")
    assert recorder.count() == 2
