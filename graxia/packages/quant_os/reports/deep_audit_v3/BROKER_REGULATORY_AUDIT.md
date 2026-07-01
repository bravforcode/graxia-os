# PHASE 11 — BROKER, COUNTERPARTY & REGULATORY AUDIT
*Per R1–R18. Tier 2. Several items require external sources — marked `[UNVERIFIED — requires broker disclosure]`.*

---

## 11.1 — Broker Identity & Regulatory Status
- Server name: **ambiguous** — `core/config.py:32` `ICMarketsSC-Demo`; `.env:4` `Pepperstone-Demo`; `Meta/pepperstone_creds.txt:5` `Pepperstone-Demo03`. **Three identities. Which broker the live system connects to is not pinned to one value.** → P1.
- Regulated & by which authority: `[UNVERIFIED — requires checking Pepperstone/IC Markets public disclosures; not in repo]`. Pepperstone is typically regulated by FCA/ASIC/DFSA; IC Markets by ASIC/Seychelles. **Must be verified against the broker's own site, not assumed.**
- Execution model (ECN/STP vs market-maker): `.env`/creds say **Razor** account → Pepperstone Razor is marketed as ECN/raw-spread-plus-commission. But "Razor" is a *branding* claim; the actual execution model (does the broker take the other side, or route to LPs?) `[UNVERIFIED from repo]`. → P1 (material for Phase 2.2's market-maker caveat).
- Negative balance protection / segregated funds: `[UNVERIFIED — requires broker TOS]`. → Critical per Phase 11.5.

## 11.2 — Real-World Cost Schedule Reconciliation
- Backtest assumes: `dynamic_spread_model.py` session spreads (asian=3, london=1.5, ny=1.5, overlap=1.2, closed=5 pips for XAUUSD) + `commission_per_lot=3.5`.
- Broker's actual published schedule: `[NOT PULLED]`. Pepperstone Razor XAUUSD typical ~10–20 pts (1.0–2.0 pips) + $3.5/side commission — the model's 1.2–5.0 pips is in a plausible range but **the actual live spread history has not been logged and compared** (Phase 11.3). → P1.
- Swap rates / triple-swap day: `[NOT MODELED — Phase 7.1 dead flag]`. → P2.
- Broker restrictions (scalping/hold-time/news): `[NOT CHECKED]`. → P2.

## 11.3 — Execution Quality Evidence
- `[NEVER MEASURED]` — no live/demo trade export with requote rate, signed slippage, fill-time distribution found. **Backtest cost assumptions are unvalidated against live execution.** → P1.
- News-time spread widening logged: `[no]`. The strategy may trade through news windows (no explicit avoidance logic confirmed). → P2.

## 11.4 — Legal, Tax & Compliance (Thailand-based)
> *Informational scaffolding only — not legal/tax advice.*
- Thai-licensed advisor confirmation that retail FX/CFD via this broker is permitted for a Thailand resident: `[NOT VERIFIED — recommend confirming with a Thai-licensed financial/legal advisor before scaling capital]`.
- Thai personal income tax treatment of trading profit: `[NOT ADDRESSED]`.
- THB FX conversion risk on deposits/withdrawals (account likely USD): `[NOT ADDRESSED]`. → P2.

## 11.5 — Counterparty Risk Table

| Item | Status | Severity if Unfavorable |
|---|---|---|
| Broker regulatory status confirmed | UNVERIFIED | High |
| Execution model confirmed | UNVERIFIED (Razor branding only) | High |
| Negative balance protection confirmed | UNVERIFIED | **Critical** |
| Segregated client funds confirmed | UNVERIFIED | High |
| Real spread schedule matches backtest | PARTIAL (model in range, not validated) | High |
| Swap rates confirmed & modeled | NO (dead flag) | Medium |
| Thai tax treatment researched | NOT ADDRESSED | Medium |
| Thai regulatory permissibility researched | NOT VERIFIED | Medium |

---

## Phase 11 — Verdict

**STATUS: BLOCKED ON EXTERNAL DATA.** Every counterparty item is UNVERIFIED — not because the code is wrong, but because these facts live in broker disclosures and Thai regulation, not in the repo. **Critical: negative-balance-protection status is unknown; in a gap-through tail event (Phase 12) without it, theoretical loss exceeds account equity.** This must be resolved before any live capital, full stop.
