# Revenue attribution bridge v1

## Scope

This contract defines the inbound, provider-signed evidence envelope for the
Phase 3 Revenue OS bridge. It records evidence only after signature
verification. It does not activate a subscription from a browser redirect,
checkout return URL, or client-side state.

The bridge endpoint is `POST /api/v1/revenue-bridge/events`. Router
registration remains an integration concern for the host application.

## Envelope

Every request contains exactly these fields:

| Field | Type | Allowed values / meaning |
| --- | --- | --- |
| `provider` | string | Provider identifier. |
| `provider_event_id` | string | Stable provider event id. |
| `organization_id` | UUID | Graxia organization receiving the event. |
| `event_kind` | string | `subscription_activated`, `subscription_cancelled`, `payment_failed`, or `refund`. |
| `plan` | string | `starter`, `growth`, or `scale`. |
| `amount` | decimal | Non-negative amount. |
| `currency` | string | `THB` only. |
| `occurred_at` | string | ISO-8601 timestamp with timezone. |
| `signature` | string | Hex SHA-256 HMAC, optionally prefixed with `sha256=`. |

Unknown fields are rejected. The provider event id is unique per provider;
re-delivery of the same provider event is a successful no-op.

## HMAC

The shared secret is supplied as `REVENUE_BRIDGE_HMAC_SECRET`. The signature
covers the following UTF-8 canonical string, excluding `signature`:

```text
provider|provider_event_id|organization_id|event_kind|plan|amount|currency|occurred_at
```

`amount` uses its plain decimal representation. `occurred_at` is normalized
to UTC and serialized with microseconds using `datetime.isoformat()`.

The bridge compares the supplied digest with a constant-time comparison.
Signature verification occurs before the duplicate lookup can result in a
write, and before any event or purchase record is committed.

## Normalization and attribution

Verified events are stored with normalized status:

| Event kind | Normalized status | Purchase conversion event |
| --- | --- | --- |
| `subscription_activated` | `active` | Yes, exactly once. |
| `subscription_cancelled` | `canceled` | No. |
| `payment_failed` | `past_due` | No. |
| `refund` | `refunded` | No. |

Only a verified `subscription_activated` creates the existing
`ConversionEvent(event_type="purchase")`, with an idempotency key derived from
the provider and provider event id. No other event kind creates that purchase
event.

## Evidence boundary

Absent a verified provider event, revenue and subscription evidence are
unavailable. This bridge does not claim live production evidence, payment
provider reachability, successful checkout, or production revenue.
