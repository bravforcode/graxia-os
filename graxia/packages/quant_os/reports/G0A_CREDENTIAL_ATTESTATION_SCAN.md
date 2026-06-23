# G0A Credential Attestation Scan

**Scan Date:** 2026-06-23
**Worktree:** `C:\tmp\quant_os_g0a_verify` (verification, read-only)
**Output:** This file in OUTPUT dir

---

## 1. Attestation Field Validation

**File:** `reports/G0A_CREDENTIAL_ROTATION_ATTESTATION.json`

| Field | Expected | Actual | Status |
|-------|----------|--------|--------|
| `account_mode` | `"DEMO"` | `"DEMO"` | PASS |
| `old_credential_revoked_or_replaced` | `true` | `true` | PASS |
| `credential_source` | `"TERMINAL_SESSION_ONLY"` | `"TERMINAL_SESSION_ONLY"` | PASS |
| `approved_terminal_path_fingerprint` | SHA-256 present | `sha256:ade8f62fe56071266d682245044bcf0aa6c07d2a6a2c52eea0b6f173e2c8cf67` | PASS |
| `account_identity_fingerprint` | SHA-256 present | `sha256:b2a952e42de3af5e5c5e8eecfaec788c794f9cb3bb75d1b407badf26694ef3cb` | PASS |
| `server_identity_fingerprint` | SHA-256 present | `sha256:7b984b3e558ab5d51e28e47113b86984e066022b253b1fabc710a1c2f43c1d70` | PASS |
| `contains_plaintext_credentials` | `false` | `false` | PASS |

**Field verdict:** 7/7 PASS

---

## 2. Raw Secret Scan — G0A Report Files

Scanned files:
- `reports/G0A_CREDENTIAL_ROTATION_ATTESTATION.json`
- `reports/G0A_DATETIME_AUDIT.md`
- `reports/G0A_HOOK_INSTALLATION.md`
- `reports/REPORT_G0A_REMEDIATION.md`

### Target Patterns

| Pattern | Type | Found | Location | Verdict |
|---------|------|-------|----------|---------|
| `61547941` | Numeric account ID | NO | — | CLEAN |
| `!muyrwBf4v` | Password literal | NO | — | CLEAN |
| `Pepperstone-Demo` | Server name | NO | — | CLEAN |
| `ICMarkets` | Broker name (partial) | YES | `REPORT_PHASE_3_2_MT5_READINESS.md:41` | NOT A CREDENTIAL (see below) |
| `password = "..."` | Credential literal | NO | — | CLEAN |
| `api_key = "..."` | Credential literal | NO | — | CLEAN |
| `MT5_LOGIN` | Env var reference | YES | Documentation only (see below) | CLEAN |
| `MT5_PASSWORD` | Env var reference | YES | Documentation only (see below) | CLEAN |
| `MT5_SERVER` | Env var reference | YES | Documentation only (see below) | CLEAN |

### Explanation of Non-Credential Matches

- **`ICMarkets`** — Found in `REPORT_PHASE_3_2_MT5_READINESS.md:41` as `"Default profile targets ICMarkets Demo02 with 5 symbols."` This is a broker profile name reference in a non-G0A readiness report. Not a credential, not a login, not a password. No account number or secret attached.

- **`MT5_LOGIN/MT5_PASSWORD/MT5_SERVER`** — All occurrences are in `G0A_HOOK_INSTALLATION.md` (lines 7-8, 36-38) and `REPORT_G0A_REMEDIATION.md` (line 44). These are documentation references describing what the pre-commit hook scans for or describing the before-state of remediation. No actual values are present.

### Non-G0A Report Scan

The attestation and G0A report files were scanned exhaustively. No raw credential literals (`61547941`, `!muyrwBf4v`, `Pepperstone-Demo`) were found in any scanned file.

---

## 3. Verdict

**CLEAN**

- All 7 attestation fields validated correctly
- No raw secrets found in attestation or G0A report files
- Two non-credential broker/variable name references found in documentation context only — no actual secret values exposed
