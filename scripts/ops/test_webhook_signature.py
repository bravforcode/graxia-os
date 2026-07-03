#!/usr/bin/env python3
"""
Test script for webhook HMAC signature verification.

This script tests the webhook endpoint with various signature scenarios:
1. Valid signature
2. Invalid signature
3. Missing signature
4. Expired timestamp
5. Bearer token fallback

Usage:
    python scripts/test_webhook_signature.py [--url URL] [--secret SECRET]

Examples:
    # Test local development server
    python scripts/test_webhook_signature.py

    # Test staging server
    python scripts/test_webhook_signature.py --url https://staging.graxia.com

    # Test with custom secret
    python scripts/test_webhook_signature.py --secret your-webhook-secret
"""
import argparse
import hashlib
import hmac
import json
import sys
import time
from typing import Dict, Any

try:
    import requests
except ImportError:
    print("❌ Error: requests library not installed")
    print("Install with: pip install requests")
    sys.exit(1)


def generate_signature(body: bytes, timestamp: int, secret: str) -> str:
    """Generate HMAC-SHA256 signature for webhook request."""
    payload = f"{timestamp}.".encode() + body
    signature = hmac.new(secret.encode(), payload, hashlib.sha256).hexdigest()
    return f"sha256={signature}"


def test_valid_signature(base_url: str, secret: str) -> Dict[str, Any]:
    """Test webhook with valid HMAC signature."""
    print("\n🔍 Test 1: Valid HMAC signature")
    
    body = json.dumps({"alert": "test", "severity": "high"}).encode()
    timestamp = int(time.time())
    signature = generate_signature(body, timestamp, secret)
    
    try:
        response = requests.post(
            f"{base_url}/api/v1/integrations/alerts/telegram",
            data=body,
            headers={
                "X-Alertmanager-Signature": signature,
                "X-Graxia-Timestamp": str(timestamp),
                "Content-Type": "application/json",
            },
            timeout=10,
        )
        
        if response.status_code == 200:
            print("✅ PASS: Valid signature accepted")
            return {"test": "valid_signature", "status": "PASS", "code": 200}
        else:
            print(f"❌ FAIL: Expected 200, got {response.status_code}")
            print(f"   Response: {response.text}")
            return {"test": "valid_signature", "status": "FAIL", "code": response.status_code}
    
    except requests.exceptions.RequestException as e:
        print(f"❌ ERROR: {e}")
        return {"test": "valid_signature", "status": "ERROR", "error": str(e)}


def test_invalid_signature(base_url: str) -> Dict[str, Any]:
    """Test webhook with invalid HMAC signature."""
    print("\n🔍 Test 2: Invalid HMAC signature")
    
    body = json.dumps({"alert": "test"}).encode()
    timestamp = int(time.time())
    invalid_signature = "sha256=invalid_signature_here"
    
    try:
        response = requests.post(
            f"{base_url}/api/v1/integrations/alerts/telegram",
            data=body,
            headers={
                "X-Alertmanager-Signature": invalid_signature,
                "X-Graxia-Timestamp": str(timestamp),
                "Content-Type": "application/json",
            },
            timeout=10,
        )
        
        if response.status_code == 401:
            print("✅ PASS: Invalid signature rejected")
            return {"test": "invalid_signature", "status": "PASS", "code": 401}
        else:
            print(f"❌ FAIL: Expected 401, got {response.status_code}")
            print(f"   Response: {response.text}")
            return {"test": "invalid_signature", "status": "FAIL", "code": response.status_code}
    
    except requests.exceptions.RequestException as e:
        print(f"❌ ERROR: {e}")
        return {"test": "invalid_signature", "status": "ERROR", "error": str(e)}


def test_missing_signature(base_url: str) -> Dict[str, Any]:
    """Test webhook without HMAC signature."""
    print("\n🔍 Test 3: Missing HMAC signature")
    
    body = json.dumps({"alert": "test"}).encode()
    
    try:
        response = requests.post(
            f"{base_url}/api/v1/integrations/alerts/telegram",
            data=body,
            headers={"Content-Type": "application/json"},
            timeout=10,
        )
        
        if response.status_code == 401:
            print("✅ PASS: Missing signature rejected")
            return {"test": "missing_signature", "status": "PASS", "code": 401}
        else:
            print(f"❌ FAIL: Expected 401, got {response.status_code}")
            print(f"   Response: {response.text}")
            return {"test": "missing_signature", "status": "FAIL", "code": response.status_code}
    
    except requests.exceptions.RequestException as e:
        print(f"❌ ERROR: {e}")
        return {"test": "missing_signature", "status": "ERROR", "error": str(e)}


def test_expired_timestamp(base_url: str, secret: str) -> Dict[str, Any]:
    """Test webhook with expired timestamp (replay attack prevention)."""
    print("\n🔍 Test 4: Expired timestamp (replay attack)")
    
    body = json.dumps({"alert": "test"}).encode()
    # Timestamp from 10 minutes ago (beyond 5-minute window)
    expired_timestamp = int(time.time()) - 600
    signature = generate_signature(body, expired_timestamp, secret)
    
    try:
        response = requests.post(
            f"{base_url}/api/v1/integrations/alerts/telegram",
            data=body,
            headers={
                "X-Alertmanager-Signature": signature,
                "X-Graxia-Timestamp": str(expired_timestamp),
                "Content-Type": "application/json",
            },
            timeout=10,
        )
        
        if response.status_code == 401:
            print("✅ PASS: Expired timestamp rejected")
            return {"test": "expired_timestamp", "status": "PASS", "code": 401}
        else:
            print(f"❌ FAIL: Expected 401, got {response.status_code}")
            print(f"   Response: {response.text}")
            return {"test": "expired_timestamp", "status": "FAIL", "code": response.status_code}
    
    except requests.exceptions.RequestException as e:
        print(f"❌ ERROR: {e}")
        return {"test": "expired_timestamp", "status": "ERROR", "error": str(e)}


