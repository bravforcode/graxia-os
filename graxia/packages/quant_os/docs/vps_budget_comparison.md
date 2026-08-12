# GRAXIA-OS VPS Budget Comparison

## Cost Breakdown

| Provider | Plan | Price/mo | Location | RAM | vCPU | Storage | Notes |
|----------|------|----------|----------|-----|------|---------|-------|
| **Contabo** | Windows VPS S | ~€5-6 | London LD4 | 4 GB | 2 | 50 GB SSD | Best value for primary; same metro as Pepperstone UK |
| **Hyonix** | Windows VPS | ~$7-8 | Singapore | 2 GB | 1 | 30 GB SSD | Good for standby (different provider, different geography) |
| **Hetzner** | CX22 + Windows License | ~€8 | Falkenstein | 4 GB | 2 | 40 GB SSD | Higher CPU perf, less known London latency |
| **AWS Lightsail** | Windows 1 GB | ~$8-12 | London | 1 GB | 1 | 30 GB SSD | More reliable SLA, marginally more expensive, 1 GB RAM tight |
| **DigitalOcean** | Premium Droplet + Windows | ~$12-16 | London | 2 GB | 2 | 60 GB SSD | Good reputation, pricier for Windows |
| **Vultr** | Cloud Compute + Windows | ~$10-12 | London | 2 GB | 1 | 40 GB SSD | Decent middle ground |

## Recommended Setup

| Role | Provider | Plan | Monthly Cost |
|------|----------|------|-------------|
| **Primary** | Contabo | Windows VPS S (London LD4) | ~€5-6 |
| **Standby** | Hyonix | Windows VPS (Singapore) | ~$7-8 |
| **Total** | | | **~$15-20/month** |

## Risk Analysis

| Scenario | Potential Loss | VPS Cost |
|----------|---------------|----------|
| Home PC crash during open position (0.01 lot, 1R) | $6.30 | $15/mo |
| Home PC crash during open position (0.10 lot, 1R) | $63 | $15/mo |
| Home PC crash during open position (0.10 lot, 3R run) | $189 | $15/mo |
| Internet outage during news event (slippage amplified) | $50-200+ | $15/mo |
| Power outage during weekend gap | Unquantified | $15/mo |

At 1R = $6.30 (0.01 lot XAUUSD), a single crash during an open position covers **5 months** of dual-VPS setup. The VPS pays for itself if it prevents even one crash.

## Why Different Providers?

- **Contabo + Hyonix** = zero shared infrastructure. A Contabo outage won't take down the Hyonix VPS.
- **London + Singapore** = different power grids, different ISPs, different regulatory zones.
- Avoid pairing Contabo London with Contabo Singapore — same parent company, shared billing/failure domain.

## Environment Variable Template

```ini
# ── Required (both VPS) ──────────────────────────────────────────
TELEGRAM_BOT_TOKEN=1234567890:ABCdefGHIjklMNOpqrsTUVwxyz
TELEGRAM_CHAT_ID=987654321

# ── Primary-only ─────────────────────────────────────────────────
STANDBY_WEBHOOK_URL=http://<standby-ip>:8000/takeover
STANDBY_SECRET=<random-32-char-hex>

# ── Standby-only ─────────────────────────────────────────────────
STANDBY_MODE=watch_only

# ── Optional ─────────────────────────────────────────────────────
ALERT_LEVEL=info              # info (default) | warning | critical
PYTHONIOENCODING=utf-8        # Prevents UnicodeEncodeError on cp1252
```

## Quick Comparison: VPS vs Alternatives

| Method | Cost/mo | Uptime | Latency to Broker | Auto-Restart | Risk |
|--------|---------|--------|-------------------|--------------|------|
| Home PC | $0 | ~99% (power/internet) | 1-5 ms | No | High — single point of failure |
| Contabo VPS (primary only) | ~€5 | 99.95% | 1-2 ms | Yes (Task Scheduler) | Medium — no failover |
| Dual VPS (this setup) | ~$15-20 | 99.99%+ | 1-2 ms | Yes + standby failover | Low — tested failover |
| AWS (production grade) | ~$30-50 | 99.99% | 1-2 ms | Yes + LB + auto-scaling | Lowest — overkill for 0.01 lot |
