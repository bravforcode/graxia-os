import os
import subprocess
import sys

sys.stdout.reconfigure(encoding="utf-8")

OLLAMA = r"C:\Users\menum\AppData\Local\Programs\Ollama\ollama.exe"
OUT = os.path.join(os.path.dirname(__file__), "..", "state", "single_test.txt")

os.makedirs(os.path.dirname(OUT), exist_ok=True)

prompt = 'Extract ticker from headline: Apple reported record iPhone sales\nReturn JSON: {"k":"TICKER"}'

with open(OUT, "w", encoding="utf-8") as f:
    f.write(f"Prompt: {prompt}\n\n")
    f.flush()

    try:
        result = subprocess.run(
            [OLLAMA, "run", "qwen3.5:9b", "--verbose", "false"],
            input=prompt,
            capture_output=True,
            text=True,
            timeout=120,
            encoding="utf-8",
            errors="replace",
        )
        f.write(f"STDOUT:\n{result.stdout[:1000]}\n")
        f.write(f"STDERR:\n{result.stderr[:500]}\n")
        f.write(f"Return code: {result.returncode}\n")
    except subprocess.TimeoutExpired:
        f.write("TIMEOUT after 120s\n")
    except Exception as e:
        f.write(f"ERROR: {e}\n")

print(f"Done. Output at {OUT}")
