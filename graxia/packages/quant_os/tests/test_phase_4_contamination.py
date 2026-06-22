import pytest
from graxia.packages.quant_os.markets.eurusd.anti_contamination import AntiContaminationGuard

class TestAntiContamination:
    def test_clean_params(self):
        guard = AntiContaminationGuard()
        params = {"ema_fast": 9, "ema_slow": 21, "rsi_period": 14}
        report = guard.check_parameter_source(params)
        assert report.clean is True
    
    def test_xauusd_source_blocked(self):
        guard = AntiContaminationGuard()
        params = {"ema_fast": 9}
        report = guard.check_parameter_source(params, source_market="XAUUSD")
        assert report.clean is False
    
    def test_gold_in_name_blocked(self):
        guard = AntiContaminationGuard()
        params = {"gold_atr_period": 14}
        report = guard.check_parameter_source(params)
        assert report.clean is False
    
    def test_gold_price_value_blocked(self):
        guard = AntiContaminationGuard()
        params = {"entry_level": 2350}
        report = guard.check_parameter_source(params)
        assert report.clean is False
    
    def test_content_xauusd_blocked(self):
        guard = AntiContaminationGuard()
        report = guard.check_file_content("strategy for XAUUSD", "test.py")
        assert report.clean is False
    
    def test_content_clean(self):
        guard = AntiContaminationGuard()
        report = guard.check_file_content("strategy for EURUSD", "test.py")
        assert report.clean is True
    
    def test_strategy_hash_match(self):
        guard = AntiContaminationGuard()
        report = guard.check_strategy_hash("abc123", ["abc123", "def456"])
        assert report.clean is False
    
    def test_strategy_hash_no_match(self):
        guard = AntiContaminationGuard()
        report = guard.check_strategy_hash("xyz789", ["abc123", "def456"])
        assert report.clean is True
