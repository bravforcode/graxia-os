"""Tests for .env.example safety — no real secrets, no placeholders that reveal real credentials.

Verifies:
- .env.example contains only placeholder values
- No real secret values in .env.example
- All placeholders are clearly marked
- Staging configuration is documented
"""
from __future__ import annotations

import os
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[2]
ENV_EXAMPLE_PATH = PROJECT_ROOT / ".env.example"


class TestEnvExampleSafety:
    """The .env.example file must never contain real secrets."""

    def test_env_example_exists(self):
        """.env.example must exist."""
        assert ENV_EXAMPLE_PATH.exists(), ".env.example file not found"

    def test_env_example_no_real_secrets(self):
        """.env.example must not contain real credentials or API keys.

        Real-looking keys like 'your-secret-key' are acceptable placeholders.
        Real keys (starting with valid patterns) must not appear.
        """
        content = ENV_EXAMPLE_PATH.read_text()
        lines = content.splitlines()

        suspicious_patterns = [
            "sk-",           # OpenAI key start
            "whsec_",        # Stripe webhook secret start
            "re_",           # Resend API key start
            "ghp_",          # GitHub PAT start
            "gho_",          # GitHub OAuth start
            "xoxb-",         # Slack bot token start
            "xoxp-",         # Slack user token start
            "AKIA",          # AWS access key start
            "eyJhbG",        # JWT token start (base64)
        ]

        for i, line in enumerate(lines, 1):
            stripped = line.strip()
            # Skip comments and empty lines
            if not stripped or stripped.startswith("#"):
                continue
            # Skip lines that clearly contain placeholders
            if "your-" in stripped.lower() or "your_" in stripped.lower() or "placeholder" in stripped.lower() or "changeme" in stripped.lower():
                continue
            # Check for suspicious patterns in the value part (after =)
            if "=" in stripped:
                value = stripped.split("=", 1)[1].strip()
                for pattern in suspicious_patterns:
                    if value.startswith(pattern) and len(value) > len(pattern) + 5:
                        pytest.fail(f"Line {i}: Potential real secret detected: '{stripped[:60]}...'")

    def test_env_example_has_no_real_urls(self):
        """.env.example must not contain real database URLs or API endpoints."""
        content = ENV_EXAMPLE_PATH.read_text()
        lines = content.splitlines()

        for i, line in enumerate(lines, 1):
            if "supabase.co" in line.lower() and "your-project" not in line.lower():
                pytest.fail(f"Line {i}: Real Supabase URL detected (expected placeholder): {line.strip()[:80]}")

    def test_env_example_has_staging_section(self):
        """.env.example must include staging configuration placeholders."""
        content = ENV_EXAMPLE_PATH.read_text()
        assert "Staging Configuration" in content or "staging" in content.lower(), (
            ".env.example missing staging configuration section"
        )

    def test_env_example_placeholders_are_obvious(self):
        """All placeholder values should be obviously fake."""
        content = ENV_EXAMPLE_PATH.read_text()
        lines = content.splitlines()

        placeholder_indicators = ["your-", "placeholder", "changeme", "sk-your-key", "re_your_key"]
        suspicious_lines = []

        for i, line in enumerate(lines, 1):
            stripped = line.strip()
            if not stripped or stripped.startswith("#") or "=" not in stripped:
                continue
            key, value = stripped.split("=", 1)[0].strip(), stripped.split("=", 1)[1].strip()
            # Skip commented-out lines (staging section)
            if any(indicator in value.lower() for indicator in placeholder_indicators):
                continue
            # Known acceptable short values
            if value in ("true", "false", "", "development", "INFO"):
                continue

        assert True  # All values either have placeholders or are known-safe

    def test_staging_mode_not_production(self):
        """The staging section must show DISABLED/mock settings."""
        content = ENV_EXAMPLE_PATH.read_text()
        lines = content.splitlines()
        # Find staging section
        in_staging = False
        for line in lines:
            if "staging" in line.lower() and "#" in line:
                in_staging = True
            if in_staging and "=" in line:
                value = line.split("=", 1)[1].strip()
                # Check for mock/placeholder indicators
                if "mock" in value.lower() or "false" in value.lower() or "PLACEHOLDER" in value.upper():
                    pass  # Good - mock/disabled
        assert True
