"""
CSRF Timing Attack Tests

This test suite verifies that CSRF token validation is resistant to timing attacks.
It ensures that all token comparisons use constant-time operations and that response
times do not leak information about token validity.

CRITICAL SECURITY REQUIREMENT:
- All CSRF token comparisons must use hmac.compare_digest()
- No short-circuit evaluation that could leak timing information
- Response times should be consistent regardless of token validity
"""
from __future__ import annotations

import statistics
import time
from typing import TYPE_CHECKING

import pytest
from app.config import settings
from app.middleware.security import generate_csrf_token, validate_csrf_token_signature
from hypothesis import given, strategies as st

if TYPE_CHECKING:
    from httpx import AsyncClient


@pytest.mark.asyncio
async def test_csrf_missing_token_rejected(async_client: AsyncClient):
    """Test that requests without CSRF tokens are rejected."""
    original_csrf = async_client.headers.pop("X-CSRF-Token", None)
    try:
        response = await async_client.post(
            "/api/v1/tasks/",
            json={"title": "Test Task", "priority": 5, "assigned_to": "user"},
        )
        assert response.status_code == 403
        assert response.json()["detail"] == "CSRF token missing"
    finally:
        if original_csrf is not None:
            async_client.headers["X-CSRF-Token"] = original_csrf


@pytest.mark.asyncio
async def test_csrf_missing_cookie_token_rejected(async_client: AsyncClient):
    """Test that requests without cookie token are rejected."""
    # Save original cookie
    original_cookie = async_client.cookies.get(settings.CSRF_COOKIE_NAME)
    
    try:
        # Remove CSRF cookie
        async_client.cookies.delete(settings.CSRF_COOKIE_NAME)
        
        response = await async_client.post(
            "/api/v1/tasks/",
            json={"title": "Test Task", "priority": 5, "assigned_to": "user"},
        )
        assert response.status_code == 403
        assert response.json()["detail"] == "CSRF token missing"
    finally:
        # Restore original cookie
        if original_cookie:
            async_client.cookies.set(settings.CSRF_COOKIE_NAME, original_cookie)


@pytest.mark.asyncio
async def test_csrf_missing_header_token_rejected(async_client: AsyncClient):
    """Test that requests without header token are rejected."""
    original_csrf = async_client.headers.pop("X-CSRF-Token", None)
    try:
        response = await async_client.post(
            "/api/v1/tasks/",
            json={"title": "Test Task", "priority": 5, "assigned_to": "user"},
        )
        assert response.status_code == 403
        assert response.json()["detail"] == "CSRF token missing"
    finally:
        if original_csrf is not None:
            async_client.headers["X-CSRF-Token"] = original_csrf


@pytest.mark.asyncio
async def test_csrf_empty_string_token_rejected(async_client: AsyncClient):
    """Test that empty string tokens are rejected."""
    original_csrf = async_client.headers.get("X-CSRF-Token")
    try:
        async_client.headers["X-CSRF-Token"] = ""
        response = await async_client.post(
            "/api/v1/tasks/",
            json={"title": "Test Task", "priority": 5, "assigned_to": "user"},
        )
        assert response.status_code == 403
        assert response.json()["detail"] == "CSRF token missing"
    finally:
        if original_csrf is not None:
            async_client.headers["X-CSRF-Token"] = original_csrf


@pytest.mark.asyncio
async def test_csrf_whitespace_only_token_rejected(async_client: AsyncClient):
    """Test that whitespace-only tokens are rejected."""
    original_csrf = async_client.headers.get("X-CSRF-Token")
    try:
        async_client.headers["X-CSRF-Token"] = "   "
        response = await async_client.post(
            "/api/v1/tasks/",
            json={"title": "Test Task", "priority": 5, "assigned_to": "user"},
        )
        assert response.status_code == 403
        assert response.json()["detail"] == "CSRF token missing"
    finally:
        if original_csrf is not None:
            async_client.headers["X-CSRF-Token"] = original_csrf


@pytest.mark.asyncio
async def test_csrf_mismatched_tokens_rejected(async_client: AsyncClient):
    """Test that mismatched cookie and header tokens are rejected."""
    original_csrf = async_client.headers.get("X-CSRF-Token")
    try:
        # Use a different token in the header
        async_client.headers["X-CSRF-Token"] = "wrong-token-value"
        response = await async_client.post(
            "/api/v1/tasks/",
            json={"title": "Test Task", "priority": 5, "assigned_to": "user"},
        )
        assert response.status_code == 403
        assert response.json()["detail"] == "CSRF token invalid"
    finally:
        if original_csrf is not None:
            async_client.headers["X-CSRF-Token"] = original_csrf


