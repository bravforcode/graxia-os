"""auto_run.py — Auto-run pipeline + query + search"""
import subprocess
import sys
import time

py = sys.executable
base = r"C:\Users\menum\graxia os\graxia\packages\quant_os\data_pipeline"

def run(cmd, desc):
    print(f"\n{'='*50}")
    print(f"  {desc}")
    print(f"{'='*50}")
    t0 = time.time()
    result = subprocess.run(
        [py] + cmd,
        cwd=base,
        capture_output=True,
        text=True,
        timeout=120,
        env={
            **subprocess.os.environ,
            # Keys come from parent environment, no hardcoding
        }
    )
    elapsed = time.time() - t0
    print(result.stdout)
    if result.stderr:
        print(f"[WARN] {result.stderr[:200]}")
    print(f"\n  Done in {elapsed:.1f}s")
    return result.returncode == 0

print(f"{'#'*50}")
print(f"  AUTO-RUN PIPELINE — {time.strftime('%Y-%m-%d %H:%M:%S')}")
print(f"{'#'*50}")

# 1. Run pipeline
run(["pipeline.py"], "STEP 1: RUN DATA PIPELINE")

# 2. Query data
run(["query_data.py"], "STEP 2: QUERY STORED DATA")

# 3. Semantic search
run(["-c", """
import sys
sys.path.insert(0, '.')
from storage.chroma_store import ChromaStore
db = ChromaStore()
stats = db.get_collection_stats()
print(f'ChromaDB Stats: {stats}')

print()
print('=== SEMANTIC SEARCH: gold bullish outlook ===')
results = db.search_news('gold bullish outlook', n_results=3)
for r in results:
    print(f'  {r[:100]}')

print()
print('=== SEMANTIC SEARCH: mean reversion strategy ===')
results = db.search_strategies('mean reversion strategy', n_results=3)
for r in results:
    print(f'  {r[:100]}')

db.close()
"""], "STEP 3: SEMANTIC SEARCH")

print(f"\n{'#'*50}")
print("  ALL STEPS COMPLETE")
print(f"{'#'*50}")
