import os
import requests
import asyncio
from dotenv import load_dotenv

async def check_connectivity():
    load_dotenv('C:/Users/menum/graxia os/.env')
    print("--- Connectivity Report ---")
    
    # Test OpenAI/DeepSeek
    openai_key = os.getenv("OPENAI_API_KEY")
    openai_base = os.getenv("OPENAI_BASE_URL")
    print(f"Testing OpenAI/DeepSeek: {openai_base}")
    try:
        r = requests.post(
            f"{openai_base}/chat/completions",
            headers={"Authorization": f"Bearer {openai_key}"},
            json={"model": "deepseek-chat", "messages": [{"role": "user", "content": "hi"}], "max_tokens": 5},
            timeout=10
        )
        print(f"  Status: {r.status_code}")
        if r.status_code == 401:
            print("  FAIL: 401 Unauthorized - Check your OPENAI_API_KEY")
        elif r.status_code != 200:
            print(f"  FAIL: {r.text}")
        else:
            print("  SUCCESS")
    except Exception as e:
        print(f"  ERROR: {e}")

    # Test Ollama Pay
    ollama_key = os.getenv("OLLAMA_PAY_API_KEY")
    ollama_base = os.getenv("OLLAMA_PAY_BASE_URL")
    print(f"Testing Ollama Pay: {ollama_base}")
    try:
        # Check /v1/models for Ollama Pay if it's OpenAI compatible
        r = requests.get(f"{ollama_base}/models", headers={"Authorization": f"Bearer {ollama_key}"}, timeout=10)
        print(f"  Status: {r.status_code}")
        if r.status_code == 401:
            print("  FAIL: 401 Unauthorized - Check your OLLAMA_PAY_API_KEY")
        else:
            print("  SUCCESS" if r.status_code == 200 else f"  FAIL: {r.text}")
    except Exception as e:
        print(f"  ERROR: {e}")

    # Test Sentry (placeholder check)
    sentry_dsn = os.getenv("SENTRY_DSN")
    print(f"Sentry DSN: {sentry_dsn}")
    if "example.com" in sentry_dsn or "your_" in sentry_dsn:
        print("  WARNING: Sentry DSN is a placeholder.")

if __name__ == "__main__":
    asyncio.run(check_connectivity())