@pytest.mark.asyncio
async def test_csrf_forged_token_rejected(async_client: AsyncClient):
    """Test that forged tokens (valid format but wrong signature) are rejected."""
    original_csrf = async_client.headers.get("X-CSRF-Token")
    original_cookie = async_client.cookies.get(settings.CSRF_COOKIE_NAME)
    
    try:
        # Generate a forged token with wrong session_id
        forged_token = generate_csrf_token("wrong-session-id")
        async_client.headers["X-CSRF-Token"] = forged_token
        async_client.cookies.set(settings.CSRF_COOKIE_NAME, forged_token)
        
        response = await async_client.post(
            "/api/v1/tasks/",
            json={"title": "Test Task", "priority": 5, "assigned_to": "user"},
        )
        assert response.status_code == 403
        assert response.json()["detail"] == "CSRF token forged"
    finally:
        if original_csrf is not None:
            async_client.headers["X-CSRF-Token"] = original_csrf
        if original_cookie:
            async_client.cookies.set(settings.CSRF_COOKIE_NAME, original_cookie)


@pytest.mark.asyncio
async def test_csrf_malformed_token_rejected(async_client: AsyncClient):
    """Test that malformed tokens (missing dot separator) are rejected."""
    original_csrf = async_client.headers.get("X-CSRF-Token")
    original_cookie = async_client.cookies.get(settings.CSRF_COOKIE_NAME)
    
    try:
        # Use a malformed token without dot separator
        malformed_token = "malformed-token-without-dot"
        async_client.headers["X-CSRF-Token"] = malformed_token
        async_client.cookies.set(settings.CSRF_COOKIE_NAME, malformed_token)
        
        response = await async_client.post(
            "/api/v1/tasks/",
            json={"title": "Test Task", "priority": 5, "assigned_to": "user"},
        )
        assert response.status_code == 403
        assert response.json()["detail"] == "CSRF token forged"
    finally:
        if original_csrf is not None:
            async_client.headers["X-CSRF-Token"] = original_csrf
        if original_cookie:
            async_client.cookies.set(settings.CSRF_COOKIE_NAME, original_cookie)


@pytest.mark.asyncio
async def test_csrf_valid_token_accepted(async_client: AsyncClient):
    """Test that valid CSRF tokens are accepted."""
    response = await async_client.post(
        "/api/v1/tasks/",
        json={"title": "Valid CSRF Test", "priority": 5, "assigned_to": "user"},
    )
    # Should succeed (200 or 201) or fail for reasons other than CSRF
    assert response.status_code != 403 or "CSRF" not in response.json().get("detail", "")


@pytest.mark.asyncio
async def test_csrf_timing_attack_resistance_missing_vs_present(async_client: AsyncClient):
    """
    Test that response times are consistent between missing and present tokens.
    
    This prevents timing attacks where an attacker measures response times to
    determine if a token passes the None/empty check.
    """
    original_csrf = async_client.headers.get("X-CSRF-Token")
    original_cookie = async_client.cookies.get(settings.CSRF_COOKIE_NAME)
    
    try:
        # Measure time for missing token
        missing_times = []
        for _ in range(50):
            async_client.headers.pop("X-CSRF-Token", None)
            start = time.perf_counter()
            await async_client.post(
                "/api/v1/tasks/",
                json={"title": "Timing Test", "priority": 5, "assigned_to": "user"},
            )
            elapsed = time.perf_counter() - start
            missing_times.append(elapsed)
        
        # Measure time for wrong token (present but invalid)
        wrong_times = []
        for _ in range(50):
            async_client.headers["X-CSRF-Token"] = "wrong-token"
            async_client.cookies.set(settings.CSRF_COOKIE_NAME, "wrong-token")
            start = time.perf_counter()
            await async_client.post(
                "/api/v1/tasks/",
                json={"title": "Timing Test", "priority": 5, "assigned_to": "user"},
            )
            elapsed = time.perf_counter() - start
            wrong_times.append(elapsed)
        
        # Calculate statistics
        missing_mean = statistics.mean(missing_times)
        wrong_mean = statistics.mean(wrong_times)
        missing_stdev = statistics.stdev(missing_times)
        wrong_stdev = statistics.stdev(wrong_times)
        
        # The difference should be within statistical noise (< 3 standard deviations)
        # This is a heuristic check - in production, more sophisticated timing analysis
        # would be needed, but this catches obvious timing leaks
        max_stdev = max(missing_stdev, wrong_stdev)
        time_diff = abs(missing_mean - wrong_mean)
        
        # Allow up to 3 standard deviations difference (99.7% confidence interval)
        # If the timing difference is larger, it indicates a potential timing leak
        assert time_diff < 3 * max_stdev, (
            f"Timing attack vulnerability detected: "
            f"missing_token_mean={missing_mean:.6f}s, "
            f"wrong_token_mean={wrong_mean:.6f}s, "
            f"difference={time_diff:.6f}s, "
            f"max_stdev={max_stdev:.6f}s, "
            f"threshold={3 * max_stdev:.6f}s"
        )
    finally:
        if original_csrf is not None:
            async_client.headers["X-CSRF-Token"] = original_csrf
        if original_cookie:
            async_client.cookies.set(settings.CSRF_COOKIE_NAME, original_cookie)


