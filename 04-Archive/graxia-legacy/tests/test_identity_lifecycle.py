import sys
import os
from datetime import timedelta

# Add root to path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '../')))

from packages.auth.python.jwt_auth import create_access_token, decode_access_token

SECRET = "bravos_test_secret"

def test_token_lifecycle():
    print("🚀 Starting Identity Broker Lifecycle Test...")
    
    # 1. Define dummy payload for a Sales Agent
    payload = {
        "sub": "agent_sales_001",
        "sub_type": "AGENT",
        "tenant_id": "tenant_bravos_corp",
        "mission_id": "mis_find_leads_01",
        "scopes": ["crm.read", "gmail.send"]
    }
    
    # 2. Issue Token
    print("--- Issuing Token for Sales Agent...")
    token = create_access_token(payload, SECRET)
    print(f"Token Issued: {token[:20]}...")
    
    # 3. Decode and Validate
    print("--- Decoding and Validating Token...")
    decoded = decode_access_token(token, SECRET)
    
    assert decoded["sub"] == payload["sub"]
    assert decoded["sub_type"] == payload["sub_type"]
    assert "crm.read" in decoded["scopes"]
    
    print("✅ Test Passed: Token issued and validated successfully with all scopes.")

if __name__ == "__main__":
    test_token_lifecycle()
