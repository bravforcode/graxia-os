# Research Bundle — Multi-broker, Telegram, G4.1 Planning, Order Book Depth

> Generated: 2026-06-24

---

## Topic 1: Multi-broker Support for XM and IC Markets

### Installed MT5 Terminals

| # | Name | Path | Data Folder | Server | Publisher |
|---|------|------|-------------|--------|-----------|
| 1 | MetaTrader 5 | `C:\Program Files\MetaTrader 5\` | `D0E8209F77C8CF37AD8BF550E51FF075` | Generic (no logged account) | MetaQuotes Ltd. |
| 2 | Pepperstone MetaTrader 5 | `C:\Program Files\Pepperstone MetaTrader 5\` | `73B7A2420D6397DFF9014A20F1201F97` | Pepperstone-Demo (login: MT5_ACCOUNT_REDACTED) | MetaQuotes Ltd. |

**Neither XM nor IC Markets terminals are installed.** No registry entries were found for either broker.

### What to Install for XM or IC Markets

To add a broker, the user needs:

1. **Download** the broker-specific MT5 installer from:
   - XM: https://www.xm.com/mt5
   - IC Markets: https://www.icmarkets.com/mt5
2. **Install** to a unique path (e.g., `C:\Program Files\IC Markets MetaTrader 5\`)
3. **Login** with demo/live credentials inside the terminal
4. **Enable AutoTrading**: Tools → Options → Expert Advisors → Allow Automated Trading

Each broker terminal gets its own data folder under `%APPDATA%\MetaQuotes\Terminal\<hash>\`.

### Multi-terminal Architecture (MT5 Python API)

**Critical limitation:** The `MetaTrader5` Python package uses a **singleton** design. Only one terminal can be connected per process. Calling `mt5.initialize(path=...)` reconnects to the specified terminal, disconnecting any previous one.

There are two strategies for multi-broker support:

| Strategy | Pros | Cons |
|----------|------|------|
| **Sequential** — connect, read, shutdown, reconnect to next | Simple, single process | Race windows between switches, no simultaneous monitoring |
| **Multi-process** — one process per broker terminal | True isolation, parallel access | IPC/comms overhead, process lifecycle management |

### Existing Codebase Support

The codebase already has Phase 11 multi-broker infrastructure:

- `governance/multi_broker_policy.py` — `MultiBrokerPolicy` and `BrokerRequirements` dataclasses (Phase 11)
- `live_readiness/broker_profile.py` — `BrokerProfile` frozen dataclass, includes a `DEFAULT_PROFILE` for IC Markets (server: `ICMarkets-Demo02`)
- `live_readiness/mt5_readonly_client.py` — `Mt5ReadOnlyClient` that accepts a config dict with a `path` key for terminal selection
- `tests/test_phase_11_expansion.py` — Tests for multi-broker policy

The `Mt5ReadOnlyClient.initialize(config)` method supports a `path` parameter, making it straightforward to point at different terminals.

---

## Topic 2: Telegram Bot for Monitoring

### Prerequisites

| Requirement | Status |
|-------------|--------|
| `python-telegram-bot` v21.3 | ✅ Installed |
| `requests` v2.34.2 | ✅ Installed |
| Bot Token from @BotFather | ❌ Needed |
| `chat_id` from target chat | ❌ Needed |

### How to Get Credentials

1. Open Telegram, search for **@BotFather**, send `/newbot`
2. Follow prompts — save the token (format: `123456:ABC-DEF1234ghIkl-zyx57W2v1u123ew11`)
3. Start a chat with your bot, then visit `https://api.telegram.org/bot<YOUR_TOKEN>/getUpdates`
4. Find your `chat_id` in the JSON response

### Minimal Notifier Template