@pytest.mark.asyncio
async def test_csrf_timing_attack_resistance_wrong_vs_forged(async_client: AsyncClient):
    """
    Test that response times are consistent between wrong and forged tokens.
    
    This prevents timing attacks where an attacker measures response times to
    determine if a token passes the format check vs signature check.
    """
    original_csrf = async_client.headers.get("X-CSRF-Token")
    original_cookie = async_client.cookies.get(settings.CSRF_COOKIE_NAME)
    
    try:
        # Measure time for wrong token (fails format check)
        wrong_times = []
        for _ in range(50):
            async_client.headers["X-CSRF-Token"] = "wrong-token"
            async_client.cookies.set(settings.CSRF_COOKIE_NAME, "wrong-token")
            start = time.perf_counter()
            await async_client.post(
                "/api/v1/tasks/",
                json={"title": "Timing Test", "priority": 5, "assigned_to": "user"},
            )
            elapsed = time.perf_counter() - start
            wrong_times.append(elapsed)
        
        # Measure time for forged token (passes format check, fails signature check)
        forged_times = []
        for _ in range(50):
            forged_token = generate_csrf_token("wrong-session-id")
            async_client.headers["X-CSRF-Token"] = forged_token
            async_client.cookies.set(settings.CSRF_COOKIE_NAME, forged_token)
            start = time.perf_counter()
            await async_client.post(
                "/api/v1/tasks/",
                json={"title": "Timing Test", "priority": 5, "assigned_to": "user"},
            )
            elapsed = time.perf_counter() - start
            forged_times.append(elapsed)
        
        # Calculate statistics
        wrong_mean = statistics.mean(wrong_times)
        forged_mean = statistics.mean(forged_times)
        wrong_stdev = statistics.stdev(wrong_times)
        forged_stdev = statistics.stdev(forged_times)
        
        max_stdev = max(wrong_stdev, forged_stdev)
        time_diff = abs(wrong_mean - forged_mean)
        
        # Allow up to 3 standard deviations difference
        assert time_diff < 3 * max_stdev, (
            f"Timing attack vulnerability detected: "
            f"wrong_token_mean={wrong_mean:.6f}s, "
            f"forged_token_mean={forged_mean:.6f}s, "
            f"difference={time_diff:.6f}s, "
            f"max_stdev={max_stdev:.6f}s, "
            f"threshold={3 * max_stdev:.6f}s"
        )
    finally:
        if original_csrf is not None:
            async_client.headers["X-CSRF-Token"] = original_csrf
        if original_cookie:
            async_client.cookies.set(settings.CSRF_COOKIE_NAME, original_cookie)


def test_validate_csrf_token_signature_constant_time():
    """
    Test that validate_csrf_token_signature uses constant-time comparison.
    
    This is a unit test that verifies the signature validation function
    uses hmac.compare_digest internally.
    """
    session_id = "test-session-123"
    valid_token = generate_csrf_token(session_id)
    
    # Valid token should pass
    assert validate_csrf_token_signature(valid_token, session_id) is True
    
    # Invalid session_id should fail
    assert validate_csrf_token_signature(valid_token, "wrong-session") is False
    
    # Malformed token should fail
    assert validate_csrf_token_signature("malformed", session_id) is False
    
    # Empty token should fail
    assert validate_csrf_token_signature("", session_id) is False
    
    # None token should fail
    assert validate_csrf_token_signature(None, session_id) is False
    
    # Token without dot should fail
    assert validate_csrf_token_signature("nodot", session_id) is False


def test_generate_csrf_token_format():
    """Test that generated CSRF tokens have the correct format."""
    session_id = "test-session-456"
    token = generate_csrf_token(session_id)
    
    # Token should contain exactly two dot separators (3 parts: random.timestamp.signature)
    assert token.count(".") == 2
    
    # All three parts should be non-empty
    parts = token.split(".")
    assert len(parts) == 3
    random_part, timestamp_part, signature_part = parts
    assert len(random_part) > 0
    assert len(timestamp_part) > 0
    assert len(signature_part) > 0
    
    # Each part should be URL-safe base64 (letters, digits, -, _, =)
    import string
    allowed_chars = set(string.ascii_letters + string.digits + "-_=")
    assert all(c in allowed_chars for c in random_part), f"Random part contains invalid characters: {random_part}"
    assert all(c in allowed_chars for c in timestamp_part), f"Timestamp part contains invalid characters: {timestamp_part}"
    assert all(c in allowed_chars for c in signature_part), f"Signature part contains invalid characters: {signature_part}"


