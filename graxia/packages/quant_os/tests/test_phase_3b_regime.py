from graxia.packages.quant_os.validation.regime_analyzer import RegimeAnalyzer, RegimeType, TradeConcentration


class TestRegimeAnalyzer:
    def test_classify_trending_up(self):
        analyzer = RegimeAnalyzer()
        import random

        random.seed(7)
        prices = [100 + i * 2.0 + random.uniform(-1, 1) for i in range(30)]
        regime = analyzer.classify_bar(prices, 25)
        assert regime == RegimeType.TRENDING_UP

    def test_classify_trending_down(self):
        analyzer = RegimeAnalyzer()
        import random

        random.seed(7)
        prices = [200 - i * 2.0 + random.uniform(-1, 1) for i in range(30)]
        regime = analyzer.classify_bar(prices, 25)
        assert regime == RegimeType.TRENDING_DOWN

    def test_classify_ranging(self):
        analyzer = RegimeAnalyzer()
        import random

        random.seed(42)
        prices = [100 + random.uniform(-0.01, 0.01) for _ in range(30)]
        regime = analyzer.classify_bar(prices, 25)
        assert regime in (RegimeType.RANGING, RegimeType.LOW_VOLATILITY)

    def test_classify_unknown_insufficient_data(self):
        analyzer = RegimeAnalyzer()
        prices = [100, 101, 102]
        regime = analyzer.classify_bar(prices, 2)
        assert regime == RegimeType.UNKNOWN

    def test_analyze_trades(self):
        analyzer = RegimeAnalyzer()
        trades = [{"pnl": 10, "bar_index": 25}, {"pnl": -5, "bar_index": 26}]
        prices = [100 + i * 0.5 for i in range(30)]
        result = analyzer.analyze_trades(trades, prices)
        assert result["total_trades"] == 2
        assert len(result["slices"]) > 0


class TestTradeConcentration:
    def test_concentration_passes(self):
        conc = TradeConcentration(
            max_single_trade_pnl=100,
            max_single_trade_pct_of_total=0.15,
            max_month_pnl=500,
            max_month_pct_of_total=0.25,
            gini_coefficient=0.3,
        )
        passes, issues = conc.passes()
        assert passes is True

    def test_concentration_single_trade_dominates(self):
        conc = TradeConcentration(
            max_single_trade_pnl=1000,
            max_single_trade_pct_of_total=0.50,
            max_month_pnl=500,
            max_month_pct_of_total=0.25,
            gini_coefficient=0.6,
        )
        passes, issues = conc.passes()
        assert passes is False
        assert any("SINGLE_TRADE" in i for i in issues)

    def test_concentration_month_dominates(self):
        conc = TradeConcentration(
            max_single_trade_pnl=100,
            max_single_trade_pct_of_total=0.15,
            max_month_pnl=2000,
            max_month_pct_of_total=0.60,
            gini_coefficient=0.4,
        )
        passes, issues = conc.passes()
        assert passes is False
        assert any("MONTH" in i for i in issues)
