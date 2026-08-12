"""
telegram_dashboard.py — Daily trading dashboard sent to Telegram
Usage: python scripts/telegram_dashboard.py
"""
import sys, json, warnings
from datetime import datetime, UTC
from pathlib import Path
warnings.filterwarnings('ignore')

BASE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE))
DATA_DIR = BASE / 'data'
MODEL_DIR = BASE / 'ml' / 'models'
RESULTS_DIR = BASE / 'results'

def get_telegram():
    try:
        from core.telegram_notify import TelegramNotifier
        return TelegramNotifier()
    except Exception:
        return None

def collect_stats():
    stats = {}
    
    # Data stats
    csvs = list(DATA_DIR.glob('*.csv'))
    stats['data_files'] = len(csvs)
    stats['data_mb'] = round(sum(f.stat().st_size for f in csvs) / 1048576, 1)
    
    # Model stats
    models = sorted(MODEL_DIR.glob('xgboost_*.pkl'))
    stats['model_count'] = len(models)
    stats['latest_model'] = models[-1].name if models else 'none'
    
    # Symbols with data
    symbols = set()
    for f in csvs:
        parts = f.stem.split('_')
        if len(parts) >= 2:
            symbols.add(parts[0])
    stats['symbols'] = sorted(symbols)
    
    # Account info from MT5
    try:
        import MetaTrader5 as mt5
        if mt5.initialize():
            account = mt5.account_info()
            if account:
                stats['balance'] = account.balance
                stats['equity'] = account.equity
                stats['profit'] = account.profit
                
                positions = mt5.positions_get()
                stats['open_positions'] = len(positions) if positions else 0
                
                if positions:
                    pos_details = []
                    for p in positions:
                        pos_details.append(f"{p.symbol} {p.type_name} Vol={p.volume:.2f} PnL={p.profit:.2f}")
                    stats['position_details'] = pos_details
            mt5.shutdown()
    except Exception:
        pass
    
    return stats

def format_message(stats):
    lines = ['📊 *Graxia Daily Dashboard*', '']
    
    lines.append(f'📁 *Data*: {stats.get("data_files", "?")} files ({stats.get("data_mb", "?")} MB)')
    lines.append(f'🔤 *Symbols*: {len(stats.get("symbols", []))} — {" ".join(stats.get("symbols", [])[:7])}')
    
    lines.append('')
    lines.append(f'🤖 *Models*: {stats.get("model_count", "?")} | Latest: {stats.get("latest_model", "none")[:30]}')
    
    if 'balance' in stats:
        pnl = stats.get('profit', 0)
        pnl_emoji = '🟢' if pnl >= 0 else '🔴'
        lines.append('')
        lines.append('💰 *Account*')
        lines.append(f'Balance: `${stats["balance"]:.2f}`')
        lines.append(f'Equity: `${stats["equity"]:.2f}`')
        lines.append(f'{pnl_emoji} PnL: `${pnl:+.2f}`')
        lines.append(f'📌 Open positions: {stats.get("open_positions", 0)}')
    
    if stats.get('position_details'):
        for p in stats['position_details'][:5]:
            lines.append(f'  • {p}')
    
    # Next pipeline runs
    lines.append('')
    lines.append('⏰ *Scheduled Tasks*')
    lines.append('Data: every 15min')
    lines.append('Quick: every 2h')
    lines.append('Full upgrade: every 6h')
    lines.append('Daily report: 03:00 UTC')
    
    lines.append('')
    lines.append(f'_{datetime.now().strftime("%Y-%m-%d %H:%M UTC")}_')
    
    return '\n'.join(lines)

def main():
    tg = get_telegram()
    if not tg:
        print('Telegram not configured. Message would be:')
        stats = collect_stats()
        print(format_message(stats))
        return
    
    stats = collect_stats()
    msg = format_message(stats)
    tg.send(msg)
    print('Dashboard sent to Telegram')
    
    # Save latest stats
    (BASE / 'Meta' / 'latest_dashboard.json').write_text(json.dumps({
        'timestamp': datetime.now(UTC).isoformat(),
        **stats
    }, default=str, indent=2))

if __name__ == '__main__':
    main()
