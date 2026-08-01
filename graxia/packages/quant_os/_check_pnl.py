import duckdb, json, numpy as np
con = duckdb.connect("reports/paper_engine/campaign_results.duckdb", read_only=True)
row = con.execute("SELECT trades_json FROM campaigns WHERE campaign_id='camp_0296'").fetchone()
con.close()
trades = json.loads(row[0])
pnls = np.array([t["net_pnl"] for t in trades])
print("Trades:", len(pnls))
print("Mean:", pnls.mean())
print("Std:", pnls.std(ddof=1))
print("Min:", pnls.min(), "Max:", pnls.max())
z = (pnls - pnls.mean()) / pnls.std(ddof=1)
print("Skew:", np.mean(z**3))
print("Excess Kurt:", np.mean(z**4) - 3)
print()
print("P&L distribution:")
pcts = [1, 5, 10, 25, 50, 75, 90, 95, 99]
for p in pcts:
    print("  P%d: %.2f" % (p, np.percentile(pnls, p)))
print()
# Check: are P&L values very uniform?
unique = len(set(pnls))
print("Unique P&L values:", unique, "out of", len(pnls))
print("Top 5 P&L:", sorted(pnls, reverse=True)[:5])
print("Bottom 5 P&L:", sorted(pnls)[:5])
