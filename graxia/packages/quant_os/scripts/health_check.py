"""
health_check.py — System health check
"""
import json, subprocess, warnings
from pathlib import Path
from datetime import datetime, UTC
warnings.filterwarnings('ignore')

BASE = Path(__file__).resolve().parent.parent

def check(ok, msg, detail=''):
    icon = '✅' if ok else '❌'
    print(f'{icon} {msg} {detail}')
    return ok

def main():
    print('=== Graxia Health Check ===')
    print()
    checks = {'passed': 0, 'failed': 0}
    age_mins = 999999
    
    # 1. Python + imports
    try:
        import MetaTrader5 as mt5
        check(True, 'MetaTrader5', mt5.__version__)
        checks['passed'] += 1
    except ImportError:
        check(False, 'MetaTrader5')
        checks['failed'] += 1
    
    # 2. MT5 connection
    try:
        import MetaTrader5 as mt5
        if mt5.initialize():
            t = mt5.terminal_info()
            a = mt5.account_info()
            check(True, 'MT5 connected', f'{a.name if a else "?"} | Bal=${a.balance:.0f}' if a else '')
            mt5.shutdown()
        else:
            check(False, 'MT5 init', str(mt5.last_error()))
            checks['failed'] += 1
        checks['passed'] += 1
    except Exception as e:
        check(False, 'MT5 error', str(e))
        checks['failed'] += 1
    
    # 3. Data files
    data_files = list((BASE / 'data').glob('*.csv'))
    check(len(data_files) > 10, f'Data files: {len(data_files)}', 
          f'~{sum(f.stat().st_size for f in data_files)/1048576:.1f} MB')
    checks['passed' if len(data_files) > 10 else 'failed'] += 1
    
    # 4. Models
    models = list((BASE / 'ml' / 'models').glob('*.pkl'))
    check(len(models) > 0, f'ML models: {len(models)}',
          f'Latest: {models[-1].name[-20:]}' if models else '')
    checks['passed' if len(models) > 0 else 'failed'] += 1
    
    # 5. Pipeline manifest
    man = BASE / 'Meta' / 'upgrade_pipeline_manifest.json'
    if man.exists():
        d = json.loads(man.read_text())
        check(True, 'Pipeline manifest', f'Last run: {d.get("last_run","?")[:16]}')
    else:
        check(False, 'Pipeline manifest')
    checks['passed'] += 1
    
    # 6. Scheduled tasks
    task_count = 0
    try:
        r = subprocess.run(['powershell', '-Command', 
            'Get-ScheduledTask -TaskName "Graxia*" | Format-Table TaskName,State -AutoSize | Out-String'],
            capture_output=True, text=True, timeout=10)
        tasks = r.stdout or ''
        task_count = tasks.count('Graxia')
        check(task_count > 0, f'Scheduled tasks: {task_count}', 
              'Data/Sync/Upgrade/Quick/Daily/Research')
    except:
        check(False, 'Scheduled tasks')
    checks['passed' if task_count > 0 else 'failed'] += 1
    
    # 7. Data recency
    latest_file = max((BASE / 'data').glob('*.csv'), key=lambda f: f.stat().st_mtime, default=None)
    if latest_file:
        age_mins = (datetime.now().timestamp() - latest_file.stat().st_mtime) / 60
        check(age_mins < 120, 'Data recency', f'{latest_file.name}: {age_mins:.0f}min old')
    else:
        check(False, 'Data recency')
    checks['passed' if age_mins < 120 else 'failed'] += 1
    
    print(f'\nResult: {checks["passed"]} passed, {checks["failed"]} failed')
    
    # Save
    (BASE / 'Meta' / 'health_check.json').write_text(json.dumps({
        'timestamp': datetime.now(UTC).isoformat(),
        **checks
    }, indent=2))

if __name__ == '__main__':
    main()
