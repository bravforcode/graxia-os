"""Quick sanity check for trades_per_year computation."""
import json
import duckdb
from paper_engine.analyzer import _trades_per_year_from_dicts
from paper_engine.engine import _trades_per_year, Trade

con = duckdb.connect("reports/paper_engine/campaign_results.duckdb", read_only=True)
row = con.execute(
    "SELECT trades_json FROM campaigns WHERE campaign_id=?", ["camp_0296"]
).fetchone()
con.close()

trades = json.loads(row[0])
tpy = _trades_per_year_from_dicts(trades)
print(f"camp_0296: {len(trades)} trades, TPY={tpy:.1f}")
print(f"  First entry: {trades[0]['entry_time']}")
print(f"  Last exit:   {trades[-1]['exit_time']}")
print(f"  Old Sharpe (sqrt252): 5.719")
print(f"  Corrected Sharpe (sqrt{tpy:.0f}): {5.719 * (tpy / 252)**0.5:.3f}")

# Check a few more campaigns
con = duckdb.connect("reports/paper_engine/campaign_results.duckdb", read_only=True)
rows = con.execute(
    "SELECT campaign_id, trades_json, sharpe FROM campaigns "
    "WHERE error IS NULL AND total_trades >= 100 "
    "ORDER BY sharpe DESC LIMIT 5"
).fetchall()
con.close()

print("\n--- Top 5 campaigns ---")
for cid, tjson, old_sharpe in rows:
    if not tjson or len(tjson) < 3:
        continue
    trades = json.loads(tjson)
    tpy = _trades_per_year_from_dicts(trades)
    corrected = old_sharpe * (tpy / 252)**0.5 if tpy > 0 else old_sharpe
    print(f"  {cid}: old={old_sharpe:.3f}, tpy={tpy:.0f}, corrected={corrected:.3f}")
