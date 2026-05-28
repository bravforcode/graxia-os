# Phase 22.5 — Provider Virtualization Policy

## Policy

All external provider calls must use mock/sandbox in AI Tester tests.

| Provider | Allowed Mode | Disallowed Mode |
|---|---|---|
| Stripe | test_key / mock | sk_live_ |
| Email (Resend) | mock / disabled | re_live_ |
| Google Workspace | read_only / mock | write / mutation |
| LLM (OpenAI/Gemini) | mock / disabled | live call |
| Database | local / test | production (supabase.co) |

## Enforcement

The `ProviderGuard` class checks environment variables (without reading `.env`) to verify no live provider keys are present.

### Hard Fail Conditions

- Live Stripe key (`sk_live_`)
- Production database URL (contains `supabase.co`)
- Any `liveProvidersEnabled = true`

### Safe Conditions

- No API keys set → all providers = mock
- Test keys only → providers = test/mock
- Local database → providers = local
- LLM keys present but not called → providers = configured (not live)

## Usage

```python
from app.beta.synthetic_tester.provider_guard import check_provider_guard, assert_no_live_providers

# Check without raising
result = check_provider_guard(env_overrides={})
print(result.to_dict())

# Assert (raises RuntimeError if live)
assert_no_live_providers(env_overrides={})
```
