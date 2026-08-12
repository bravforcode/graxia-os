"""Start both trading bots as background processes."""
import subprocess, sys, os, time

wd = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
log_dir = os.path.join(wd, 'data')
os.makedirs(log_dir, exist_ok=True)

env = {**os.environ, 'PYTHONIOENCODING': 'utf-8'}

bots = [
    ('paper_trade_bot.py', ['--interval', '60'], 'bot_xauusd'),
    ('multi_symbol_bot.py', [], 'bot_multi'),
]

procs = []
for script, args, name in bots:
    path = os.path.join(wd, 'scripts', script)
    log = open(os.path.join(log_dir, f'{name}.log'), 'w', encoding='utf-8')
    p = subprocess.Popen(
        [sys.executable, '-u', path] + args,
        cwd=wd, stdout=log, stderr=subprocess.STDOUT,
        env=env, creationflags=subprocess.CREATE_NO_WINDOW
    )
    procs.append((name, p.pid))
    print(f'{name}: PID {p.pid}')

time.sleep(8)
for name, pid in procs:
    alive = subprocess.Popen(['tasklist', '/FI', f'PID eq {pid}'],
                             stdout=subprocess.PIPE).communicate()[0].decode()
    status = 'RUNNING' if str(pid) in alive else 'DIED'
    print(f'{name}: {status} (PID {pid})')
