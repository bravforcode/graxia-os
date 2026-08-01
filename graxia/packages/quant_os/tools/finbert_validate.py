"""
Phase 3: FinBERT Validation on Real Headlines
==============================================
Pull 100 real headlines from DuckDB, run FinBERT, compare with Ollama qwen3.5:9b.

Usage:
    python tools/finbert_validate.py
"""

import sys

sys.stdout.reconfigure(encoding="utf-8")
import time
from pathlib import Path

import torch
from transformers import AutoModelForSequenceClassification, AutoTokenizer

# === Config ===
BASE_DIR = Path(__file__).parent.parent
DB_PATH = BASE_DIR / "data_pipeline" / "storage" / "quant_os.duckdb"
REPORT_PATH = BASE_DIR / "reports" / "finbert_validation.md"

FINBERT_MODEL = "ProsusAI/finbert"
NUM_SAMPLES = 100


def load_headlines_from_duckdb() -> list:
    """Pull headlines with Ollama sentiment from DuckDB."""
    sys.path.insert(0, str(BASE_DIR / "data_pipeline"))
    from storage.duckdb_store import DuckDBStore

    duck = DuckDBStore()
    rows = duck.conn.execute(
        """
        SELECT title, sentiment, tickers, source, analyzed_at
        FROM llm_news_sentiment
        WHERE title IS NOT NULL AND title != ''
        ORDER BY analyzed_at DESC
        LIMIT ?
    """,
        [NUM_SAMPLES],
    ).fetchall()
    duck.close()

    headlines = []
    for row in rows:
        headlines.append(
            {
                "title": row[0],
                "ollama_sentiment": row[1],
                "tickers": row[2],
                "source": row[3],
                "analyzed_at": str(row[4])[:19] if row[4] else None,
            }
        )
    return headlines


def load_finbert():
    """Load FinBERT model and tokenizer."""
    print(f"Loading FinBERT from {FINBERT_MODEL}...")
    t0 = time.time()
    tokenizer = AutoTokenizer.from_pretrained(FINBERT_MODEL)
    model = AutoModelForSequenceClassification.from_pretrained(FINBERT_MODEL)
    elapsed = time.time() - t0
    print(f"  Loaded in {elapsed:.1f}s")
    return tokenizer, model


def finbert_predict(tokenizer, model, text: str) -> dict:
    """Run FinBERT on a single headline."""
    inputs = tokenizer(text, return_tensors="pt", padding=True, truncation=True, max_length=512)
    with torch.no_grad():
        outputs = model(**inputs)

    probs = torch.nn.functional.softmax(outputs.logits, dim=-1)
    probs_np = probs.numpy()[0]

    # FinBERT labels: positive, negative, neutral
    labels = ["positive", "negative", "neutral"]
    sentiment = labels[probs_np.argmax()]
    confidence = float(probs_np.max())

    return {
        "finbert_sentiment": sentiment,
        "finbert_confidence": confidence,
        "finbert_probs": {labels[i]: float(probs_np[i]) for i in range(3)},
    }


