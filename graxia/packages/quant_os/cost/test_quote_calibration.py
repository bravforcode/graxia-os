"""Tests for quote calibration."""
from graxia.packages.quant_os.cost.quote_calibration import QuoteCalibrator


def test_calibrator_creates():
    cal = QuoteCalibrator()
    assert cal is not None


def test_calibrator_observes():
    cal = QuoteCalibrator()
    for i in range(100):
        cal.observe_spread(0.3 + i * 0.01)
        cal.observe_quote_move(0.1 + i * 0.005)
        cal.observe_latency(10 + i * 0.1)
    result = cal.calibrate()
    assert result.sample_count == 100
    assert result.spread_p50 > 0
    assert result.spread_p90 > result.spread_p50
    assert result.evidence_level == "QUOTE_OBSERVED"


def test_calibrator_insufficient():
    cal = QuoteCalibrator()
    for i in range(10):
        cal.observe_spread(0.3)
    result = cal.calibrate()
    assert not result.is_sufficient(100)


def test_calibrator_sufficient():
    cal = QuoteCalibrator()
    for i in range(200):
        cal.observe_spread(0.3)
    result = cal.calibrate()
    assert result.is_sufficient(100)
