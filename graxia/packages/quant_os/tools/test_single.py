import subprocess
import sys

sys.stdout.reconfigure(encoding="utf-8")

prompt = 'Extract the primary ticker from this headline: Apple reported record iPhone sales\nReturn JSON only: {"k":"TICKER"}'
print(f"Prompt: {prompt}")
print()

r = subprocess.run(
    [r"C:\Users\menum\AppData\Local\Programs\Ollama\ollama.exe", "run", "qwen3.5:9b", "--verbose", "false"],
    input=prompt,
    capture_output=True,
    text=True,
    timeout=180,
    encoding="utf-8",
    errors="replace",
)
print(f"Output: {r.stdout[:500]}")
print(f"Errors: {r.stderr[:200] if r.stderr else 'none'}")
