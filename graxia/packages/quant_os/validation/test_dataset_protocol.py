"""Tests for dataset protocol."""
from graxia.packages.quant_os.validation.dataset_protocol import DatasetProtocol, DatasetSplit


def test_protocol_creates():
    protocol = DatasetProtocol()
    assert protocol is not None


def test_protocol_add_splits():
    protocol = DatasetProtocol()
    protocol.add_split(DatasetSplit("train", "2020-01-01", "2024-06-30", "train"))
    protocol.add_split(DatasetSplit("holdout", "2025-07-01", "2026-06-30", "holdout"))
    assert len(protocol.get_splits()) == 2
    assert protocol.get_holdout() is not None


def test_protocol_no_overlap():
    protocol = DatasetProtocol()
    protocol.add_split(DatasetSplit("train", "2020-01-01", "2024-06-30", "train"))
    protocol.add_split(DatasetSplit("holdout", "2025-07-01", "2026-06-30", "holdout"))
    ok, issues = protocol.validate_no_overlap()
    assert ok


def test_protocol_overlap_detected():
    protocol = DatasetProtocol()
    protocol.add_split(DatasetSplit("a", "2020-01-01", "2024-06-30", "train"))
    protocol.add_split(DatasetSplit("b", "2024-01-01", "2025-06-30", "validation"))
    ok, issues = protocol.validate_no_overlap()
    assert not ok
    assert len(issues) > 0


def test_protocol_holdout_used():
    protocol = DatasetProtocol()
    assert not protocol.is_holdout_used()
    protocol.mark_holdout_used()
    assert protocol.is_holdout_used()


def test_protocol_default():
    protocol = DatasetProtocol.default_xauusd()
    assert len(protocol.get_splits()) == 3
    assert protocol.get_holdout() is not None
