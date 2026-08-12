#!/usr/bin/env python3
"""
Verification script for TASK 2.1: Required Secrets Validation.

This script tests that the secrets validation is working correctly
by attempting to create Settings instances with various configurations.

Usage:
    python scripts/verify_secrets_validation.py
"""

import sys
from pathlib import Path

# Add backend to path
backend_dir = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(backend_dir))

from app.config import Settings


def print_header(text: str) -> None:
    """Print a formatted header."""
    print(f"\n{'=' * 60}")
    print(f"  {text}")
    print('=' * 60)


def print_test(number: int, description: str) -> None:
    """Print test description."""
    print(f"\n[Test {number}] {description}")


def print_success(message: str) -> None:
    """Print success message."""
    print(f"  ✓ {message}")


def print_failure(message: str) -> None:
    """Print failure message."""
    print(f"  ✗ {message}")


def test_missing_secrets_rejected_development() -> bool:
    """Test that missing secrets are rejected in development mode."""
    print_test(1, "Missing secrets rejected in development")
    
    try:
        Settings(
            APP_ENV="development",
            SECRET_KEY=None,
            ENCRYPTION_KEY=None,
            POSTGRES_PASSWORD=None,
        )
        print_failure("Should have raised RuntimeError for missing secrets")
        return False
    except RuntimeError as e:
        error_msg = str(e)
        if "Required secrets not configured" in error_msg:
            print_success("Missing secrets correctly rejected")
            print_success(f"Error message includes: 'Required secrets not configured'")
            if "openssl rand" in error_msg:
                print_success("Error message includes generation commands")
            return True
        else:
            print_failure(f"Unexpected error message: {error_msg}")
            return False


def test_missing_secrets_rejected_production() -> bool:
    """Test that missing secrets are rejected in production mode."""
    print_test(2, "Missing secrets rejected in production")
    
    try:
        Settings(
            APP_ENV="production",
            SECRET_KEY=None,
            ENCRYPTION_KEY=None,
            POSTGRES_PASSWORD=None,
        )
        print_failure("Should have raised RuntimeError for missing secrets")
        return False
    except RuntimeError as e:
        error_msg = str(e)
        if "Required secrets not configured" in error_msg:
            print_success("Missing secrets correctly rejected in production")
            return True
        else:
            print_failure(f"Unexpected error message: {error_msg}")
            return False


def test_weak_secrets_rejected() -> bool:
    """Test that weak secrets are rejected."""
    print_test(3, "Weak secrets rejected")
    
    # Test short SECRET_KEY
    try:
        Settings(
            APP_ENV="development",
            SECRET_KEY="short",
            ENCRYPTION_KEY="a" * 32,
            POSTGRES_PASSWORD="a" * 16,
        )
        print_failure("Should have rejected short SECRET_KEY")
        return False
    except RuntimeError as e:
        if "SECRET_KEY must be at least 32 characters" in str(e):
            print_success("Short SECRET_KEY correctly rejected")
        else:
            print_failure(f"Unexpected error for short SECRET_KEY: {e}")
            return False
    
    # Test short ENCRYPTION_KEY
    try:
        Settings(
            APP_ENV="development",
            SECRET_KEY="a" * 32,
            ENCRYPTION_KEY="short",
            POSTGRES_PASSWORD="a" * 16,
        )
        print_failure("Should have rejected short ENCRYPTION_KEY")
        return False
    except RuntimeError as e:
        if "ENCRYPTION_KEY must be at least 32 characters" in str(e):
            print_success("Short ENCRYPTION_KEY correctly rejected")
        else:
            print_failure(f"Unexpected error for short ENCRYPTION_KEY: {e}")
            return False
    
    # Test short POSTGRES_PASSWORD
    try:
        Settings(
            APP_ENV="development",
            SECRET_KEY="a" * 32,
            ENCRYPTION_KEY="a" * 32,
            POSTGRES_PASSWORD="short",
        )
        print_failure("Should have rejected short POSTGRES_PASSWORD")
        return False
    except RuntimeError as e:
        if "POSTGRES_PASSWORD must be at least 16 characters" in str(e):
            print_success("Short POSTGRES_PASSWORD correctly rejected")
        else:
            print_failure(f"Unexpected error for short POSTGRES_PASSWORD: {e}")
            return False
    
    # Test low entropy SECRET_KEY
    try:
        Settings(
            APP_ENV="development",
            SECRET_KEY="a" * 64,  # Long but low entropy
            ENCRYPTION_KEY="b" * 32,
            POSTGRES_PASSWORD="c" * 16,
        )
        print_failure("Should have rejected low entropy SECRET_KEY")
        return False
    except RuntimeError as e:
        if "insufficient entropy" in str(e):
            print_success("Low entropy SECRET_KEY correctly rejected")
        else:
            print_failure(f"Unexpected error for low entropy: {e}")
            return False
    
    # Test placeholder values
    placeholders = ["changeme", "development-secret", "your_secret", "placeholder"]
    for placeholder in placeholders:
        try:
            Settings(
                APP_ENV="development",
                SECRET_KEY=placeholder,
                ENCRYPTION_KEY=placeholder,
                POSTGRES_PASSWORD=placeholder,
            )
            print_failure(f"Should have rejected placeholder: {placeholder}")
            return False
        except RuntimeError as e:
            if "Required secrets not configured" in str(e):
                pass  # Expected
            else:
                print_failure(f"Unexpected error for placeholder '{placeholder}': {e}")
                return False
    
    print_success(f"All placeholder values correctly rejected: {', '.join(placeholders)}")
    
    return True


