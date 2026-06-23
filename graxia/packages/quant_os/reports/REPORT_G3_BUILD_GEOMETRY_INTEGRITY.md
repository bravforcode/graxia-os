# G3 Build Geometry Integrity

## Provenance

| Field | Value |
|-------|-------|
| source_code_sha | `cc27c465fc6e791a20be1a0d79f4bbeba842890c` |
| run_id | `20260623_102610` |

## Market Snapshot

| Field | Value |
|-------|-------|
| bid | 4129.56 |
| ask | 4129.69 |
| spread | 0.13 |

## Geometry Comparison

| Field | Before (G2.1b bug) | After (true 1:1) |
|-------|-------------------|------------------|
| BUY protective_buffer | 0.57 | 0.57 |
| BUY spread | 0.71 | 0.71 |
| BUY gross_loss_delta | 0.71 (spread only) | 1.28 (spread+buffer) |
| BUY gross_reward_delta | 0.43 | 1.28 |
| BUY planned_gross_rr | 0.61 | 1.0 |
| SELL spread | 1.14 | 1.14 |
| SELL gross_loss_delta | 1.14 (spread only) | 1.71 (spread+buffer) |
| SELL gross_reward_delta | 0.57 | 1.71 |
| SELL planned_gross_rr | 0.50 | 1.0 |

## Formula (explicit)

BUY: entry=ask, SL=bid-buffer, gross_loss=entry-SL, TP=entry+gross_loss

SELL: entry=bid, SL=ask+buffer, gross_loss=SL-entry, TP=entry-gross_loss

## Tests: 30/30 pass

## Verdict

PASS_TO_G3_FINAL_PREFLIGHT
