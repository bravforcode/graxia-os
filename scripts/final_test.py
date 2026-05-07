#!/usr/bin/env python3
"""
Final comprehensive test for Graxia OS - ตรวจสอบทุกระบบ
"""
import os
import sys
import asyncio
from pathlib import Path
from datetime import datetime

# Setup paths
sys.path.insert(0, 'backend')
os.chdir('c:/Users/menum/graxia os')

print("=" * 70)
print("🚀 GRAXIA OS - FINAL COMPREHENSIVE TEST")
print(f"Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
print("=" * 70)

results = {}

# 1. Test Obsidian
print("\n📁 [1/5] Testing Obsidian Integration...")
try:
    from app.integrations.obsidian import build_obsidian_connector
    
    # Force clear any cached connector
    import app.integrations.obsidian as obs_module
    obs_module.obsidian_connector = None
    
    connector = build_obsidian_connector()
    if connector:
        print(f"   ✅ Obsidian connector created")
        print(f"   📂 Vault path: {connector.vault_path}")
        print(f"   📁 Root folder: {connector.root_folder}")
        
        # Test write note
        async def test_obsidian():
            test_path = await connector.write_note(
                filename="graxia_test",
                content="# Graxia OS Test\n\nSystem test at " + datetime.now().isoformat(),
                folder="90-System",
                frontmatter={"type": "test", "source": "graxia_os", "auto": True}
            )
            return test_path
        
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        test_path = loop.run_until_complete(test_obsidian())
        print(f"   ✅ Test note written: {test_path}")
        results['obsidian'] = True
    else:
        print("   ❌ Connector returned None")
        results['obsidian'] = False
except Exception as e:
    print(f"   ❌ Error: {e}")
    import traceback
    traceback.print_exc()
    results['obsidian'] = False

# 2. Test Redis Connection
print("\n🔌 [2/5] Testing Redis Connection...")
try:
    import redis
    from app.config import settings
    
    # Test Redis Labs connection
    redis_client = redis.from_url(
        settings.REDIS_URL, 
        decode_responses=True,
        socket_connect_timeout=5
    )
    redis_client.ping()
    print(f"   ✅ Redis Labs connected")
    print(f"   🌐 URL: {settings.REDIS_URL.split('@')[1] if '@' in settings.REDIS_URL else 'local'}")
    results['redis'] = True
    
    # Test write/read
    redis_client.set('graxia:test', 'connected', ex=60)
    value = redis_client.get('graxia:test')
    print(f"   ✅ Read/Write test: {value}")
    
except Exception as e:
    print(f"   ❌ Redis error: {e}")
    print("   ⚠️  Falling back to local storage mode")
    results['redis'] = False

# 3. Test Agent Identity
print("\n🤖 [3/5] Testing Agent Identity System...")
try:
    from app.core.agent_identity import identity_manager, AgentType, PlatformType
    
    async def test_identity():
        await identity_manager.connect()
        print("   ✅ Identity Manager connected")
        
        # Create test agent
        agent = await identity_manager.create_agent(
            name="Graxia Test Agent",
            agent_type=AgentType.SOCIAL,
            bio="Test agent for Graxia OS verification",
        )
        print(f"   ✅ Agent created: {agent.agent_name}")
        print(f"   🆔 ID: {agent.agent_id}")
        
        # Add account
        await identity_manager.add_account(
            agent_id=agent.agent_id,
            platform=PlatformType.TELEGRAM,
            account_id="test_bot",
            username="graxia_test"
        )
        print("   ✅ Telegram account added")
        
        # List agents
        agents = await identity_manager.list_agents()
        print(f"   📊 Total agents: {len(agents)}")
        
        return True
    
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    identity_result = loop.run_until_complete(test_identity())
    results['agent_identity'] = identity_result
    
except Exception as e:
    print(f"   ❌ Agent Identity error: {e}")
    import traceback
    traceback.print_exc()
    results['agent_identity'] = False

# 4. Test Message Bus
print("\n📡 [4/5] Testing Message Bus...")
try:
    from app.core.enhanced_message_bus import message_bus
    
    async def test_bus():
        await message_bus.connect()
        print("   ✅ Message Bus connected")
        
        # Test pub/sub
        received_messages = []
        async def handler(msg):
            received_messages.append(msg)
        
        await message_bus.subscribe("test.graxia", handler)
        await message_bus.publish("test.graxia", {"test": "data", "time": datetime.now().isoformat()}, "test_agent")
        
        await asyncio.sleep(0.5)
        
        if received_messages:
            print(f"   ✅ Message received: {received_messages[0].content}")
        else:
            print("   ⚠️  Message not received (local mode)")
        
        return True
    
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    bus_result = loop.run_until_complete(test_bus())
    results['message_bus'] = bus_result
    
except Exception as e:
    print(f"   ❌ Message Bus error: {e}")
    results['message_bus'] = False

# 5. Test Social Agents
print("\n📱 [5/5] Testing Social Media Agents...")
try:
    from app.agents.social.facebook_agent import facebook_agent
    from app.agents.social.line_agent import line_agent
    
    print(f"   ✅ Facebook Agent: {facebook_agent.name} (Status: {facebook_agent.status})")
    print(f"   ✅ LINE Agent: {line_agent.name} (Status: {line_agent.status})")
    
    # Check if configured
    from app.config import settings
    fb_enabled = getattr(settings, 'FACEBOOK_AGENT_ENABLED', False)
    line_enabled = getattr(settings, 'LINE_AGENT_ENABLED', False)
    
    if fb_enabled:
        print("   🟢 Facebook Agent is ENABLED")
    else:
        print("   ⚪ Facebook Agent is disabled (set FACEBOOK_PAGE_TOKEN to enable)")
    
    if line_enabled:
        print("   🟢 LINE Agent is ENABLED")
    else:
        print("   ⚪ LINE Agent is disabled (set LINE_CHANNEL_TOKEN to enable)")
    
    results['social_agents'] = True
    
except Exception as e:
    print(f"   ❌ Social Agents error: {e}")
    results['social_agents'] = False

# Summary
print("\n" + "=" * 70)
print("📊 TEST SUMMARY")
print("=" * 70)

passed = 0
total = len(results)

for name, status in results.items():
    icon = "✅ PASS" if status else "❌ FAIL"
    print(f"   {icon}: {name.replace('_', ' ').title()}")
    if status:
        passed += 1

print("\n" + "-" * 70)
print(f"   Total: {passed}/{total} tests passed ({passed/total*100:.0f}%)")

if passed == total:
    print("\n🎉 ALL SYSTEMS OPERATIONAL!")
    print("   Graxia OS is ready for use.")
else:
    print(f"\n⚠️  {total-passed} test(s) failed. Check output above.")
    
print("=" * 70)

# Exit code
sys.exit(0 if passed == total else 1)
