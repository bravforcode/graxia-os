"""Tests for shadow campaign."""
from graxia.packages.quant_os.shadow.shadow_campaign import ShadowCampaign, CampaignConfig


def test_campaign_creates():
    config = CampaignConfig(symbol="XAUUSD", strategy_id="test")
    campaign = ShadowCampaign(config)
    assert campaign.get_status() == "idle"


def test_campaign_start_stop():
    config = CampaignConfig(symbol="XAUUSD", strategy_id="test")
    campaign = ShadowCampaign(config)
    campaign.start()
    assert campaign.is_active()
    assert campaign.get_status() == "running"
    campaign.stop()
    assert not campaign.is_active()
    assert campaign.get_status() == "completed"


def test_campaign_records_signals():
    config = CampaignConfig(symbol="XAUUSD", strategy_id="test")
    campaign = ShadowCampaign(config)
    campaign.start()
    campaign.record_signal()
    campaign.record_signal()
    summary = campaign.get_summary()
    assert summary["signal_count"] == 2
    campaign.stop()
