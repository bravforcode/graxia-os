#!/usr/bin/env python3
"""
ตรวจสอบการตั้งค่า Obsidian และ Redis
"""
import sys
import os
from pathlib import Path

# Check Python path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'backend'))

print("=" * 60)
print("🔍 ตรวจสอบการตั้งค่า Graxia OS")
print("=" * 60)

# 1. Check Obsidian Vault Path
print("\n📁 Obsidian Vault Check:")
vault_path = Path("C:/Users/menum/OneDrive/Documents/Gracia/Second Brain")
print(f"   Path: {vault_path}")
print(f"   Exists: {vault_path.exists()}")
print(f"   Is Dir: {vault_path.is_dir() if vault_path.exists() else 'N/A'}")

# Check alternative paths
alt_paths = [
    Path("C:/Users/menum/OneDrive/Documents/Gracia/Second Brain"),
    Path.home() / "OneDrive" / "Documents" / "Gracia" / "Second Brain",
    Path("C:/Users/menum/Documents/Gracia/Second Brain"),
]

print("\n   Alternative paths:")
for p in alt_paths:
    print(f"   - {p}: {'✅' if p.exists() else '❌'}")

# 2. Check Redis Connection
print("\n🔌 Redis Connection Check:")
try:
    import redis
    r = redis.Redis(host='localhost', port=6379, db=0, socket_connect_timeout=5)
    r.ping()
    print("   ✅ Redis connected (no auth)")
except Exception as e:
    print(f"   ❌ Redis error: {e}")

# 3. Check environment variables
print("\n🔧 Environment Variables:")
from dotenv import load_dotenv
load_dotenv(Path(__file__).parent.parent / 'backend' / '.env')

obsidian_path = os.getenv('OBSIDIAN_VAULT_PATH', 'NOT SET')
redis_url = os.getenv('REDIS_URL', 'NOT SET')

print(f"   OBSIDIAN_VAULT_PATH: {obsidian_path}")
print(f"   REDIS_URL: {redis_url}")

# 4. Test Obsidian connector
print("\n📝 Testing Obsidian Connector:")
try:
    from app.integrations.obsidian import build_obsidian_connector
    connector = build_obsidian_connector()
    if connector:
        print(f"   ✅ Connector created: {connector}")
        print(f"   - Vault path: {connector.vault_path}")
        print(f"   - Root folder: {connector.root_folder}")
    else:
        print("   ❌ Connector returned None")
except Exception as e:
    print(f"   ❌ Error: {e}")
    import traceback
    traceback.print_exc()

print("\n" + "=" * 60)
print("✅ Check complete")
print("=" * 60)
