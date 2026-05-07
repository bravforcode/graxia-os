#!/usr/bin/env python3
"""
Auto-setup and run test for Graxia OS
"""
import subprocess
import sys
import os
from pathlib import Path

os.chdir("c:/Users/menum/graxia os")

print("=" * 70)
print("🚀 GRAXIA OS - AUTO SETUP & TEST")
print("=" * 70)

# 1. Create vault structure
print("\n📁 [1/3] Creating vault structure...")
vault = Path("C:/Users/menum/OneDrive/Documents/Gracia/Second Brain")
folders = ["00-Inbox", "01-Projects", "02-Areas", "03-Resources", "04-Archive", "90-System"]
created = 0
for folder in folders:
    try:
        (vault / folder).mkdir(parents=True, exist_ok=True)
        created += 1
    except Exception as e:
        print(f"   ⚠️  {folder}: {e}")
print(f"   ✅ Created {created} folders")

# 2. Clear cache
print("\n🧹 [2/3] Clearing Python cache...")
cache_dirs = [
    "backend/app/__pycache__",
    "backend/app/core/__pycache__",
    "backend/app/integrations/__pycache__",
]
for d in cache_dirs:
    try:
        import shutil
        shutil.rmtree(d, ignore_errors=True)
    except:
        pass
print("   ✅ Cache cleared")

# 3. Run test
print("\n🧪 [3/3] Running test...")
print("=" * 70)
result = subprocess.run([sys.executable, "scripts/test_agent_system.py"], capture_output=False)
print("=" * 70)

if result.returncode == 0:
    print("\n🎉 ALL TESTS PASSED!")
else:
    print(f"\n⚠️  Test exited with code {result.returncode}")
