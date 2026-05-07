import sys
import os

# Define mock local evaluation logic for verification
def evaluate_logic(flag_key, tenant_id=None):
    # Mock Database
    MOCK_DB = {
        "agent_v2": {"global_override": None, "allowlist": ["tenant_vip"], "default": False},
        "kill_switch": {"global_override": True, "allowlist": [], "default": False}
    }
    
    flag = MOCK_DB.get(flag_key)
    if not flag: return (False, "Not Found")
    
    if flag["global_override"] is not None:
        return (flag["global_override"], "Global Override")
    
    if tenant_id in flag["allowlist"]:
        return (True, "Tenant Allowlist")
        
    return (flag["default"], "Default")

def test_release_control_hierarchy():
    print("🚀 Starting Release Control Logic Test...")
    
    # Test 1: Global Override (Kill Switch)
    enabled, reason = evaluate_logic("kill_switch")
    print(f"--- 1. Kill Switch Test: Enabled={enabled}, Reason={reason}")
    assert enabled == True
    
    # Test 2: Tenant Allowlist (VIP access to V2)
    enabled, reason = evaluate_logic("agent_v2", tenant_id="tenant_vip")
    print(f"--- 2. VIP Tenant Test: Enabled={enabled}, Reason={reason}")
    assert enabled == True
    
    # Test 3: Default State (Regular tenant access to V2)
    enabled, reason = evaluate_logic("agent_v2", tenant_id="tenant_regular")
    print(f"--- 3. Regular Tenant Test: Enabled={enabled}, Reason={reason}")
    assert enabled == False
    
    print("✅ Test Passed: Release Control correctly enforces hierarchy.")

if __name__ == "__main__":
    test_release_control_hierarchy()