def test_missing_timestamp(base_url: str, secret: str) -> Dict[str, Any]:
    """Test webhook without timestamp header."""
    print("\n🔍 Test 5: Missing timestamp header")
    
    body = json.dumps({"alert": "test"}).encode()
    timestamp = int(time.time())
    signature = generate_signature(body, timestamp, secret)
    
    try:
        response = requests.post(
            f"{base_url}/api/v1/integrations/alerts/telegram",
            data=body,
            headers={
                "X-Alertmanager-Signature": signature,
                # Missing X-Graxia-Timestamp
                "Content-Type": "application/json",
            },
            timeout=10,
        )
        
        if response.status_code == 401:
            print("✅ PASS: Missing timestamp rejected")
            return {"test": "missing_timestamp", "status": "PASS", "code": 401}
        else:
            print(f"❌ FAIL: Expected 401, got {response.status_code}")
            print(f"   Response: {response.text}")
            return {"test": "missing_timestamp", "status": "FAIL", "code": response.status_code}
    
    except requests.exceptions.RequestException as e:
        print(f"❌ ERROR: {e}")
        return {"test": "missing_timestamp", "status": "ERROR", "error": str(e)}


def test_bearer_token_fallback(base_url: str, bearer_token: str) -> Dict[str, Any]:
    """Test webhook with bearer token (deprecated fallback)."""
    print("\n🔍 Test 6: Bearer token fallback (deprecated)")
    
    body = json.dumps({"alert": "test"}).encode()
    
    try:
        response = requests.post(
            f"{base_url}/api/v1/integrations/alerts/telegram",
            data=body,
            headers={
                "Authorization": f"Bearer {bearer_token}",
                "Content-Type": "application/json",
            },
            timeout=10,
        )
        
        if response.status_code == 200:
            print("⚠️  WARN: Bearer token still works (should migrate to HMAC)")
            return {"test": "bearer_token_fallback", "status": "WARN", "code": 200}
        elif response.status_code == 401:
            print("✅ PASS: Bearer token rejected (HMAC required)")
            return {"test": "bearer_token_fallback", "status": "PASS", "code": 401}
        else:
            print(f"❓ UNKNOWN: Got {response.status_code}")
            print(f"   Response: {response.text}")
            return {"test": "bearer_token_fallback", "status": "UNKNOWN", "code": response.status_code}
    
    except requests.exceptions.RequestException as e:
        print(f"❌ ERROR: {e}")
        return {"test": "bearer_token_fallback", "status": "ERROR", "error": str(e)}


def main():
    parser = argparse.ArgumentParser(
        description="Test webhook HMAC signature verification"
    )
    parser.add_argument(
        "--url",
        default="http://localhost:8000",
        help="Base URL of the API (default: http://localhost:8000)",
    )
    parser.add_argument(
        "--secret",
        default="test-webhook-secret-min-32-chars-long",
        help="Webhook HMAC secret (default: test secret)",
    )
    parser.add_argument(
        "--bearer-token",
        default="",
        help="Bearer token for fallback test (optional)",
    )
    
    args = parser.parse_args()
    
    print("=" * 70)
    print("🔐 Webhook HMAC Signature Verification Test Suite")
    print("=" * 70)
    print(f"Target URL: {args.url}")
    print(f"Secret: {'*' * len(args.secret)} ({len(args.secret)} chars)")
    
    results = []
    
    # Run tests
    results.append(test_valid_signature(args.url, args.secret))
    results.append(test_invalid_signature(args.url))
    results.append(test_missing_signature(args.url))
    results.append(test_expired_timestamp(args.url, args.secret))
    results.append(test_missing_timestamp(args.url, args.secret))
    
    if args.bearer_token:
        results.append(test_bearer_token_fallback(args.url, args.bearer_token))
    
    # Summary
    print("\n" + "=" * 70)
    print("📊 Test Summary")
    print("=" * 70)
    
    passed = sum(1 for r in results if r["status"] == "PASS")
    failed = sum(1 for r in results if r["status"] == "FAIL")
    errors = sum(1 for r in results if r["status"] == "ERROR")
    warnings = sum(1 for r in results if r["status"] == "WARN")
    total = len(results)
    
    print(f"Total tests: {total}")
    print(f"✅ Passed: {passed}")
    print(f"❌ Failed: {failed}")
    print(f"⚠️  Warnings: {warnings}")
    print(f"💥 Errors: {errors}")
    
    if failed > 0 or errors > 0:
        print("\n❌ OVERALL: FAILED")
        sys.exit(1)
    elif warnings > 0:
        print("\n⚠️  OVERALL: PASSED WITH WARNINGS")
        sys.exit(0)
    else:
        print("\n✅ OVERALL: ALL TESTS PASSED")
        sys.exit(0)


if __name__ == "__main__":
    main()
