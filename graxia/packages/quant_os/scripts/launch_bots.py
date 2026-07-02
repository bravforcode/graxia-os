"""Kill old bots and launch with correct Python."""
import subprocess, os, time

PYTHON = r"C:\Users\menum\AppData\Local\Programs\Python\Python312\python.exe"
ROOT = os.path.join(os.environ.get("USERPROFILE", ""), "graxia os", "graxia", "packages", "quant_os")
DATA = os.path.join(ROOT, "data")
os.makedirs(DATA, exist_ok=True)

# Kill existing bot processes by PID
hermes_py = r"C:\Users\menum\AppData\Local\hermes\hermes-agent\venv\Scripts\python.exe"
uv_py = r"C:\Users\menum\AppData\Roaming\uv\python\cpython-3.11-windows-x86_64-none\python.exe"

result = subprocess.run(
    ["powershell", "-NoProfile", "-Command",
     "Get-CimInstance Win32_Process -Filter \"name='python.exe'\" | "
     "Where-Object { $_.CommandLine -match 'paper_trade_bot|multi_symbol_bot' } | "
     "ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue; "
     "Write-Host \"Killed PID $($_.ProcessId)\" }"],
    capture_output=True, text=True, timeout=10
)
print(result.stdout)
time.sleep(2)

# Clean old logs
for f in ["bot_out.log", "bot_err.log", "bot_multi.log", "bot_multi_err.log"]:
    fp = os.path.join(DATA, f)
    if os.path.exists(fp):
        os.remove(fp)

procs = [
    ("paper_trade_bot", [PYTHON, "-u", os.path.join(ROOT, "scripts", "paper_trade_bot.py"), "--retrain", "--interval", "60"], "bot_out.log", "bot_err.log"),
    ("multi_symbol_bot", [PYTHON, "-u", os.path.join(ROOT, "scripts", "multi_symbol_bot.py")], "bot_multi.log", "bot_multi_err.log"),
]

for name, cmd, out_log, err_log in procs:
    stdout = open(os.path.join(DATA, out_log), "w", encoding="utf-8")
    stderr = open(os.path.join(DATA, err_log), "w", encoding="utf-8")
    p = subprocess.Popen(cmd, cwd=ROOT, stdout=stdout, stderr=stderr,
                         creationflags=subprocess.CREATE_NO_WINDOW | subprocess.DETACHED_PROCESS)
    print(f"{name} PID: {p.pid}")

print("Both bots launched.")
