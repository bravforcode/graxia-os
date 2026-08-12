"""
pipeline_alert.py — Send Telegram when upgrade pipeline finishes
"""
import sys, json
from pathlib import Path

BASE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE))

# Read pipeline manifest
manifest_path = BASE / 'Meta' / 'upgrade_pipeline_manifest.json'
if manifest_path.exists():
    data = json.loads(manifest_path.read_text())
    msg_lines = ['🔄 *Upgrade Pipeline Complete*', f'Time: {data.get("last_run", "?")}']
    summary = data.get('summary', {})
    msg_lines.append(f'Data: {summary.get("market_data_downloaded", 0)} files')
    msg_lines.append(f'ML: {"✅" if summary.get("ml_retrained") else "⏭️"}')
    msg_lines.append(f'Backtest: {summary.get("strategies_tested", 0)} strategies')
    msg_lines.append(f'NotebookLM: {summary.get("insights_saved", 0)} insights')
    
    msg = '\n'.join(msg_lines)
    try:
        from core.telegram_notify import TelegramNotifier
        n = TelegramNotifier()
        n.send(msg)
        print('Alert sent to Telegram')
    except Exception as e:
        print(f'Telegram unavailable: {e}')
        print('Message would be:')
        print(msg)
else:
    print('No pipeline manifest found')
