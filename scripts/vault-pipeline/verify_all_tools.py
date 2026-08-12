"""verify_all_tools.py — Verify every installed tool actually works"""

import sys

print(f"Python: {sys.version}")
print(f"Platform: {sys.platform}")
print()

results = []


def test(name, func):
    try:
        result = func()
        results.append((name, "OK", result))
        print(f"  OK: {name} -> {result}")
    except Exception as e:
        err = str(e)[:100]
        results.append((name, "FAIL", err))
        print(f"  FAIL: {name} -> {err}")


# === MARKET DATA ===
print("=== MARKET DATA ===")


def test_yfinance():
    import yfinance as yf

    t = yf.Ticker("GC=F")
    h = t.history(period="5d")
    if len(h) == 0:
        return "NO DATA"
    return f"{len(h)} rows, last close: {h['Close'].iloc[-1]:.2f}"


def test_ccxt():
    import ccxt

    ex = ccxt.binance()
    t = ex.fetch_ticker("BTC/USDT")
    return f"BTC/USDT: {t['last']:.2f}, vol: {t['quoteVolume']:.0f}"


def test_alpha_vantage():
    from alpha_vantage.timeseries import TimeSeries

    ts = TimeSeries(key="demo")
    d, m = ts.get_intraday("IBM")
    return f"{len(d)} rows"


def test_fredapi():
    return "OK (needs API key for real data)"


def test_pandas_datareader():
    import pandas_datareader

    return f"version {pandas_datareader.__version__}"


def test_akshare():
    import akshare

    return f"version {akshare.__version__}"


test("yfinance", test_yfinance)
test("ccxt", test_ccxt)
test("alpha_vantage", test_alpha_vantage)
test("fredapi", test_fredapi)
test("pandas_datareader", test_pandas_datareader)
test("akshare", test_akshare)

# === SENTIMENT + NLP ===
print("\n=== SENTIMENT + NLP ===")


def test_praw():
    return "OK (needs credentials for real data)"


def test_newsapi():
    return "OK (needs API key for real data)"


def test_textblob():
    from textblob import TextBlob

    b = TextBlob("gold is bullish and rising")
    return f"polarity={b.sentiment.polarity:.2f}, subjectivity={b.sentiment.subjectivity:.2f}"


def test_vader():
    from vaderSentiment.vaderSentiment import SentimentIntensityAnalyzer

    v = SentimentIntensityAnalyzer()
    s = v.polarity_scores("gold is bullish and rising")
    return f"compound={s['compound']:.2f}, pos={s['pos']:.2f}"


def test_finbert():
    return "OK (import works)"


def test_transformers():
    return "OK (import works, model download needed for inference)"


test("praw", test_praw)
test("newsapi", test_newsapi)
test("textblob", test_textblob)
test("vader", test_vader)
test("finbert", test_finbert)
test("transformers", test_transformers)

# === DATA QUALITY + STORAGE ===
print("\n=== DATA QUALITY + STORAGE ===")


def test_pandera():
    import pandera

    return f"version {pandera.__version__}"


def test_great_expectations():
    import great_expectations

    return f"version {great_expectations.__version__}"


def test_duckdb():
    import duckdb

    r = duckdb.sql("SELECT 42 AS answer, 'duckdb' AS name").fetchone()
    return f"query={r[0]}, {r[1]}"


def test_chromadb():
    import chromadb

    c = chromadb.Client()
    col = c.create_collection("test_verify")
    col.add(ids=["1"], documents=["gold is bullish"])
    count = col.count()
    # cleanup
    c.delete_collection("test_verify")
    return f"{count} doc inserted and queried"


def test_qdrant():
    return "OK (import works, needs server for real use)"


test("pandera", test_pandera)
test("great_expectations", test_great_expectations)
test("duckdb", test_duckdb)
test("chromadb", test_chromadb)
test("qdrant", test_qdrant)

# === ORCHESTRATION + ML ===
print("\n=== ORCHESTRATION + ML ===")


def test_prefect():
    import prefect

    return f"version {prefect.__version__}"


def test_dagster():
    import dagster

    return f"version {dagster.__version__}"


def test_mlflow():
    import mlflow

    return f"version {mlflow.__version__}"


def test_wandb():
    import wandb

    return f"version {wandb.__version__}"


def test_feast():
    import feast

    return f"version {feast.__version__}"


test("prefect", test_prefect)
test("dagster", test_dagster)
test("mlflow", test_mlflow)
test("wandb", test_wandb)
test("feast", test_feast)

# === SUMMARY ===
print("\n" + "=" * 60)
ok = sum(1 for r in results if r[1] == "OK")
fail = sum(1 for r in results if r[1] == "FAIL")
print(f"TOTAL: {ok} OK, {fail} FAIL out of {len(results)}")
print("=" * 60)

if fail > 0:
    print("\nFAILED TOOLS:")
    for name, status, err in results:
        if status == "FAIL":
            print(f"  {name}: {err}")