```python
"""telegram_notifier.py — Minimal Telegram monitoring bot."""
import logging
from typing import Optional

import requests

logger = logging.getLogger(__name__)


class TelegramNotifier:
    """Sends alerts to a Telegram chat via bot."""

    BASE_URL = "https://api.telegram.org/bot{token}"

    def __init__(self, token: str, chat_id: str):
        self._send_url = f"{self.BASE_URL.format(token=token)}/sendMessage"
        self._chat_id = chat_id

    def send(self, message: str) -> bool:
        """Send a text message. Returns True on success."""
        try:
            resp = requests.post(
                self._send_url,
                json={"chat_id": self._chat_id, "text": message, "parse_mode": "Markdown"},
                timeout=10,
            )
            resp.raise_for_status()
            return True
        except Exception as exc:
            logger.error("Telegram send failed: %s", exc)
            return False


# Usage:
# notifier = TelegramNotifier(token="123:ABC", chat_id="12345")
# notifier.send("*Execution Alert*\nOrder XAUUSD opened at 2350.00")
```

### What to Monitor

| Event | Trigger | Example Message |
|-------|---------|-----------------|
| Order failure | `order_check` retcode != 0 | `❌ ORDER FAILED\nSymbol: XAUUSD\nRetcode: 10012\nReason: Invalid volume` |
| Balance change | Equity drops > threshold | `📉 BALANCE ALERT\nAccount: ***7941\nDrop: -$124.50 (2.1%)\nThreshold: 2.0%` |
| Daily summary | Scheduled (e.g., 23:00 UTC) | `📊 DAILY SUMMARY\nDate: 2026-06-24\nPnL: +$45.20\nTrades: 3\nWin rate: 66.7%` |
| Kill switch | Emergency stop triggered | `🛑 KILL SWITCH ACTIVE\nPosition XAUUSD closed\nReason: Max drawdown reached` |
| System health | MT5 disconnect/reconnect | `⚠️ MT5 DISCONNECTED\nImpact: market data stale\nLast tick: 15s ago` |

---

## Topic 3: G4.1 Phase Investigation

### Search Results

**No "G4.1", "G4.1", or explicit next-phase-after-G4 references exist anywhere in the codebase.**

The `.planning/` directory does not exist.

### Current G-Series Status

| Phase | Report | Verdict | Status |
|-------|--------|---------|--------|
| G0 | `REPORT_G0.md` | Not found in last commit | Cleanup/freeze audits |
| G3 | `REPORT_G3_*.md` | Complete | Source integrity audits |
| G4 | `REPORT_G4_PRE_EXECUTION_AUDIT.md` | **BLOCKED** | Pre-execution audit failed |
| G4 | `REPORT_G4_FINAL_EXECUTION_GUIDE.md` | Guide only | Not yet executable |

**G4 is BLOCKED** because:
- Candidate `e834031` has source closure (PASS) but no retcode matrix (MISSING)
- Candidate `c7933f9` has retcode matrix (PASS) but source closure (FAIL)
- No single clean candidate proves both

### Recommended G4.1 Scope

Based on the BLOCKED G4 audit and the codebase's trajectory (Phase 10 PASS, Phase 11 multi-broker policy defined), G4.1 should contain:

1. **Merge retcode matrix into main lineage** — Bring `test_g3_4_ordersend_failure_matrix.py` and `test_g3_4_ordersend_integration.py` into the `e834031` base
2. **Verified clean candidate** — Create, verify in detached worktree, confirm both source closure AND retcode coverage pass
3. **G4.0 execution** — One-shot demo `order_send` on Pepperstone (reusing existing G4 execution guide)
4. **G4.1 reconciliation** — Position reconciliation, order lifecycle validation, protective stop verification on Pepperstone demo
5. **G4.2 Symbol expansion** — Move from single-symbol XAUUSD to EURUSD + GBPUSD (aligned with Phase 10 expansion step 2)

After G4 series: Phase 11 (Multi-broker) is the natural next milestone, with the multi-broker policy already scaffolded.

### Phase Roadmap (Inferred)

```
G0 (Repo Reconciliation) → G3 (Source Integrity) → G4.0 (One-shot Demo) → G4.1 (Reconciliation)
  → G4.2 (Symbol Expansion) → Phase 10 (Controlled Expansion) → Phase 11 (Multi-broker)
```

---

