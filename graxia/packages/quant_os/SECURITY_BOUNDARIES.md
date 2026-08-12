# Security Boundaries

## Execution Authority

- Only quant_os may control MT5 orders
- No external repository has order_send permission
- Quarantined repos have zero permissions

## Credential Policy

- No credentials stored in code
- No .env files read by tests
- MT5 gateway is read-only

## Risk Controls

- Kill switch is persistent and cannot be bypassed by code
- Pre-trade risk gate is mandatory
- Risk policy is frozen dataclass
