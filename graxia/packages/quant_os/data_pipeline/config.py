"""
config.py — Data Pipeline Configuration
"""
import os
from pathlib import Path

# === PATHS ===
PROJECT_ROOT = Path(os.environ.get("QUANT_OS_ROOT", r"C:\Users\menum\graxia os\graxia\packages\quant_os"))
DATA_DIR = PROJECT_ROOT / "data"
PIPELINE_DIR = PROJECT_ROOT / "data_pipeline"
STORAGE_DIR = PIPELINE_DIR / "storage"
LOG_DIR = STORAGE_DIR / "logs"
BACKUP_DIR = STORAGE_DIR / "backups"

# === DATABASES ===
DUCKDB_PATH = STORAGE_DIR / "quant_os.duckdb"
CHROMA_PATH = STORAGE_DIR / "chroma_db"

# === API KEYS ===
# SECURITY: No hardcoded keys. Fail closed if env vars missing.
ALPHAVANTAGE_API_KEY = os.environ.get("ALPHAVANTAGE_API_KEY", "")
FRED_API_KEY = os.environ.get("FRED_API_KEY", "")
NEWS_API_KEY = os.environ.get("NEWS_API_KEY", "")

# === SYMBOLS ===
SYMBOLS = {
    "forex": ["EURUSD=X", "GBPUSD=X", "USDJPY=X"],
    "commodities": ["GC=F"],
    "crypto": ["BTC/USDT"],
    "indices": ["^IXIC", "^DJI"],
}

ALL_SYMBOLS = []
for category, syms in SYMBOLS.items():
    ALL_SYMBOLS.extend([(s, category) for s in syms])

# === MACRO SERIES ===
FRED_SERIES = {
    "GDP": "Gross Domestic Product",
    "FEDFUNDS": "Federal Funds Rate",
    "CPIAUCSL": "Consumer Price Index",
    "UNRATE": "Unemployment Rate",
    "T10Y2Y": "10-2 Year Treasury Spread",
    "DGS10": "10-Year Treasury Rate",
    "DGS2": "2-Year Treasury Rate",
    "VIXCLS": "CBOE Volatility Index",
    "DTWEXBGS": "Trade Weighted US Dollar Index (Broad)",
}

# === NEWS ===
NEWS_QUERIES = [
    "gold trading",
    "forex market",
    "federal reserve",
    "bitcoin cryptocurrency",
    "stock market",
    "inflation",
    "interest rates",
]

# === RETRY CONFIG ===
RETRY_MAX = 3
RETRY_DELAY = 5  # seconds
REQUEST_TIMEOUT = 30  # seconds
