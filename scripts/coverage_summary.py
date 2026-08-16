"""Summarize coverage_revenue_os.json by top-level module (source only)."""
import collections
import json

d = json.load(open("coverage_revenue_os.json", encoding="utf-8"))
files = {k: v for k, v in d["files"].items() if "tests" not in k and "conftest" not in k}

by_mod = collections.defaultdict(lambda: [0, 0])  # [statements, missed]
for path, v in files.items():
    mod = path.replace("\\", "/").split("/")[3]  # graxia/packages/revenue_os/<mod>
    by_mod[mod][0] += v["summary"]["num_statements"]
    by_mod[mod][1] += v["summary"]["missing_lines"]

print(f"{'module':<40} {'stmts':>6} {'missed':>6} {'cov%':>6}")
print("-" * 60)
tot_s = tot_m = 0
for mod in sorted(by_mod):
    s, m = by_mod[mod]
    tot_s += s
    tot_m += m
    print(f"{mod:<40} {s:>6} {m:>6} {100 * (1 - m / s):>5.1f}%")
print("-" * 60)
print(f"{'TOTAL':<40} {tot_s:>6} {tot_m:>6} {100 * (1 - tot_m / tot_s):>5.1f}%")