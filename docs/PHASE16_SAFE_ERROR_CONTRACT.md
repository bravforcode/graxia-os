# Phase 16 Safe Error Contract

## External Shape

```json
{
  "error": {
    "code": "RATE_LIMITED",
    "message": "Too many requests",
    "request_id": "req_...",
    "correlation_id": "req_..."
  }
}
```

## Current Codes

- `AUTH_REQUIRED`
- `AUTH_INVALID`
- `PERMISSION_DENIED`
- `ORG_REQUIRED`
- `ORG_FORBIDDEN`
- `RATE_LIMITED`
- `PAYLOAD_TOO_LARGE`
- `NOT_FOUND`
- `VALIDATION_ERROR`
- `DANGEROUS_BLOCKED`
- `APPROVAL_REQUIRED`
- `INTERNAL_ERROR`

## Guarantees

- `request_id` always present
- `correlation_id` always present
- no stack trace in external response
- no SQL, file path, or secret-like value in external response
- 429 preserves `Retry-After`
- middleware-level 401/403/413/429 use same envelope as route exceptions

## Current Coverage

- `backend/tests/test_rate_limit.py`
- `backend/tests/test_payload_size_guard.py`
- `backend/tests/test_safe_errors.py`

## Remaining Follow-up

- extend coverage to more public/customer routes
- extend safe error assertions to MCP HTTP transport and workflow APIs
