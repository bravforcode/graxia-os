# QuantConnect Integration Guide for Quant OS

**Date:** 2026-07-13
**Status:** Research complete, ready for implementation

---

## What is QuantConnect?

QuantConnect is a cloud platform for algorithmic trading with:
- **LEAN Engine** (open source) - Backtesting + Live trading engine
- **Cloud IDE** - Write, backtest, deploy algorithms
- **REST API** - Programmatic control of projects, backtests, live trading
- **Multiple brokerages** - IB, Alpaca, Binance, Kraken, etc.
- **Free tier** - 10 backtests/month, 1 live algo, paper trading

## Integration Options

### Option 1: QuantConnect Cloud (Recommended for Paper Trading)

**Use case:** Run quant_os strategies on QuantConnect cloud for paper trading validation

**Steps:**
1. Create QuantConnect account (free tier)
2. Export quant_os strategy to LEAN format
3. Upload to QuantConnect
4. Run backtest on QuantConnect data
5. Deploy to paper trading

**Pros:**
- No need to manage infrastructure
- Free historical data
- Built-in risk management
- Easy deployment to live trading

**Cons:**
- Strategy must be in LEAN format
- Limited customization
- Cloud dependency

### Option 2: LEAN Engine Local (Recommended for Backtesting)

**Use case:** Run LEAN engine locally for backtesting validation

**Steps:**
1. Install LEAN CLI locally
2. Convert quant_os strategy to LEAN format
3. Run backtest locally
4. Compare results with quant_os backtest

**Pros:**
- Full control over execution
- No cloud dependency
- Can use local data

**Cons:**
- Requires LEAN CLI installation
- Limited to supported brokerages

### Option 3: Hybrid (Recommended for Production)

**Use case:** Use quant_os for strategy generation, QuantConnect for execution

**Steps:**
1. quant_os generates signals
2. Signals sent to QuantConnect via REST API
3. QuantConnect executes trades
4. Results synced back to quant_os

**Pros:**
- Best of both worlds
- quant_os handles research
- QuantConnect handles execution

**Cons:**
- Requires API integration
- More complex setup

## Implementation Plan

### Phase 1: LEAN CLI Setup (Week 1)

```bash
# Install LEAN CLI
pip install lean

# Initialize LEAN project
lean init

# Configure brokerage (paper trading)
lean live deploy --brokerage-paper --data-provider-paper
```

### Phase 2: Strategy Conversion (Week 2)

Convert quant_os strategy to LEAN format:

```python
# quant_os strategy (original)
class LiquiditySweepStrategy:
    def generate_signal(self, data):
        # Signal generation logic
        return signal

# LEAN strategy (converted)
from Algorithm import *

class LiquiditySweepAlgorithm(QCAlgorithm):
    def Initialize(self):
        self.SetStartDate(2020, 1, 1)
        self.SetEndDate(2026, 1, 1)
        self.SetCash(100000)
        self.AddForex("XAUUSD", Resolution.Hour)
    
    def OnData(self, data):
        # Signal generation logic
        if signal:
            self.SetHoldings("XAUUSD", 0.1)
```

### Phase 3: Backtesting Validation (Week 3)

```bash
# Run backtest on QuantConnect
lean backtest "LiquiditySweep" --output "artifacts/quantconnect"

# Compare with quant_os backtest
python scripts/compare_backtests.py \
  --quant-os "artifacts/walk_forward/wf_results.json" \
  --quantconnect "artifacts/quantconnect/backtest_results.json"
```

### Phase 4: Paper Trading (Week 4+)

```bash
# Deploy to paper trading
lean live deploy "LiquiditySweep" \
  --brokerage "QuantConnectPaperTrading" \
  --data-provider "QuantConnect"

# Monitor
lean live status "LiquiditySweep"
```

## REST API Integration

### Authentication

```python
import requests

QC_API_URL = "https://www.quantconnect.com/api/v2"
QC_API_TOKEN = "your-api-token"

headers = {
    "Authorization": f"Bearer {QC_API_TOKEN}",
    "Content-Type": "application/json"
}
```

### Create Project

```python
def create_project(name, description):
    response = requests.post(
        f"{QC_API_URL}/projects/create",
        headers=headers,
        json={
            "name": name,
            "description": description
        }
    )
    return response.json()["projectId"]
```

### Run Backtest

```python
def run_backtest(project_id, backtest_name):
    response = requests.post(
        f"{QC_API_URL}/backtests/create",
        headers=headers,
        json={
            "projectId": project_id,
            "name": backtest_name
        }
    )
    return response.json()["backtestId"]
```

### Deploy Live

```python
def deploy_live(project_id, brokerage, node):
    response = requests.post(
        f"{QC_API_URL}/live/create",
        headers=headers,
        json={
            "projectId": project_id,
            "brokerage": brokerage,
            "node": node
        }
    )
    return response.json()["deployId"]
```

## Data Pipeline Integration

### Export quant_os Data to QuantConnect

```python
# Export OHLCV data to QuantConnect format
def export_to_quantconnect(df, symbol, resolution):
    """Convert quant_os DataFrame to LEAN format."""
    lean_data = []
    for idx, row in df.iterrows():
        lean_data.append({
            "time": idx.strftime("%Y-%m-%d %H:%M:%S"),
            "open": row["open"],
            "high": row["high"],
            "low": row["low"],
            "close": row["close"],
            "volume": row["volume"]
        })
    return lean_data
```

### Import QuantConnect Results to quant_os

```python
# Import QuantConnect backtest results
def import_from_quantconnect(backtest_id):
    """Fetch QuantConnect backtest results."""
    response = requests.get(
        f"{QC_API_URL}/backtests/{backtest_id}",
        headers=headers
    )
    return response.json()
```

## Cost Calibration

### Use QuantConnect Data for Spread Measurement

QuantConnect provides free historical bid/ask data that can be used for cost calibration:

```python
# Fetch historical bid/ask from QuantConnect
def fetch_quantconnect_spread(symbol, start_date, end_date):
    """Get spread data from QuantConnect."""
    response = requests.get(
        f"{QC_API_URL}/datasets/symbols/{symbol}/spread",
        headers=headers,
        params={
            "start": start_date.isoformat(),
            "end": end_date.isoformat()
        }
    )
    return response.json()
```

## Migration Checklist

- [ ] Create QuantConnect account
- [ ] Install LEAN CLI locally
- [ ] Convert quant_os strategy to LEAN format
- [ ] Run backtest on QuantConnect
- [ ] Compare results with quant_os backtest
- [ ] Set up REST API integration
- [ ] Deploy to paper trading
- [ ] Monitor for 60 days
- [ ] Deploy to live trading (if paper trading passes)

## Cost

- **Free tier:** 10 backtests/month, 1 live algo, paper trading
- **Trader tier ($20/month):** 40 backtests/month, 2 live algos
- **Team tier ($80/month):** Unlimited backtests, 5 live algos

## Conclusion

QuantConnect integration provides:
1. **Free historical data** for backtesting
2. **Cloud execution** for paper trading
3. **Multiple brokerage support** for live trading
4. **REST API** for programmatic control

**Recommended approach:** Use QuantConnect for paper trading validation, keep quant_os for strategy generation and research.
