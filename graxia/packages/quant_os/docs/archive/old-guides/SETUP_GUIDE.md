# Setup Guide

## Status

This archived guide is deprecated for MT5 credential handling.

Do not place `MT5_LOGIN`, `MT5_PASSWORD`, or `MT5_SERVER` in repo-owned files, compose manifests, or checked-in setup notes.

## Phase 0A Policy

Use terminal-session-only MT5 authentication.

1. Install or locate the MT5 terminal on the host machine.
2. Sign into the terminal interactively outside the repository.
3. Provide only non-secret runtime location and timeout settings from repo-owned paths:
   - `MT5_PATH`
   - `MT5_TIMEOUT_MS`
4. Keep broker identity in non-secret broker profile metadata such as:
   - `profile_id`
   - `expected_server`
   - `account_mode`
   - `account_currency`
   - `account_login`

## Approved Examples

```env
MT5_PATH=C:\Program Files\MetaTrader 5\terminal64.exe
MT5_TIMEOUT_MS=10000
```

Broker identity belongs in broker profile metadata, not secret env vars.

## Deprecated Examples

Do not use:

```env
MT5_LOGIN=12345678
MT5_PASSWORD=example-secret
MT5_SERVER=Broker-Demo
```

## Rationale

Current repository policy rejects broker credential env injection and initializes MT5 using path and timeout only. This archived guide exists to prevent old setup patterns from reintroducing repo-owned secret guidance.
