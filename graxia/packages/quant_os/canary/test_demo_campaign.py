"""Tests for demo campaign."""
from graxia.packages.quant_os.canary.demo_campaign import DemoCampaign


def test_campaign_creates():
    campaign = DemoCampaign()
    assert campaign.get_state().status == "idle"


def test_campaign_lifecycle():
    campaign = DemoCampaign()
    campaign.start()
    assert campaign.is_running()
    campaign.pause()
    assert campaign.get_state().status == "paused"
    campaign.resume()
    assert campaign.is_running()
    campaign.complete()
    assert not campaign.is_running()


def test_campaign_records():
    campaign = DemoCampaign()
    campaign.start()
    campaign.record_day(signals=10, orders=5, fills=3, incidents=1)
    campaign.record_day(signals=8, orders=4, fills=2, incidents=0)
    s = campaign.get_summary()
    assert s["days_run"] == 2
    assert s["total_signals"] == 18
    assert s["incidents"] == 1
