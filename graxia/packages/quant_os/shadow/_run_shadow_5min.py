"""Quick 5-minute shadow run with real MT5."""
import sys
sys.path.insert(0, ".")

from shadow.broker_observed_runner import BrokerObservedShadowRunner

runner = BrokerObservedShadowRunner(
    symbol="XAUUSD",
    strategy_version="locked_v1",
    feature_hash="abc123",
    mt5_path=r"C:\Program Files\MetaTrader 5\terminal64.exe",
)

if not runner.connect():
    print("FAILED to connect")
    sys.exit(1)

try:
    summary = runner.run(duration_seconds=300, interval_seconds=60)
    print(f"Total: {summary['total_signals']}")
    print(f"Accepted: {summary['accepted']}")
    print(f"Rejected: {summary['rejected']}")
    print(f"Ledger valid: {summary['ledger_valid']}")
    seal = summary["ledger_seal"]
    print(f"Ledger seal: {seal[:16]}..." if seal else "Ledger seal: empty")
    snap = summary["broker_snapshot"]
    if snap:
        print(f"Broker: {snap['account_server']} / Login: {snap['account_login']}")
        print(f"Contract: {snap['contract_size']} | Spread: {snap['spread_current']}")
    print(f"Rejection reasons: {summary['rejection_reasons']}")
    print(f"Reconnects: {summary['reconnect_count']}")
    print(f"Stale ticks: {summary['stale_tick_count']}")
finally:
    runner.disconnect()