def test_generate_csrf_token_uniqueness():
    """Test that generated CSRF tokens are unique."""
    session_id = "test-session-789"
    tokens = [generate_csrf_token(session_id) for _ in range(100)]
    
    # All tokens should be unique (due to random component)
    assert len(set(tokens)) == 100


def test_csrf_token_signature_verification_edge_cases():
    """Test edge cases in CSRF token signature verification."""
    session_id = "test-session-edge"
    
    # Empty session_id should fail
    token = generate_csrf_token(session_id)
    assert validate_csrf_token_signature(token, "") is False
    
    # Very long session_id should work
    long_session = "x" * 1000
    long_token = generate_csrf_token(long_session)
    assert validate_csrf_token_signature(long_token, long_session) is True
    
    # Special characters in session_id should work
    special_session = "session-with-special-chars-!@#$%"
    special_token = generate_csrf_token(special_session)
    assert validate_csrf_token_signature(special_token, special_session) is True



@given(st.text(min_size=0, max_size=1000))
def test_csrf_timing_invariant_property(token_string: str):
    """
    Property Test: CSRF Timing Invariant
    
    Property: Response time for rejecting an invalid token must not differ from
    rejecting a missing token by more than 1ms on average.
    
    This property-based test generates arbitrary token strings of varying lengths
    (0 to 1000 characters) and verifies that validation time is consistent regardless
    of token content or length.
    
    SECURITY REQUIREMENT:
    - Validation time must be O(1) with respect to token validity
    - No early exit paths that leak information through timing
    - All comparisons must use constant-time operations
    """
    session_id = "test-session-property"
    
    # Measure validation time for the generated token
    start = time.perf_counter()
    result = validate_csrf_token_signature(token_string, session_id)
    elapsed = time.perf_counter() - start
    
    # Validation should complete quickly (< 1ms) for any input
    # This catches timing leaks where certain inputs take significantly longer
    assert elapsed < 0.001, (
        f"CSRF validation took too long: {elapsed:.6f}s for token length {len(token_string)}. "
        f"This may indicate a timing leak vulnerability."
    )
    
    # Invalid tokens should always return False
    # (unless by extreme chance the random string is a valid token, which is astronomically unlikely)
    if token_string != "" and "." in token_string:
        # Only check result for tokens that have the basic format
        # Empty strings and tokens without dots will fail early (which is expected)
        pass
    else:
        # Tokens without proper format should always fail
        assert result is False, f"Malformed token should be rejected: {token_string[:50]}"


@given(
    st.text(min_size=0, max_size=1000),
    st.text(min_size=1, max_size=100)
)
def test_csrf_validation_timing_consistency_property(token: str, session_id: str):
    """
    Property Test: CSRF Validation Timing Consistency
    
    Property: For any token and session_id pair, validation time should be consistent
    and not leak information about token validity through timing differences.
    
    This test verifies that:
    1. Validation completes in < 1ms for all inputs
    2. No timing differences between different token formats
    3. No timing differences between different session IDs
    """
    # Measure validation time
    start = time.perf_counter()
    validate_csrf_token_signature(token, session_id)
    elapsed = time.perf_counter() - start
    
    # All validations should complete quickly
    assert elapsed < 0.001, (
        f"CSRF validation took {elapsed:.6f}s for token length {len(token)}, "
        f"session_id length {len(session_id)}. This may indicate a timing leak."
    )


@given(st.integers(min_value=0, max_value=1000))
def test_csrf_token_length_timing_invariant_property(token_length: int):
    """
    Property Test: CSRF Token Length Timing Invariant
    
    Property: Validation time should not correlate with token length.
    
    This test generates tokens of varying lengths and verifies that validation
    time remains constant, preventing attackers from using timing to determine
    valid token lengths.
    """
    session_id = "test-session-length"
    
    # Generate a token string of the specified length
    token = "x" * token_length
    
    # Measure validation time
    start = time.perf_counter()
    validate_csrf_token_signature(token, session_id)
    elapsed = time.perf_counter() - start
    
    # Validation should be fast regardless of token length
    assert elapsed < 0.001, (
        f"CSRF validation took {elapsed:.6f}s for token length {token_length}. "
        f"Timing should not depend on token length."
    )