def test_strong_secrets_accepted() -> bool:
    """Test that strong secrets are accepted."""
    print_test(4, "Strong secrets accepted")
    
    try:
        settings = Settings(
            APP_ENV="development",
            SECRET_KEY="a1b2c3d4e5f6g7h8i9j0k1l2m3n4o5p6q7r8s9t0u1v2w3x4y5z6",  # 56 chars, mixed
            ENCRYPTION_KEY="9f8e7d6c5b4a3928170615243f2e1d0c",  # 32 chars hex-like
            POSTGRES_PASSWORD="StrongP@ssw0rd123!",  # 18 chars, mixed
        )
        print_success("Strong secrets accepted")
        print_success(f"SECRET_KEY length: {len(settings.SECRET_KEY)}")
        print_success(f"ENCRYPTION_KEY length: {len(settings.ENCRYPTION_KEY)}")
        print_success(f"POSTGRES_PASSWORD length: {len(settings.POSTGRES_PASSWORD)}")
        return True
    except Exception as e:
        print_failure(f"Strong secrets should be accepted: {e}")
        return False


def test_testing_mode_allows_defaults() -> bool:
    """Test that testing mode allows defaults."""
    print_test(5, "Testing mode allows defaults")
    
    try:
        settings = Settings(
            APP_ENV="testing",
            SECRET_KEY=None,
            ENCRYPTION_KEY=None,
            POSTGRES_PASSWORD=None,
        )
        print_success("Testing mode allows None values")
        print_success(f"Auto-generated SECRET_KEY: {settings.SECRET_KEY[:20]}...")
        print_success(f"Auto-generated ENCRYPTION_KEY: {settings.ENCRYPTION_KEY[:20]}...")
        print_success(f"Auto-generated POSTGRES_PASSWORD: {settings.POSTGRES_PASSWORD[:10]}...")
        
        # Verify auto-generated values meet requirements
        if len(settings.SECRET_KEY) >= 32:
            print_success(f"Auto-generated SECRET_KEY meets length requirement ({len(settings.SECRET_KEY)} chars)")
        else:
            print_failure(f"Auto-generated SECRET_KEY too short: {len(settings.SECRET_KEY)} chars")
            return False
        
        if len(settings.ENCRYPTION_KEY) >= 32:
            print_success(f"Auto-generated ENCRYPTION_KEY meets length requirement ({len(settings.ENCRYPTION_KEY)} chars)")
        else:
            print_failure(f"Auto-generated ENCRYPTION_KEY too short: {len(settings.ENCRYPTION_KEY)} chars")
            return False
        
        if len(settings.POSTGRES_PASSWORD) >= 16:
            print_success(f"Auto-generated POSTGRES_PASSWORD meets length requirement ({len(settings.POSTGRES_PASSWORD)} chars)")
        else:
            print_failure(f"Auto-generated POSTGRES_PASSWORD too short: {len(settings.POSTGRES_PASSWORD)} chars")
            return False
        
        return True
    except Exception as e:
        print_failure(f"Testing mode should allow defaults: {e}")
        return False


