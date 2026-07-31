"""
Setup Ollama Environment Variables for Maximum Speed (No Quality Loss)
======================================================================
Run this once to configure Windows environment variables.
Then restart Ollama.

Techniques applied:
  1. OLLAMA_FLASH_ATTENTION=1 — faster attention computation
  2. OLLAMA_KV_CACHE_TYPE=q8_0 — 50% less KV cache memory
  3. OLLAMA_NUM_PARALLEL=2 — handle 2 concurrent requests
  4. OLLAMA_MAX_LOADED_MODELS=1 — single model in memory

Usage:
  python setup_ollama_env.py          # Show current settings
  python setup_ollama_env.py --apply  # Apply to Windows user env vars
"""

import sys

sys.stdout.reconfigure(encoding="utf-8")
import os
import subprocess

ENV_VARS = {
    "OLLAMA_FLASH_ATTENTION": "1",
    "OLLAMA_KV_CACHE_TYPE": "q8_0",
    "OLLAMA_NUM_PARALLEL": "2",
    "OLLAMA_MAX_LOADED_MODELS": "1",
}


def show_current():
    """Show current environment variable values."""
    print("\n[CURRENT SETTINGS]")
    for var, expected in ENV_VARS.items():
        current = os.environ.get(var, "(not set)")
        status = "OK" if current == expected else "MISMATCH"
        print(f"  {var} = {current} [{status}] (expected: {expected})")


def apply_env_vars():
    """Apply environment variables to Windows user environment."""
    print("\n[APPLYING ENVIRONMENT VARIABLES]")

    for var, value in ENV_VARS.items():
        cmd = f'[System.Environment]::SetEnvironmentVariable("{var}", "{value}", "User")'
        result = subprocess.run(["powershell", "-Command", cmd], capture_output=True, text=True)
        if result.returncode == 0:
            print(f"  OK: {var}={value}")
        else:
            print(f"  FAIL: {var} — {result.stderr[:100]}")

    print("\n[DONE] Environment variables set.")
    print("  IMPORTANT: Restart Ollama for changes to take effect.")
    print("  1. Right-click Ollama icon in taskbar > Quit")
    print("  2. Start Ollama from Start menu")


def main():
    import argparse

    parser = argparse.ArgumentParser(description="Setup Ollama env vars for max speed")
    parser.add_argument("--apply", action="store_true", help="Apply to Windows user env vars")
    args = parser.parse_args()

    print("=" * 60)
    print("OLLAMA SPEED OPTIMIZATION — Environment Setup")
    print("=" * 60)

    show_current()

    if args.apply:
        apply_env_vars()
    else:
        print("\n[DRY RUN] Use --apply to set these variables.")
        print("  Or set manually in PowerShell:")
        for var, value in ENV_VARS.items():
            print(f'    $env:{var}="{value}"')


if __name__ == "__main__":
    main()
