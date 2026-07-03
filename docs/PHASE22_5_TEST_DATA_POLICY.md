# Phase 22.5 — Test Data Policy

## Rules

### 1. No Real PII
All test data uses synthetic identities with `@example.test` email domains. No real names, addresses, or phone numbers.

### 2. Test Prefix Convention
All IDs must be clearly prefixed to distinguish from real data:

| Entity | Prefix |
|---|---|
| Organization | `org_test_` |
| User | `user_test_` |
| Operator | `op_test_` |
| Feedback | `test_` |
| Run | `run_` |
| Evidence | `rev_` |

### 3. No Real Payment Data
No credit card numbers, bank accounts, or payment tokens in test data.

### 4. All Payloads Marked `is_test: true`
Every test data payload includes `is_test: True` for easy filtering.

### 5. Adversarial Data Marked
Adversarial test cases (wrong org, missing permission, etc.) are explicitly created by dedicated factory functions.

### 6. All Emails Use `@example.test`
The only allowed email domain for test data is `@example.test` (RFC 2606 reserved domain).

### 7. No Secrets in Test Data
Test data does not contain API keys, tokens, certificates, or credentials.
