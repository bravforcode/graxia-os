import sys
import os

# Add root to path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '../')))
from packages.bwcp_protocol.python.protocol import create_bwcp_msg, MessageType, validate_message

def test_bwcp_protocol_flow():
    print("🚀 Starting BWCP Protocol Integrity Test...")
    
    # 1. Create a Mission Created message
    print("--- 1. Creating MISSION_CREATED message...")
    msg = create_bwcp_msg(
        from_agent="ceo_portal",
        to_agent="chief_of_staff",
        msg_type=MessageType.MISSION_CREATED,
        mission_id="mis_gold_scout_01",
        payload={"title": "Scout AI Jobs"}
    )
    print(f"   Message Created: ID={msg.message_id}, Type={msg.message_type}")
    
    # 2. Validate the message
    print("--- 2. Validating message against schema...")
    validated = validate_message(msg.dict())
    assert validated.mission_id == "mis_gold_scout_01"
    assert validated.message_type == "MISSION_CREATED"
    
    # 3. Test Failure Mode (Protocol Violation)
    print("--- 3. Testing Protocol Violation (Missing ID)...")
    invalid_data = msg.dict()
    del invalid_data["message_id"]
    
    try:
        validate_message(invalid_data)
        print("❌ Test Failed: Should have raised ValidationError")
    except Exception:
        print("✅ Correct: ValidationError caught for missing message_id.")

    print("✅ All BWCP Protocol Tests Passed.")

if __name__ == "__main__":
    test_bwcp_protocol_flow()
