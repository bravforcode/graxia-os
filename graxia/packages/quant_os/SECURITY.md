# Security Policy

## Reporting a Vulnerability

If you discover a security vulnerability in quant_os, please report it via email to **[security@graxia.dev](mailto:security@graxia.dev)** — do **not** open a public GitHub issue.

Please include:
- A description of the vulnerability
- Steps to reproduce
- Potential impact
- Any suggested mitigation (if known)

We aim to acknowledge receipt within 48 hours and provide a fix or mitigation timeline within 5 business days.

## Scope

Security coverage applies to:

- Core trading logic (`core/`, `execution/`, `risk/`, `strategies/`, `validation/`)
- API surface (`api/`, `broker/`)
- Authentication and credential handling
- Dataset and configuration integrity
- Dependency supply chain (via pre-commit and CI scanning)

Out of scope:

- Backtest and research outputs (treated as non-production artifacts)
- Third-party broker APIs (responsibility lies with the broker)
- Development-only scripts and test fixtures

## Best Practices

- Never commit secrets, API keys, or credentials to the repository
- Use environment variables (`.env`) for all sensitive configuration
- Run `detect-private-key` pre-commit hook locally
- Keep dependencies updated via regular `pip audit` or Dependabot
