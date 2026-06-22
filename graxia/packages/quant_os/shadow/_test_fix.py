"""Test fixed campaign runner."""
import sys
sys.path.insert(0, ".")
from graxia.packages.quant_os.shadow.pepperstone_campaign import PepperstoneCampaignRunner

runner = PepperstoneCampaignRunner()
runner._mt5.connect(timeout=30000)
acct = runner._mt5.get_account_info()
print("Connected:", acct["server"])

for i in range(3):
    ev = runner.run_cycle(i + 1)
    print(f"Cycle {i+1}: {ev.outcome} | ticks={ev.raw_tick_count} | spread={ev.spread:.4f}")

runner._mt5.disconnect()
