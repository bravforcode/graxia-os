# Graxia OS Architecture

Graxia OS operates as a comprehensive personal sovereign OS with a unified control plane.

## System Workflow

1. **Frontend (React)**: The canonical UI for operators, offering dashboards for leads, approval queues, opportunities, and metric visualizations. It communicates with the backend via REST and WebSockets.
2. **Backend (FastAPI)**: Manages business logic, coordinates AI agents, interfaces with the database (Supabase/PostgreSQL), and schedules background tasks.
3. **Database (Supabase/PostgreSQL)**: The primary source of truth for all entities (contacts, drafts, jobs, email threads, opportunities).
4. **Configuration & Scripts**: 
   - `config/`: Houses operational configurations for Docker, Redis, and process managers like PM2.
   - `scripts/`: Operational scripts for database migrations, deployments, and utility tasks.
5. **Agents & External Integrations**: Integrates with external APIs (like n8n, OpenAI) to perform autonomous data gathering and drafting. Human operators approve critical actions before they are executed.

## quant_os Algorithmic Trading Subsystem

Location: `graxia/packages/quant_os/`

An MT5-based algorithmic trading execution layer, targeting Forex/CFD markets via the MetaTrader 5 terminal (Pepperstone-Demo). Designed as an autonomous canary system for zero-defect order execution.

### Components

| Package | Path | Role |
|---------|------|------|
| **execution/demo_canary** | `execution/demo_canary/` | Core order lifecycle: submission, close, failure matrix, reconciliation |
| **execution/qualification** | `execution/qualification/` | Market-open gate, campaign qualification |
| **live_readiness** | `live_readiness/` | MT5 runtime health verification, terminal connectivity |
| **risk** | `risk/` | Position sizing, anti-martingale tier logic, contract specs |
| **market_data** | `market_data/` | Tick recording, data watermark, timeframe management |
| **strategy** | `strategy/` | Entry/exit signal generation |

### Key Design Decisions

- **DRY_RUN_MODE** defaults `True` — no real orders without explicit opt-in
- **Security hook** — `repo_intelligence/hooks/pre_commit_security_check.py` allowlists `order_send`/`position_close` in `order_submission.py` only
- **Zero retry** — one `order_send`/`position_close` attempt per signal, never retry on `None`
- **Failure matrix** — 7 documented failure modes (`None`, `REQUOTE`, `REJECT`, `INVALID_STOPS`, `MARKET_CLOSED`, `NO_MONEY`, `TRADE_DISABLED`)
- **Canary architecture** — demo-first, reconciliation-led verification, closure campaign for clean state

### Status

All G4 phases (A4–A6, B1–B4, C1, C3) completed and committed to `release/g3-canonical-geometry-rc` (commit `ea9e123`). PR #1 open. See `RELEASE_MANIFEST_G4.md` for full artifact inventory.
