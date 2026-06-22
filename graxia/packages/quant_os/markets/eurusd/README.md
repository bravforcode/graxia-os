# EURUSD Market Module

Separate from XAUUSD. Shared infrastructure allowed; shared optimized parameters NOT allowed.

## Structure
- `contract_snapshot.py` — MT5 contract specs for EURUSD
- `session_calendar.py` — EUR/USD session times
- `event_calendar.py` — Economic event mapping for USD and EUR
- `hypothesis.py` — Single active hypothesis template

## Rules
- No XAUUSD ATR values
- No renamed liquidity_sweep
- No random CV
- No ML/RL as primary
- No Yahoo data for final evidence
- No TradingView signal as authority
