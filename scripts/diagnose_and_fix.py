#!/usr/bin/env python3
"""
Diagnose and fix Graxia OS setup issues
"""
import sys
import os
from pathlib import Path

# Setup paths
sys.path.insert(0, 'backend')

print("=" * 70)
print("🔍 DIAGNOSE & FIX GRAXIA OS")
print("=" * 70)

# 1. Check vault path
print("\n📁 Checking Obsidian Vault...")
vault_path = Path("C:/Users/menum/OneDrive/Documents/Gracia")
print(f"   Path: {vault_path}")
print(f"   Exists: {vault_path.exists()}")
print(f"   Is Directory: {vault_path.is_dir() if vault_path.exists() else 'N/A'}")

if not vault_path.exists():
    print("   ⚠️  Vault not found! Creating...")
    try:
        vault_path.mkdir(parents=True, exist_ok=True)
        print(f"   ✅ Created: {vault_path}")
    except Exception as e:
        print(f"   ❌ Failed to create: {e}")
else:
    print(f"   ✅ Vault exists")
    # List contents
    try:
        contents = list(vault_path.iterdir())
        print(f"   📂 Contents ({len(contents)} items):")
        for item in contents[:5]:
            print(f"      - {item.name}")
    except Exception as e:
        print(f"   ⚠️  Cannot read contents: {e}")

# 2. Check env file
print("\n📄 Checking .env file...")
env_file = Path("backend/.env")
if env_file.exists():
    print(f"   ✅ .env exists at: {env_file.absolute()}")
    content = env_file.read_text()
    
    # Check OBSIDIAN_VAULT_PATH
    if "OBSIDIAN_VAULT_PATH" in content:
        for line in content.split('\n'):
            if line.startswith('OBSIDIAN_VAULT_PATH='):
                print(f"   📝 {line}")
    else:
        print("   ❌ OBSIDIAN_VAULT_PATH not found!")
else:
    print(f"   ❌ .env not found at: {env_file.absolute()}")

# 3. Test Python imports
print("\n🐍 Testing Python imports...")
try:
    from app.config import settings
    print("   ✅ Settings loaded")
    
    obs_path = getattr(settings, "OBSIDIAN_VAULT_PATH", None)
    print(f"   📂 OBSIDIAN_VAULT_PATH from settings: {obs_path}")
    
    if obs_path:
        obs_path_obj = Path(obs_path)
        print(f"   📂 Path exists check: {obs_path_obj.exists()}")
    else:
        print("   ❌ OBSIDIAN_VAULT_PATH is None or not set!")
        
except Exception as e:
    print(f"   ❌ Error loading settings: {e}")
    import traceback
    traceback.print_exc()

# 4. Test connector
print("\n🔗 Testing Obsidian Connector...")
try:
    from app.integrations.obsidian import build_obsidian_connector
    
    # Force clear cache
    import app.integrations.obsidian as obs_module
    obs_module.obsidian_connector = None
    
    connector = build_obsidian_connector()
    if connector:
        print(f"   ✅ Connector created successfully!")
        print(f"   📂 Vault: {connector.vault_path}")
        print(f"   📁 Root folder: {connector.root_folder}")
    else:
        print("   ❌ Connector returned None")
        print("   📝 Possible causes:")
        print("      - Vault path doesn't exist")
        print("      - Path in .env doesn't match actual location")
        print("      - Permission issues accessing the folder")
except Exception as e:
    print(f"   ❌ Error: {e}")
    import traceback
    traceback.print_exc()

# 5. Test Redis
print("\n🔌 Testing Redis...")
try:
    from app.config import settings
    print(f"   📡 REDIS_URL: {settings.REDIS_URL[:50]}...")
    
    import redis
    client = redis.from_url(settings.REDIS_URL, decode_responses=True, socket_connect_timeout=5)
    client.ping()
    print("   ✅ Redis connected!")
    
    # Test write
    client.set('diagnose:test', 'ok', ex=60)
    val = client.get('diagnose:test')
    print(f"   ✅ Read/Write test: {val}")
    
except Exception as e:
    print(f"   ❌ Redis error: {e}")

print("\n" + "=" * 70)
print("✅ Diagnose complete")
print("=" * 70)
