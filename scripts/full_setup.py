#!/usr/bin/env python3
"""
Full setup script for Graxia OS - ทำทุกอย่างให้พร้อมใช้งาน
"""
import sys
import os
import asyncio
from pathlib import Path

sys.path.insert(0, 'backend')
os.chdir('c:/Users/menum/graxia os')

print("=" * 70)
print("🚀 GRAXIA OS - FULL SETUP & VERIFY")
print("=" * 70)

# 1. Create Obsidian Vault Structure
print("\n📁 [1/5] Setting up Obsidian Vault...")
vault_path = Path("C:/Users/menum/OneDrive/Documents/Gracia")
second_brain = vault_path / "Second Brain"

folders = [
    second_brain / "00-Inbox",
    second_brain / "01-Projects",
    second_brain / "02-Areas",
    second_brain / "03-Resources",
    second_brain / "04-Archive",
    second_brain / "90-System",
]

created = 0
for folder in folders:
    try:
        folder.mkdir(parents=True, exist_ok=True)
        created += 1
    except Exception as e:
        print(f"   ⚠️  {folder.name}: {e}")

print(f"   ✅ Created {created} folders")

# Create test note
readme = second_brain / "README.md"
readme.write_text("# Graxia OS Second Brain\n\nConnected to Graxia OS Agent System.", encoding='utf-8')
print(f"   ✅ Created README.md")

# 2. Verify Redis
print("\n🔌 [2/5] Verifying Redis...")
try:
    from app.config import settings
    import redis
    
    r = redis.from_url(settings.REDIS_URL, decode_responses=True, socket_connect_timeout=10)
    r.ping()
    print("   ✅ Redis Labs connected")
    
    r.set('graxia:status', 'ready', ex=300)
    print("   ✅ Redis write test passed")
    redis_ok = True
except Exception as e:
    print(f"   ❌ Redis error: {e}")
    redis_ok = False

# 3. Test Obsidian Connector
print("\n🔗 [3/5] Testing Obsidian Connector...")
try:
    # Force reload
    import importlib
    import app.integrations.obsidian as obs_module
    importlib.reload(obs_module)
    
    from app.integrations.obsidian import build_obsidian_connector
    
    connector = build_obsidian_connector()
    if connector:
        print(f"   ✅ Connector created")
        print(f"   📂 Vault: {connector.vault_path}")
        print(f"   📁 Folder: {connector.root_folder}")
        
        # Test write
        async def test_write():
            return await connector.write_note(
                filename="system_ready",
                content="# Graxia OS Ready\n\nSystem initialized successfully!",
                folder="90-System",
                frontmatter={"type": "system", "status": "ready"}
            )
        
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        result = loop.run_until_complete(test_write())
        print(f"   ✅ Test note written: {result}")
        obs_ok = True
    else:
        print("   ❌ Connector is None")
        obs_ok = False
except Exception as e:
    print(f"   ❌ Error: {e}")
    import traceback
    traceback.print_exc()
    obs_ok = False

# 4. Test Agent Identity
print("\n🤖 [4/5] Testing Agent Identity...")
try:
    from app.core.agent_identity import identity_manager, AgentType, PlatformType
    
    async def test_identity():
        await identity_manager.connect()
        
        # Create or get agent
        agents = await identity_manager.list_agents()
        if not agents:
            agent = await identity_manager.create_agent(
                name="Graxia System",
                agent_type=AgentType.SOCIAL,
                bio="Main system agent"
            )
            print(f"   ✅ Created agent: {agent.agent_name}")
        else:
            print(f"   ✅ Found {len(agents)} agents")
        
        return True
    
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    id_ok = loop.run_until_complete(test_identity())
    
except Exception as e:
    print(f"   ❌ Error: {e}")
    id_ok = False

# 5. Test Message Bus
print("\n📡 [5/5] Testing Message Bus...")
try:
    from app.core.enhanced_message_bus import message_bus
    
    async def test_bus():
        await message_bus.connect()
        print("   ✅ Message bus connected")
        
        await message_bus.publish("graxia.test", {"status": "ready"}, "system")
        print("   ✅ Test message published")
        return True
    
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    bus_ok = loop.run_until_complete(test_bus())
    
except Exception as e:
    print(f"   ❌ Error: {e}")
    bus_ok = False

# Summary
print("\n" + "=" * 70)
print("📊 SETUP SUMMARY")
print("=" * 70)

results = {
    "Obsidian Vault": obs_ok,
    "Redis Connection": redis_ok,
    "Agent Identity": id_ok,
    "Message Bus": bus_ok,
}

for name, ok in results.items():
    status = "✅ READY" if ok else "❌ FAILED"
    print(f"   {status}: {name}")

passed = sum(results.values())
total = len(results)

print(f"\n   {passed}/{total} systems ready")

if passed == total:
    print("\n🎉 GRAXIA OS IS FULLY OPERATIONAL!")
    print("   You can now run the backend and frontend.")
else:
    print(f"\n⚠️  {total-passed} system(s) need attention")

print("=" * 70)
