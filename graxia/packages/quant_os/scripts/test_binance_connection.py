"""End-to-end BinanceAdapter class test — verifies the actual adapter works."""

import os, sys
from pathlib import Path
from dotenv import load_dotenv
load_dotenv(Path('.env'))

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from quant_os.execution.adapters.binance import BinanceAdapter
from quant_os.execution.adapters.base import Order

api_key = os.getenv('BINANCE_API_KEY')
secret = os.getenv('BINANCE_SECRET')

print('=== BinanceAdapter E2E Test ===\n')

# Create adapter in spot mode (matches .env config)
adapter = BinanceAdapter(
    api_key=api_key,
    api_secret=secret,
    testnet=False,
    default_type='spot',
)

# Test 1: Connect
print('--- 1. Connect ---')
try:
    result = adapter.connect()
    print(f'connect() = {result}')
    print(f'is_connected = {adapter.is_connected}')
except Exception as e:
    print(f'connect FAILED: {e}')

# Test 2: Account info
print('\n--- 2. Account Info ---')
try:
    info = adapter.get_account_info()
    print(f'equity:    ${info.equity:,.2f}')
    print(f'cash:      ${info.cash:,.2f}')
    print(f'margin_used:    ${info.margin_used:,.2f}')
    print(f'margin_avail:   ${info.margin_available:,.2f}')
except Exception as e:
    print(f'get_account_info FAILED: {e}')

# Test 3: Positions
print('\n--- 3. Positions ---')
try:
    positions = adapter.get_positions()
    print(f'Positions: {len(positions)}')
    for p in positions:
        print(f'  {p["symbol"]}: {p["side"]} qty={p["quantity"]}')
    if not positions:
        print('  (empty - no holdings)')
except Exception as e:
    print(f'get_positions FAILED: {e}')

# Test 4: Submit a tiny market buy (paper-like: 0.0001 BTCUSDT)
print('\n--- 4. Submit Order (0.0001 BTCUSDT) ---')
import uuid
signal_id = f'test-{uuid.uuid4().hex[:8]}'
order = Order(
    order_id=str(uuid.uuid4()),
    signal_id=signal_id,
    symbol='BTCUSDT',
    asset_class='crypto',
    side='BUY',
    quantity=0.0001,
)
try:
    result = adapter.submit_order(order)
    print(f'status:    {result.status.value}')
    print(f'broker_id: {result.broker_id}')
    print(f'filled:    {result.filled_quantity}')
    print(f'avg_price: ${result.avg_price:,.2f}')
    if result.error:
        print(f'error:     {result.error}')
except Exception as e:
    print(f'submit_order FAILED: {e}')

# Test 5: Disconnect
print('\n--- 5. Disconnect ---')
adapter.disconnect()
print(f'is_connected = {adapter.is_connected}')

print('\n=== All tests complete ===')
