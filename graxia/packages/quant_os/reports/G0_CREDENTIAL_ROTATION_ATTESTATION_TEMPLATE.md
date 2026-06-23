# G0 Credential Rotation Attestation Template

## Status
- Template only.
- This file is not evidence until an operator records and signs a real attestation.

## Redaction rules
- Do not include any password.
- Do not include any login number.
- Do not include any server secret.
- Do not include any token or terminal path.

## Required fields

```yaml
rotated_at_utc: "REPLACE_WITH_UTC_TIMESTAMP"
account_mode: "DEMO"
credential_source: "TERMINAL_SESSION_ONLY"
terminal_session_fingerprint_hash: "sha256:REPLACE_WITH_HASH"
old_credential_revoked_or_replaced: true
operator_attestation_id: "REDACTED_OPERATOR_ID"
recorded_at_utc: "REPLACE_WITH_UTC_TIMESTAMP"
notes: "Optional short note. No secret values."
```

## Gate note
- Phase 0A remains `BLOCKED` until a real redacted attestation is recorded.
