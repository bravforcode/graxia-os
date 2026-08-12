"""Quick shadow mode test — 30 seconds."""
import asyncio, sys
sys.path.insert(0, '.')
from dotenv import load_dotenv
from datetime import UTC
load_dotenv()

async def test_shadow():
    from data.mt5_tick_ingester import MT5TickIngester, MT5IngesterConfig
    from data.duckdb_write_queue import DuckDBWriteQueue
    from data.bar_aggregator import BarAggregator
    from core.event_bus import EventBus
    from monitoring.telegram import TelegramAlerts
    from datetime import datetime

    db_path = 'data/market_data.duckdb'

    event_bus = EventBus()
    write_queue = DuckDBWriteQueue(db_path)
    bar_aggregator = BarAggregator(
        symbols=['XAUUSD', 'EURUSD'],
        timeframes=['1m', '5m', '15m', '1h'],
        event_bus=event_bus,
    )
    telegram = TelegramAlerts()
    await telegram.start()

    await write_queue.start()

    config = MT5IngesterConfig(poll_interval_ms=500)
    ingester = MT5TickIngester(
        symbols=['XAUUSD', 'EURUSD'],
        event_bus=event_bus,
        write_queue=write_queue,
        config=config,
    )

    now = datetime.now(UTC).strftime('%Y-%m-%d %H:%M UTC')
    await telegram.send_alert(
        f'[SHADOW] System started\n'
        f'Server: Pepperstone-Demo\n'
        f'Time: {now}\n'
        f'Symbols: XAUUSD, EURUSD',
        severity='HIGH',
    )

    ingester_task = asyncio.create_task(ingester.start())
    bar_task = asyncio.create_task(bar_aggregator.start())

    await asyncio.sleep(30)

    stats = write_queue.stats
    print(f'Ticks written: {getattr(stats, "total_written", 0)}')
    print(f'Flushes: {getattr(stats, "total_flushes", 0)}')
    print(f'Errors: {getattr(stats, "total_errors", 0)}')

    import duckdb
    con = duckdb.connect(db_path, read_only=True)
    tables = con.execute('SHOW TABLES').fetchall()
    for t in tables:
        count = con.execute(f'SELECT COUNT(*) FROM {t[0]}').fetchone()[0]
        print(f'{t[0]}: {count} rows')
    con.close()

    await ingester.stop()
    await write_queue.stop()
    bar_aggregator.stop()

    await telegram.send_alert(
        f'[SHADOW] 30s test complete\n'
        f'Ticks: {getattr(stats, "total_written", 0)}\n'
        f'Flushes: {getattr(stats, "total_flushes", 0)}',
        severity='MEDIUM',
    )

    print('Shadow mode test PASSED')

asyncio.run(test_shadow())