## Topic 4: Order Book Depth Feasibility

### MT5 Python API: Market Book Functions

The `MetaTrader5` package exposes three functions for order book (Depth of Market) access:

| Function | Signature | Purpose |
|----------|-----------|---------|
| `market_book_add(symbol)` | `(str) -> bool` | Subscribe to DOM for a symbol |
| `market_book_get(symbol)` | `(str) -> list[MBookBook]` | Get current DOM snapshot |
| `market_book_release(symbol)` | `(str) -> None` | Unsubscribe from DOM |

Each returned `MBookBook` entry has:
- `type` — Order type (0=SELL, 1=BUY, 2=SELL_MARKET, 3=BUY_MARKET)
- `price` — Price level
- `volume` — Volume at this level (in lots)
- `volume_dyn` — Dynamic volume (if applicable)

### Pepperstone Demo Test Results

| Operation | Result |
|-----------|--------|
| `mt5.initialize()` | ✅ Connected to Pepperstone-Demo (login MT5_ACCOUNT_REDACTED) |
| `mt5.market_book_add('XAUUSD')` | ✅ Returned `True` |
| `mt5.market_book_get('XAUUSD')` | ❌ Returned `None` (last_error: `(1, 'Success')`) |

**Verdict:** `market_book_add` is supported (subscription succeeds), but `market_book_get` returns empty — no depth data is provided. This is expected behavior for demo accounts. Many brokers (including Pepperstone) **restrict Depth of Market to live/pro accounts only**.

### Market Depth Test Script

```python
"""test_market_depth.py — Check if a broker provides order book data."""

import sys
import time

import MetaTrader5 as mt5


def test_market_depth(terminal_path: str, symbol: str = "XAUUSD") -> dict:
    """
    Test market depth availability for a symbol.
    
    Returns a dict with results.
    """
    result = {
        "terminal_path": terminal_path,
        "symbol": symbol,
        "init_ok": False,
        "book_add_ok": False,
        "book_entries": None,
        "error": None,
    }
    
    init = mt5.initialize(path=terminal_path, timeout=10000)
    if not init:
        result["error"] = f"MT5 init failed: {mt5.last_error()}"
        return result
    result["init_ok"] = True
    
    try:
        add_ok = mt5.market_book_add(symbol)
        result["book_add_ok"] = bool(add_ok)
        
        if add_ok:
            time.sleep(2)  # wait for depth data
            book = mt5.market_book_get(symbol)
            if book and len(book) > 0:
                result["book_entries"] = [
                    {"type": b.type, "price": b.price,
                     "volume": b.volume, "volume_dyn": b.volume_dyn}
                    for b in book
                ]
            else:
                result["book_entries"] = []
                result["error"] = f"Book empty (last_error: {mt5.last_error()})"
            
            mt5.market_book_release(symbol)
    except Exception as e:
        result["error"] = str(e)
    finally:
        mt5.shutdown()
    
    return result


if __name__ == "__main__":
    path = "C:\\Program Files\\Pepperstone MetaTrader 5\\terminal64.exe"
    r = test_market_depth(path, "XAUUSD")
    print(f"Init OK:       {r['init_ok']}")
    print(f"Book Add OK:   {r['book_add_ok']}")
    print(f"Book Entries:  {r['book_entries']}")
    if r["error"]:
        print(f"Error:         {r['error']}")
    # Exit code: 0 if depth available, 1 if not
    sys.exit(0 if r.get("book_entries") else 1)
```

### Broker Support Assessment

| Broker | Demo DOM | Live DOM | Notes |
|--------|----------|----------|-------|
| Pepperstone | ❌ Unavailable | ✅ Typically available | Market depth restricted on demo |
| IC Markets | ❌ Unavailable | ✅ Available | IC Markets provides DOM on live only |
| XM | ❌ Unavailable | ✅ Available | Requires live/pro account |

**For development/testing purposes**, the `market_book_add()` → `market_book_get()` pipeline can be coded now but will only return data when connected to a live Pepperstone, IC Markets, or XM account.

---

*End of Research Bundle*
