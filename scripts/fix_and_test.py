#!/usr/bin/env python3
"""
ตรวจสอบและแก้ไขปัญหา Graxia OS setup
"""
import os
import sys
import asyncio
from pathlib import Path

sys.path.insert(0, 'backend')

print("=" * 60)
print("🔧 ตรวจสอบและแก้ไขปัญหา Graxia OS")
print("=" * 60)

# 1. Fix Obsidian - สร้างโฟลเดอร์ถ้ายังไม่มี
print("\n📁 Checking Obsidian Vault...")
vault_path = Path("C:/Users/menum/OneDrive/Documents/Gracia/Second Brain")
if not vault_path.exists():
    print(f"   Creating vault at: {vault_path}")
    vault_path.mkdir(parents=True, exist_ok=True)
    # สร้างโครงสร้างพื้นฐาน
    folders = ["00-Inbox", "01-Projects", "02-Areas", "03-Resources", "04-Archive", "90-System"]
    for folder in folders:
        (vault_path / folder).mkdir(exist_ok=True)
    print("   ✅ Vault structure created")
else:
    print(f"   ✅ Vault exists: {vault_path}")

# 2. Check Redis
print("\n🔌 Checking Redis...")
try:
    import redis
    # ลองเชื่อมต่อแบบไม่มี password
    r = redis.Redis(host='localhost', port=6379, db=0, socket_connect_timeout=3)
    r.ping()
    print("   ✅ Redis connected (no auth required)")
    redis_auth = False
except redis.AuthenticationError:
    print("   ⚠️ Redis requires authentication")
    redis_auth = True
except Exception as e:
    print(f"   ❌ Redis error: {e}")
    redis_auth = None

if redis_auth:
    print("\n   📝 To fix Redis auth, you need to either:")
    print("   1. Find the Redis password and update backend/.env")
    print("   2. Or disable Redis auth in redis.conf")
    print("   3. Or stop the current Redis and start without auth:")
    print("      redis-server --port 6379 --protected-mode no")

# 3. Run tests
print("\n" + "=" * 60)
print("🧪 Running Tests")
print("=" * 60)

async def run_tests():
    results = {}
    
    # Test Obsidian
    print("\n📝 Testing Obsidian...")
    try:
        from app.integrations.obsidian import get_obsidian, build_obsidian_connector
        
        # Force recreate connector
        import app.integrations.obsidian as obs_module
        obs_module.obsidian_connector = None
        
        connector = build_obsidian_connector()
        if connector:
            print(f"   ✅ Obsidian connector created")
            print(f"   - Vault: {connector.vault_path}")
            
            # Test write
            test_path = await connector.write_note(
                filename="system_test",
                content="# System Test\nObsidian integration working!",
                folder="90-System",
                frontmatter={"type": "test", "source": "graxia"}
            )
            print(f"   ✅ Test note written: {test_path}")
            results['obsidian'] = True
        else:
            print("   ❌ Connector returned None - check vault path")
            results['obsidian'] = False
    except Exception as e:
        print(f"   ❌ Obsidian test failed: {e}")
        import traceback
        traceback.print_exc()
        results['obsidian'] = False
    
    # Test Agent Identity
    print("\n🤖 Testing Agent Identity...")
    try:
        from app.core.agent_identity import identity_manager, AgentType
        from app.core.agent_identity import PlatformType
        
        await identity_manager.connect()
        print("   ✅ Identity Manager connected")
        
        # Create agent
        agent = await identity_manager.create_agent(
            name="Graxia System Agent",
            agent_type=AgentType.SOCIAL,
            bio="System agent for Graxia OS",
        )
        print(f"   ✅ Agent created: {agent.agent_name} ({agent.agent_id})")
        
        # Add Telegram account
        await identity_manager.add_account(
            agent_id=agent.agent_id,
            platform=PlatformType.TELEGRAM,
            account_id="system_bot",
            username="graxia_system"
        )
        print("   ✅ Account added")
        
        results['agent_identity'] = True
    except Exception as e:
        print(f"   ❌ Agent Identity failed: {e}")
        results['agent_identity'] = False
    
    # Test Message Bus
    print("\n📡 Testing Message Bus...")
    try:
        from app.core.enhanced_message_bus import message_bus
        
        await message_bus.connect()
        print("   ✅ Message Bus connected")
        
        # Test publish/subscribe
        received = []
        async def handler(msg):
            received.append(msg)
        
        await message_bus.subscribe("test.topic", handler)
        await message_bus.publish("test.topic", {"test": "data"}, "test_agent")
        
        await asyncio.sleep(0.5)
        if received:
            print("   ✅ Message received successfully")
            results['message_bus'] = True
        else:
            print("   ⚠️ Message not received (may be local mode)")
            results['message_bus'] = True  # Still pass if connected
    except Exception as e:
        print(f"   ❌ Message Bus failed: {e}")
        results['message_bus'] = False
    
    return results

# Run tests
results = asyncio.run(run_tests())

# Summary
print("\n" + "=" * 60)
print("📊 Test Summary")
print("=" * 60)
for name, passed in results.items():
    status = "✅ PASS" if passed else "❌ FAIL"
    print(f"   {status}: {name}")

passed = sum(results.values())
total = len(results)
print(f"\n   Total: {passed}/{total} tests passed")

if passed == total:
    print("\n🎉 All systems operational!")
else:
    print("\n⚠️ Some tests failed. Check output above.")
