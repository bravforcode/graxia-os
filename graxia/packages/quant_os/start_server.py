"""Start Quant OS API server with correct environment."""
import os
import sys
from pathlib import Path

# Set working directory
os.chdir(r"C:\Users\menum\graxia os")

# Set Python path FIRST — need the monorepo root so 'graxia.packages.quant_os' resolves
monorepo_root = r"C:\Users\menum\graxia os"
os.environ["PYTHONPATH"] = monorepo_root
if monorepo_root not in sys.path:
    sys.path.insert(0, monorepo_root)

# Set encoding — must be in os.environ so uvicorn subprocess inherits it
os.environ["PYTHONIOENCODING"] = "utf-8"
os.environ["PYTHONDONTWRITEBYTECODE"] = "1"
os.environ["PYTHONLEGACYWINDOWSSTDIO"] = "utf-8"

# Load .env file with override=True to override system env vars
from dotenv import load_dotenv
env_path = Path(monorepo_root) / "graxia" / "packages" / "quant_os" / ".env"
if env_path.exists():
    load_dotenv(env_path, override=True)
    print(f"Loaded .env from {env_path}")

# Print config
print(f"TRADING_MODE: {os.environ.get('TRADING_MODE', 'NOT SET')}")
print(f"LIVE_TRADING_ENABLED: {os.environ.get('LIVE_TRADING_ENABLED', 'NOT SET')}")
print(f"DATABASE_URL: {os.environ.get('DATABASE_URL', 'NOT SET')[:30]}...")
# NOTE: never print secrets — not even truncated prefixes
# JWT, HMAC, and API key values confirmed present via env

# Start uvicorn
import uvicorn
uvicorn.run(
    "graxia.packages.quant_os.api.main:app",
    host="0.0.0.0",
    port=8000,
    log_level="info",
    workers=1,
)
