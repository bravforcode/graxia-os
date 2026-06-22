"""Quick shadow runner test with Pepperstone"""
from mt5_connector.shadow_runner import ShadowRunnerV2

runner = ShadowRunnerV2()
ok = runner.connect()
print("Connected:", ok)
if ok:
    info = runner._mt5.get_account_info()
    print("Account:", info.login, "@", info.server)
    print("Balance:", info.balance)

    # Single cycle test
    result = runner.run_cycle("XAUUSD")
    print("Signal:", result["signal_id"])
    print("Outcome:", result["outcome"])
    print("Direction:", result.get("direction", "-"))
    print("Entry:", result.get("entry_price", "-"))
    te = result.get("tick_evidence")
    if te:
        print("Spread:", te["spread"])
    print("Hyp PnL:", result.get("hypothetical_pnl", 0))
    print("Exit:", result.get("exit_reason", "-"))

    runner.disconnect()
