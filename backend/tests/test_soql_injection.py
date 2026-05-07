"""Tests for SOQL injection prevention in Salesforce integration."""

import pytest
from app.integrations.salesforce import _validate_safe_email


def test_valid_emails_pass():
    assert _validate_safe_email("user@example.com") == "user@example.com"
    assert (
        _validate_safe_email("first.last+tag@sub.domain.co.uk") == "first.last+tag@sub.domain.co.uk"
    )


def test_soql_injection_single_quote_rejected():
    with pytest.raises(ValueError):
        _validate_safe_email("test@example.com' OR '1'='1")


def test_soql_injection_delete_statement_rejected():
    with pytest.raises(ValueError):
        _validate_safe_email("test'; DELETE FROM Lead--@x.com")


def test_soql_injection_union_select_rejected():
    with pytest.raises(ValueError):
        _validate_safe_email("' UNION SELECT Id FROM User--@x.com")


def test_empty_email_rejected():
    with pytest.raises(ValueError):
        _validate_safe_email("")


def test_whitespace_only_rejected():
    with pytest.raises(ValueError):
        _validate_safe_email("   ")


def test_no_at_sign_rejected():
    with pytest.raises(ValueError):
        _validate_safe_email("notanemail")
