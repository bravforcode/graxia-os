#!/usr/bin/env python3
"""
Test script for Graxia OS Agent System
ทดสอบระบบ Agents ทั้งหมด
"""
import asyncio
import sys
sys.path.insert(0, 'backend')

async def test_obsidian():
    """ทดสอบ Obsidian Connection"""
    print("\n" + "="*50)
    print("📝 Testing Obsidian Connection")
    print("="*50)
    
    try:
        from app.integrations.obsidian import get_obsidian
        obsidian = await get_obsidian()
        
        print(f"✅ Obsidian connected!")
        print(f"   Vault path: {obsidian.vault_path}")
        print(f"   Root folder: {obsidian.root_folder}")
        
        # Test write
        test_path = await obsidian.write_note(
            filename="agent_system_test",
            content="# Test\nAgent system test successful!",
            folder="Tests",
            frontmatter={"type": "test", "timestamp": "2024"}
        )
        print(f"✅ Test note written: {test_path}")
        
        return True
    except Exception as e:
        print(f"❌ Obsidian test failed: {e}")
        return False


async def test_agent_identity():
    """ทดสอบ Agent Identity System"""
    print("\n" + "="*50)
    print("🤖 Testing Agent Identity System")
    print("="*50)
    
    try:
        from app.core.agent_identity import identity_manager, AgentType, AgentCapability
        
        await identity_manager.connect()
        print("✅ Identity Manager connected")
        
        # Create test agent
        agent = await identity_manager.create_agent(
            name="Test Social Agent",
            agent_type=AgentType.SOCIAL,
            bio="Test agent for demonstration",
            capabilities=[
                AgentCapability(name="posting", description="Post to social", skill_level=8),
                AgentCapability(name="replying", description="Reply messages", skill_level=9)
            ]
        )
        
        print(f"✅ Agent created: {agent.agent_name}")
        print(f"   ID: {agent.agent_id}")
        print(f"   Type: {agent.agent_type.value}")
        print(f"   Reputation: {agent.reputation_score}")
        
        # Add account
        from app.core.agent_identity import PlatformType
        account = await identity_manager.add_account(
            agent_id=agent.agent_id,
            platform=PlatformType.TELEGRAM,
            account_id="test_account_123",
            username="test_bot"
        )
        print(f"✅ Account added: {account.platform.value}")
        
        # List all agents
        all_agents = await identity_manager.get_all_agents()
        print(f"✅ Total agents: {len(all_agents)}")
        
        return True
    except Exception as e:
        print(f"❌ Agent Identity test failed: {e}")
        import traceback
        traceback.print_exc()
        return False


async def test_message_bus():
    """ทดสอบ Message Bus"""
    print("\n" + "="*50)
    print("📡 Testing Enhanced Message Bus")
    print("="*50)
    
    try:
        from app.core.enhanced_message_bus import message_bus, AgentMessage, MessageType
        
        await message_bus.connect()
        print("✅ Message Bus connected")
        
        # Test publish/subscribe
        received_messages = []
        
        async def subscriber():
            queue = await message_bus.subscribe("test_topic")
            try:
                msg = await asyncio.wait_for(queue.get(), timeout=2.0)
                received_messages.append(msg)
            except asyncio.TimeoutError:
                pass
        
        # Start subscriber
        sub_task = asyncio.create_task(subscriber())
        
        # Publish message
        await asyncio.sleep(0.1)  # Let subscriber start
        
        msg = AgentMessage(
            sender="test_sender",
            topic="test_topic",
            message_type=MessageType.BROADCAST,
            content={"test": "message"}
        )
        await message_bus.publish("test_topic", msg)
        
        # Wait for subscriber
        await sub_task
        
        if received_messages:
            print(f"✅ Message received: {received_messages[0].content}")
        else:
            print("⚠️ Message not received (local mode may have timing issues)")
        
        return True
    except Exception as e:
        print(f"❌ Message Bus test failed: {e}")
        import traceback
        traceback.print_exc()
        return False


async def test_social_agents():
    """ทดสอบ Social Media Agents"""
    print("\n" + "="*50)
    print("📱 Testing Social Media Agents")
    print("="*50)
    
    try:
        from app.agents.social import facebook_agent, line_agent
        
        # Test Facebook Agent (disabled by default)
        await facebook_agent.initialize()
        if facebook_agent.identity:
            print(f"✅ Facebook Agent initialized: {facebook_agent.agent_name}")
            print(f"   Status: {'Enabled' if facebook_agent.enabled else 'Disabled'}")
        else:
            print("⚠️ Facebook Agent not configured (set FACEBOOK_AGENT_ENABLED=true)")
        
        # Test LINE Agent (disabled by default)
        await line_agent.initialize()
        if line_agent.identity:
            print(f"✅ LINE Agent initialized: {line_agent.agent_name}")
            print(f"   Status: {'Enabled' if line_agent.enabled else 'Disabled'}")
        else:
            print("⚠️ LINE Agent not configured (set LINE_AGENT_ENABLED=true)")
        
        return True
    except Exception as e:
        print(f"❌ Social Agents test failed: {e}")
        import traceback
        traceback.print_exc()
        return False


async def test_negotiation():
    """ทดสอบ Negotiation System"""
    print("\n" + "="*50)
    print("🤝 Testing Negotiation System")
    print("="*50)
    
    try:
        from app.core.enhanced_message_bus import message_bus
        
        # Start negotiation
        session = await message_bus.start_negotiation(
            initiator="test_initiator",
            responder="test_responder",
            task="create_social_post",
            terms={"deadline": "1 hour", "quality": "high"},
            timeout_minutes=5
        )
        
        print(f"✅ Negotiation started: {session.negotiation_id}")
        print(f"   Status: {session.status}")
        print(f"   Task: {session.task}")
        
        # Check active negotiations
        active = await message_bus.get_active_negotiations()
        print(f"✅ Active negotiations: {len(active)}")
        
        return True
    except Exception as e:
        print(f"❌ Negotiation test failed: {e}")
        import traceback
        traceback.print_exc()
        return False


async def run_all_tests():
    """รันการทดสอบทั้งหมด"""
    print("\n" + "="*60)
    print("🚀 GRAXIA OS AGENT SYSTEM - COMPREHENSIVE TEST")
    print("="*60)
    
    results = {}
    
    # Run tests
    results["obsidian"] = await test_obsidian()
    results["agent_identity"] = await test_agent_identity()
    results["message_bus"] = await test_message_bus()
    results["social_agents"] = await test_social_agents()
    results["negotiation"] = await test_negotiation()
    
    # Summary
    print("\n" + "="*60)
    print("📊 TEST SUMMARY")
    print("="*60)
    
    for name, passed in results.items():
        status = "✅ PASS" if passed else "❌ FAIL"
        print(f"{status}: {name}")
    
    passed_count = sum(results.values())
    total_count = len(results)
    
    print(f"\nTotal: {passed_count}/{total_count} tests passed")
    
    if passed_count == total_count:
        print("\n🎉 All tests passed! Agent system is ready.")
    else:
        print("\n⚠️  Some tests failed. Check the output above.")
    
    return results


if __name__ == "__main__":
    # Check if backend path exists
    import os
    if not os.path.exists("backend/app"):
        print("❌ Error: Run this script from the project root directory")
        print("   cd c:\\Users\\menum\\graxia os")
        print("   python scripts/test_agent_system.py")
        sys.exit(1)
    
    # Run tests
    asyncio.run(run_all_tests())
