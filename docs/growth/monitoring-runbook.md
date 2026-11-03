# Funnel monitoring runbook

The backend exposes bounded Prometheus counters for checkout and Stripe
webhook failures. Load `ops/monitoring/graxia-funnel-alerts.yml` into the
Prometheus rule set and route the alerts through the existing Alertmanager.

The counters intentionally contain only fixed stage/reason labels. They never
include email addresses, payment payloads, card data, tokens, or secrets.

If an alert fires:

1. Check `/metrics` and the application health endpoint.
2. Inspect the bounded `stage`/`reason` labels and provider status.
3. Verify the Stripe dashboard event before replaying a webhook.
4. Do not mark an order paid from a browser return URL.
