#!/usr/bin/env python3
"""
Validate production configuration at build time.

This script validates that all required production configuration is set
before building the Docker image. It fails fast if any configuration is
missing or invalid, preventing deployment of misconfigured systems.

Usage:
    python scripts/validate_production_config.py

Exit Codes:
    0: Configuration is valid
    1: Configuration is invalid (errors found)
    2: Not production environment (skipped validation)

Environment Variables:
    APP_ENV: Application environment (production, staging, development)
    All other configuration variables from app.config.Settings

Example:
    # In Dockerfile
    RUN python scripts/validate_production_config.py

    # Manual validation
    APP_ENV=production python scripts/validate_production_config.py
"""

import sys
import os
from pathlib import Path

# Add backend directory to Python path
backend_dir = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(backend_dir))


def main() -> int:
    """
    Main validation function.
    
    Returns:
        0 if validation passes
        1 if validation fails
        2 if not production environment (skipped)
    """
    try:
        from app.config import settings
    except Exception as e:
        print(f"❌ Failed to load configuration: {e}")
        return 1
    
    # Check if production environment
    if settings.APP_ENV.lower() != "production":
        print(f"ℹ️  Skipping production validation (APP_ENV={settings.APP_ENV})")
        return 2
    
    print("🔍 Validating production configuration...")
    print(f"   Environment: {settings.APP_ENV}")
    print(f"   Strict Bootstrap: {settings.STRICT_BOOTSTRAP}")
    print()
    
    # Get production configuration errors
    try:
        errors = settings.get_production_configuration_errors()
    except Exception as e:
        print(f"❌ Validation failed with exception: {e}")
        return 1
    
    if errors:
        print("❌ Production configuration validation FAILED")
        print()
        print("The following configuration errors were found:")
        print()
        for i, error in enumerate(errors, 1):
            print(f"  {i}. {error}")
        print()
        print("Please fix these errors before deploying to production.")
        print()
        print("Common fixes:")
        print("  - Generate strong secrets: openssl rand -hex 32")
        print("  - Set environment variables in .env file")
        print("  - Update configuration in app/config.py")
        print()
        return 1
    
    print("✅ Production configuration validation PASSED")
    print()
    print("All required configuration is set and valid.")
    print("System is ready for production deployment.")
    print()
    
    # Print summary of key configuration
    print("Configuration Summary:")
    print(f"  - Database: {settings.DATABASE_HOST}:{settings.DATABASE_PORT}")
    print(f"  - Redis: {settings.REDIS_URL.split('@')[-1] if '@' in settings.REDIS_URL else settings.REDIS_URL}")
    print(f"  - CORS Origins: {len(settings.CORS_ORIGINS)} configured")
    print(f"  - JWT Signing Keys: {len(settings.JWT_KEYSET)} configured")
    print(f"  - Supabase: {'Enabled' if settings.IS_SUPABASE else 'Disabled'}")
    print(f"  - Backup: {'Configured' if settings.BACKUP_BUCKET else 'Not configured'}")
    print()
    
    return 0


if __name__ == "__main__":
    exit_code = main()
    sys.exit(exit_code)
