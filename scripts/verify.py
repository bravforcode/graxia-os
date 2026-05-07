#!/usr/bin/env python3
"""
Simple verification script for Graxia OS
"""
import sys
import os
from pathlib import Path

sys.path.insert(0, 'backend')

print("=" * 60)
print("GRAXIA OS VERIFICATION")
print("=" * 60)

# 1. Check vault
vault = Path("C:/Users/menum/OneDrive/Documents/Gracia")
print(f"\n1. Vault Path: {vault}")
print(f"   Exists: {vault.exists()}")

# 2. Check .env
env_file = Path("backend/.env")
print(f"\n2. Env File: {env_file.exists()}")
if env_file.exists():
    content = env_file.read_text()
    obs_line = [l for l in content.split('\n') if 'OBSIDIAN_VAULT_PATH' in l and not l.startswith('#')]
    print(f"   Obsidian setting: {obs_line[0] if obs_line else 'NOT FOUND'}")

# 3. Test settings
print("\n3. Loading settings...")
try:
    from app.config import settings
    obs = getattr(settings, 'OBSIDIAN_VAULT_PATH', None)
    redis = getattr(settings, 'REDIS_URL', None)
    print(f"   OBSIDIAN_VAULT_PATH: {obs}")
    print(f"   REDIS_URL: {redis[:40]}..." if redis else "   REDIS_URL: None")
except Exception as e:
    print(f"   ERROR: {e}")

# 4. Test Obsidian
print("\n4. Testing Obsidian connector...")
try:
    from app.integrations.obsidian import build_obsidian_connector
    conn = build_obsidian_connector()
    if conn:
        print(f"   SUCCESS: Connector created")
        print(f"   Vault: {conn.vault_path}")
    else:
        print("   FAILED: Connector is None")
except Exception as e:
    print(f"   ERROR: {e}")

# 5. Test Redis
print("\n5. Testing Redis...")
try:
    import redis
    from app.config import settings
    r = redis.from_url(settings.REDIS_URL, decode_responses=True, socket_connect_timeout=5)
    r.ping()
    print("   SUCCESS: Redis connected")
except Exception as e:
    print(f"   FAILED: {e}")

print("\n" + "=" * 60)
print("Verification complete")
print("=" * 60)