def run_validation():
    """Run FinBERT on 100 real headlines and compare with Ollama."""
    print("=" * 60)
    print("FinBERT VALIDATION ON REAL HEADLINES")
    print("=" * 60)

    # Load headlines
    headlines = load_headlines_from_duckdb()
    print(f"\nLoaded {len(headlines)} headlines from DuckDB")

    if len(headlines) == 0:
        print("ERROR: No headlines found in DuckDB")
        return

    # Load FinBERT
    tokenizer, model = load_finbert()

    # Run FinBERT on each headline
    results = []
    correct = 0
    total = 0
    t0 = time.time()

    for i, h in enumerate(headlines):
        result = finbert_predict(tokenizer, model, h["title"])
        h.update(result)

        # Compare with Ollama
        match = h["finbert_sentiment"] == h["ollama_sentiment"]
        if match:
            correct += 1
        total += 1

        h["match"] = match
        results.append(h)

        if (i + 1) % 20 == 0:
            elapsed = time.time() - t0
            print(f"  Processed {i+1}/{len(headlines)} ({elapsed:.1f}s)")

    elapsed = time.time() - t0
    accuracy = 100 * correct / total if total > 0 else 0

    print(f"\n{'='*60}")
    print("RESULTS")
    print(f"{'='*60}")
    print(f"Total headlines: {total}")
    print(f"FinBERT vs Ollama agreement: {correct}/{total} ({accuracy:.1f}%)")
    print(f"Time: {elapsed:.1f}s ({elapsed/total:.2f}s per headline)")

    # Sentiment distribution comparison
    print("\n--- Sentiment Distribution ---")
    finbert_dist = {"positive": 0, "negative": 0, "neutral": 0}
    ollama_dist = {"positive": 0, "negative": 0, "neutral": 0}
    for r in results:
        finbert_dist[r["finbert_sentiment"]] += 1
        ollama_dist[r["ollama_sentiment"]] += 1

    print(f"{'Sentiment':12} {'FinBERT':>10} {'Ollama':>10}")
    print(f"{'-'*34}")
    for s in ["positive", "negative", "neutral"]:
        print(f"{s:12} {finbert_dist[s]:>10} {ollama_dist[s]:>10}")

    # Agreement by sentiment
    print("\n--- Agreement by Sentiment ---")
    for s in ["positive", "negative", "neutral"]:
        subset = [r for r in results if r["ollama_sentiment"] == s]
        if subset:
            agree = sum(1 for r in subset if r["finbert_sentiment"] == s)
            print(f"  Ollama={s}: {agree}/{len(subset)} agree ({100*agree/len(subset):.0f}%)")

    # Show disagreements
    disagreements = [r for r in results if not r["match"]]
    print(f"\n--- Disagreements ({len(disagreements)} total) ---")
    for d in disagreements[:10]:
        print(f"  Ollama={d['ollama_sentiment']:8} FinBERT={d['finbert_sentiment']:8} | {d['title'][:60]}")

    # Save report
    save_report(results, accuracy, finbert_dist, ollama_dist, elapsed)

    return results, accuracy


def save_report(results, accuracy, finbert_dist, ollama_dist, elapsed):
    """Save validation report."""
    disagreements = [r for r in results if not r["match"]]

    report = f"""# FinBERT Validation Report

## Summary

| Metric | Value |
|--------|-------|
| Headlines tested | {len(results)} |
| FinBERT vs Ollama agreement | {accuracy:.1f}% |
| Processing time | {elapsed:.1f}s ({elapsed/len(results):.2f}s/headline) |
| Model | {FINBERT_MODEL} |

## Sentiment Distribution

| Sentiment | FinBERT | Ollama |
|-----------|---------|--------|
| positive | {finbert_dist['positive']} | {ollama_dist['positive']} |
| negative | {finbert_dist['negative']} | {ollama_dist['negative']} |
| neutral | {finbert_dist['neutral']} | {ollama_dist['neutral']} |

## Agreement by Sentiment

"""

    for s in ["positive", "negative", "neutral"]:
        subset = [r for r in results if r["ollama_sentiment"] == s]
        if subset:
            agree = sum(1 for r in subset if r["finbert_sentiment"] == s)
            report += f"- Ollama={s}: {agree}/{len(subset)} agree ({100*agree/len(subset):.0f}%)\n"

    report += f"\n## Disagreements ({len(disagreements)} total)\n\n"
    report += "| Ollama | FinBERT | Title |\n|--------|---------|-------|\n"
    for d in disagreements[:20]:
        title = d["title"][:60].replace("|", "\\|")
        report += f"| {d['ollama_sentiment']} | {d['finbert_sentiment']} | {title} |\n"

    report += "\n## Conclusion\n\n"
    if accuracy >= 80:
        report += f"FinBERT agrees with Ollama qwen3.5:9b {accuracy:.1f}% of the time. "
        report += "This is sufficient for ensemble work (Phase 4)."
    elif accuracy >= 60:
        report += f"FinBERT agrees with Ollama qwen3.5:9b {accuracy:.1f}% of the time. "
        report += "Moderate agreement. Consider ensemble with weighted voting."
    else:
        report += f"FinBERT agrees with Ollama qwen3.5:9b only {accuracy:.1f}% of the time. "
        report += "Low agreement. Ensemble may not be beneficial. Investigate further."

    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    REPORT_PATH.write_text(report, encoding="utf-8")
    print(f"\nReport saved to {REPORT_PATH}")


if __name__ == "__main__":
    run_validation()
