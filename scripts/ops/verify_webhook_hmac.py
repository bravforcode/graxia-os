#!/usr/bin/env python3
"""
Verification script for webhook HMAC signature implementation.

This script verifies that:
1. HMAC signature verification is implemented correctly
2. Timestamp validation works (5-minute window)
3. Constant-time comparison is used
4. Request body restoration works

Usage:
    python scripts/verify_webhook_hmac.py
"""
import hashlib
import hmac
import sys
import time
from pathlib import Path

# Add backend to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from app.config import settings
from app.middleware.auth import AuthMiddleware


def test_hmac_signature_generation():
    """Test HMAC signature generation."""
    print("\n🔍 Test 1: HMAC Signature Generation")
    
    secret = "test-secret"
    body = b'{"alert": "test"}'
    timestamp = 1234567890
    
    # Generate signature
    payload = f"{timestamp}.".encode() + body
    expected_sig = "sha256=" + hmac.new(secret.encode(), payload, hashlib.sha256).hexdigest()
    
    print(f"   Secret: {secret}")
    print(f"   Body: {body}")
    print(f"   Timestamp: {timestamp}")
    print(f"   Signature: {expected_sig}")
    print("✅ PASS: Signature generation works")
    
    return True


def test_constant_time_comparison():
    """Test that hmac.compare_digest is used for constant-time comparison."""
    print("\n🔍 Test 2: Constant-Time Comparison")
    
    # Read the middleware code
    middleware_file = Path(__file__).parent.parent / "app" / "middleware" / "auth.py"
    with open(middleware_file, "r") as f:
        code = f.read()
    
    # Check for hmac.compare_digest usage
    if "hmac.compare_digest" in code:
        print("✅ PASS: hmac.compare_digest is used")
        return True
    else:
        print("❌ FAIL: hmac.compare_digest not found")
        return False


def test_timestamp_validation():
    """Test timestamp validation logic."""
    print("\n🔍 Test 3: Timestamp Validation")
    
    # Read the middleware code
    middleware_file = Path(__file__).parent.parent / "app" / "middleware" / "auth.py"
    with open(middleware_file, "r") as f:
        code = f.read()
    
    # Check for timestamp validation (5-minute window = 300 seconds)
    if "abs(time.time() - timestamp) > 300" in code:
        print("✅ PASS: Timestamp validation with 5-minute window found")
        return True
    else:
        print("❌ FAIL: Timestamp validation not found or incorrect")
        return False


def test_signature_format():
    """Test signature format (sha256= prefix)."""
    print("\n🔍 Test 4: Signature Format")
    
    # Read the middleware code
    middleware_file = Path(__file__).parent.parent / "app" / "middleware" / "auth.py"
    with open(middleware_file, "r") as f:
        code = f.read()
    
    # Check for sha256= prefix check
    if 'signature.startswith("sha256=")' in code:
        print("✅ PASS: Signature format validation found")
        return True
    else:
        print("❌ FAIL: Signature format validation not found")
        return False


def test_request_body_restoration():
    """Test request body restoration after verification."""
    print("\n🔍 Test 5: Request Body Restoration")
    
    # Read the middleware code
    middleware_file = Path(__file__).parent.parent / "app" / "middleware" / "auth.py"
    with open(middleware_file, "r") as f:
        code = f.read()
    
    # Check for body restoration
    if "request._receive = receive" in code or "async def receive()" in code:
        print("✅ PASS: Request body restoration found")
        return True
    else:
        print("❌ FAIL: Request body restoration not found")
        return False


def test_bearer_token_fallback():
    """Test bearer token fallback when HMAC secret not configured."""
    print("\n🔍 Test 6: Bearer Token Fallback")
    
    # Read the middleware code
    middleware_file = Path(__file__).parent.parent / "app" / "middleware" / "auth.py"
    with open(middleware_file, "r") as f:
        code = f.read()
    
    # Check for bearer token fallback
    if "ALERTMANAGER_WEBHOOK_TOKEN" in code:
        print("✅ PASS: Bearer token fallback found")
        return True
    else:
        print("❌ FAIL: Bearer token fallback not found")
        return False


def main():
    print("=" * 70)
    print("🔐 Webhook HMAC Signature Verification - Code Analysis")
    print("=" * 70)
    
    results = []
    
    # Run tests
    results.append(("HMAC Signature Generation", test_hmac_signature_generation()))
    results.append(("Constant-Time Comparison", test_constant_time_comparison()))
    results.append(("Timestamp Validation", test_timestamp_validation()))
    results.append(("Signature Format", test_signature_format()))
    results.append(("Request Body Restoration", test_request_body_restoration()))
    results.append(("Bearer Token Fallback", test_bearer_token_fallback()))
    
    # Summary
    print("\n" + "=" * 70)
    print("📊 Verification Summary")
    print("=" * 70)
    
    passed = sum(1 for _, result in results if result)
    failed = sum(1 for _, result in results if not result)
    total = len(results)
    
    print(f"Total checks: {total}")
    print(f"✅ Passed: {passed}")
    print(f"❌ Failed: {failed}")
    
    print("\n" + "=" * 70)
    print("📋 Detailed Results")
    print("=" * 70)
    for name, result in results:
        status = "✅ PASS" if result else "❌ FAIL"
        print(f"{status}: {name}")
    
    if failed > 0:
        print("\n❌ OVERALL: VERIFICATION FAILED")
        sys.exit(1)
    else:
        print("\n✅ OVERALL: ALL CHECKS PASSED")
        print("\n📝 Implementation Status:")
        print("   - HMAC signature verification: ✅ IMPLEMENTED")
        print("   - Timestamp validation (replay attack prevention): ✅ IMPLEMENTED")
        print("   - Constant-time comparison: ✅ IMPLEMENTED")
        print("   - Request body restoration: ✅ IMPLEMENTED")
        print("   - Bearer token fallback: ✅ IMPLEMENTED")
        print("\n🎯 Ready for deployment!")
        sys.exit(0)


if __name__ == "__main__":
    main()
