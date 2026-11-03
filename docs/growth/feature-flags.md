# Growth OS runtime flags

These flags are independent kill switches. They do not delete attribution,
orders, bridge evidence, batch records, or publish receipts.

| Flag | Default | Effect when disabled |
| --- | --- | --- |
| `REFERRAL_LOOP_ENABLED` | `true` | Stops referral issue/resolve/conversion |
| `REFERRAL_REWARD_ENABLED` | `true` | Keeps verified conversion ledger, pays no bonus/commission |
| `REVENUE_BRIDGE_ENABLED` | `true` | Rejects new Revenue OS bridge events with 503 |
| `CONTENT_BATCH_ENABLED` | `true` | Stops new batches and blocks queued work safely |
| `CONTENT_OPS_EXTERNAL_PUBLISH_ENABLED` | `false` | Keeps content in export/dry-run mode |

For production rollout, set `CONTENT_OPS_EXTERNAL_PUBLISH_ENABLED=false` until
provider consent, credentials, approval, canary, claim review, and UTM checks
have current evidence. Payment/revenue claims remain unavailable without
verified provider evidence.