def test_boundary_conditions() -> bool:
    """Test boundary conditions (exactly minimum length)."""
    print_test(6, "Boundary conditions (minimum length secrets)")
    
    try:
        settings = Settings(
            APP_ENV="development",
            SECRET_KEY="a1b2c3d4e5f6g7h8i9j0k1l2m3n4o5p6",  # Exactly 32 chars
            ENCRYPTION_KEY="12345678901234567890123456789012",  # Exactly 32 chars
            POSTGRES_PASSWORD="1234567890123456",  # Exactly 16 chars
        )
        print_success("Minimum length secrets accepted")
        print_success(f"SECRET_KEY: {len(settings.SECRET_KEY)} chars (minimum 32)")
        print_success(f"ENCRYPTION_KEY: {len(settings.ENCRYPTION_KEY)} chars (minimum 32)")
        print_success(f"POSTGRES_PASSWORD: {len(settings.POSTGRES_PASSWORD)} chars (minimum 16)")
        return True
    except Exception as e:
        print_failure(f"Minimum length secrets should be accepted: {e}")
        return False


def test_empty_strings_rejected() -> bool:
    """Test that empty strings are rejected."""
    print_test(7, "Empty strings rejected")
    
    try:
        Settings(
            APP_ENV="development",
            SECRET_KEY="",
            ENCRYPTION_KEY="",
            POSTGRES_PASSWORD="",
        )
        print_failure("Should have rejected empty strings")
        return False
    except RuntimeError as e:
        if "Required secrets not configured" in str(e):
            print_success("Empty strings correctly rejected")
            return True
        else:
            print_failure(f"Unexpected error message: {e}")
            return False


def test_whitespace_only_rejected() -> bool:
    """Test that whitespace-only strings are rejected."""
    print_test(8, "Whitespace-only strings rejected")
    
    try:
        Settings(
            APP_ENV="development",
            SECRET_KEY="   ",
            ENCRYPTION_KEY="   ",
            POSTGRES_PASSWORD="   ",
        )
        print_failure("Should have rejected whitespace-only strings")
        return False
    except RuntimeError as e:
        if "Required secrets not configured" in str(e):
            print_success("Whitespace-only strings correctly rejected")
            return True
        else:
            print_failure(f"Unexpected error message: {e}")
            return False


def main() -> int:
    """Run all verification tests."""
    print_header("🔍 Verifying Secrets Validation (TASK 2.1)")
    
    tests = [
        test_missing_secrets_rejected_development,
        test_missing_secrets_rejected_production,
        test_weak_secrets_rejected,
        test_strong_secrets_accepted,
        test_testing_mode_allows_defaults,
        test_boundary_conditions,
        test_empty_strings_rejected,
        test_whitespace_only_rejected,
    ]
    
    results = []
    for test_func in tests:
        try:
            result = test_func()
            results.append(result)
        except Exception as e:
            print_failure(f"Test failed with exception: {e}")
            results.append(False)
    
    # Summary
    print_header("📊 Verification Summary")
    passed = sum(results)
    total = len(results)
    
    print(f"\nTests passed: {passed}/{total}")
    
    if passed == total:
        print("\n✅ All verification tests passed!")
        print("\nThe secrets validation is working correctly:")
        print("  • Missing secrets are rejected")
        print("  • Weak secrets are rejected")
        print("  • Placeholder values are detected")
        print("  • Strong secrets are accepted")
        print("  • Testing mode provides safe defaults")
        print("  • Boundary conditions handled correctly")
        print("\n🚀 Ready for deployment!")
        return 0
    else:
        print(f"\n❌ {total - passed} test(s) failed!")
        print("\n⚠️  Please review the failures above and fix the issues.")
        return 1


if __name__ == "__main__":
    sys.exit(main())
