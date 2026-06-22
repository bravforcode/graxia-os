"""Tests for data quality checker."""
from graxia.packages.quant_os.tick.data_quality import DataQualityChecker


def test_valid_tick_no_incidents():
    checker = DataQualityChecker()
    tick = {"bid": 2350.50, "ask": 2350.80, "tick_id": 1, "source_time_msc": 1000, "ingest_sequence": 1}
    incidents = checker.check_tick(tick)
    assert len(incidents) == 0


def test_invalid_bid():
    checker = DataQualityChecker()
    incidents = checker.check_tick({"bid": -1, "ask": 2350.80, "tick_id": 1})
    assert any(i.incident_type == "invalid_bid" for i in incidents)


def test_invalid_ask():
    checker = DataQualityChecker()
    incidents = checker.check_tick({"bid": 2350.50, "ask": 0, "tick_id": 1})
    assert any(i.incident_type == "invalid_ask" for i in incidents)


def test_inverted_quote():
    checker = DataQualityChecker()
    incidents = checker.check_tick({"bid": 2350.80, "ask": 2350.50, "tick_id": 1})
    assert any(i.incident_type == "inverted_quote" for i in incidents)


def test_out_of_order():
    checker = DataQualityChecker()
    checker.check_tick({"bid": 100, "ask": 101, "source_time_msc": 2000, "ingest_sequence": 1})
    incidents = checker.check_tick({"bid": 100, "ask": 101, "source_time_msc": 1000, "ingest_sequence": 2})
    assert any(i.incident_type == "out_of_order" for i in incidents)


def test_gap_detection():
    checker = DataQualityChecker(gap_threshold=10)
    checker.check_tick({"bid": 100, "ask": 101, "ingest_sequence": 1})
    incidents = checker.check_tick({"bid": 100, "ask": 101, "ingest_sequence": 20})
    assert any(i.incident_type == "gap" for i in incidents)


def test_duplicate_detection():
    checker = DataQualityChecker()
    checker.check_tick({"bid": 100, "ask": 101, "ingest_sequence": 1})
    incidents = checker.check_tick({"bid": 100, "ask": 101, "ingest_sequence": 1})
    assert any(i.incident_type == "duplicate" for i in incidents)


def test_stale_tick_detection():
    checker = DataQualityChecker(stale_threshold_ms=100)
    checker.check_tick({"bid": 100, "ask": 101, "source_time_msc": 1000, "ingest_sequence": 1})
    checker._last_source_time_ms = 1000
    checker._last_sequence = 2
    incidents = checker.check_tick({"bid": 100, "ask": 101, "source_time_msc": 800, "ingest_sequence": 3})
    assert any(i.incident_type == "stale" for i in incidents)


def test_session_break_detection():
    checker = DataQualityChecker()
    checker.check_tick({"bid": 100, "ask": 101, "source_time_msc": 1000000, "ingest_sequence": 1})
    incidents = checker.check_tick({"bid": 100, "ask": 101, "source_time_msc": 1360000, "ingest_sequence": 2})
    assert any(i.incident_type == "session_break" for i in incidents)
