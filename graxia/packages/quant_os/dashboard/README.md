# Quant OS Dashboard

Real-time trading dashboard built with React + Vite.

## Quick Start

```bash
# 1. Start the API server (from quant_os root)
python -m monitoring.dashboard_server

# 2. Start the dashboard dev server
cd dashboard
npm install
npm run dev

# 3. Open http://localhost:5173
```

## Architecture

- **Frontend**: React 19 + Vite, CSS with OKLCH tokens
- **Backend**: FastAPI serving `/api/*` endpoints
- **Data**: Polls every 10s for real-time updates

## API Endpoints

| Endpoint | Description |
|----------|-------------|
| `/api/state` | Macro regime + system status |
| `/api/status` | Live trading status (bid/ask/balance/PnL) |
| `/api/risk` | Risk budget state |
| `/api/positions` | Open positions |
| `/api/trades` | Recent trade history |
| `/api/news` | News pipeline data |
| `/api/health` | Health check |

## Design

- Dark theme (trading terminal aesthetic)
- Gold accent for XAUUSD identity
- OKLCH color space throughout
- Inter + JetBrains Mono typography
- Responsive layout (mobile-friendly)
- Reduced motion support
