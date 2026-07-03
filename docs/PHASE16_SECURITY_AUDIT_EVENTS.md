# Phase 16 Security Audit Events

## Implemented Helper

File:

`backend/app/audit/security_events.py`

## Current Event Types

- `auth.missing`
- `auth.invalid`
- `permission.denied`
- `org.required`
- `org.boundary.denied`
- `rate_limit.exceeded`
- `payload.too_large`
- `mcp.dangerous.blocked`
- `safe_error.emitted`

## Logged Fields

- `reason_code`
- `risk_level`
- `route_or_tool`
- `request_id`
- `correlation_id`
- `organization_id`
- `actor_type`
- `actor_id`
- redacted payload

## Redaction Rules

- redact keys containing:
  - `authorization`
  - `password`
  - `secret`
  - `token`
  - `cookie`
  - `api_key`
  - `access_token`
  - `refresh_token`
- customer/public token values never logged raw
- delivery/public token identifiers use fingerprint only

## Current Coverage

- `backend/tests/test_security_audit_events.py`
- `backend/tests/test_rate_limit.py`
- `backend/tests/test_safe_errors.py`

## Remaining Follow-up

- add org-boundary deny audit assertions
- add MCP deny audit assertions
- add workflow deny audit assertions
