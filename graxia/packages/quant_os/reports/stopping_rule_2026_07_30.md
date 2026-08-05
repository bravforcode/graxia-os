# Stopping Rule — Direction D (Multi-Instrument Expansion) — Pre-Registration

**Status:** LOCKED — 2026-07-30
**Supersedes for future trials:** `reports/stopping_rule_2026_07_12.md` (archived, not deleted — see §6)
**SHA-256 of this file:** recorded in `research/trial_ledger.json` → `lock_doc_sha256` at lock time. No hash is embedded inline here to avoid the self-reference paradox (a hash line inside the file changes the file's own hash). Verify by hashing this file and comparing to the ledger field.
**Cumulative trial count at lock:** 1022 (unchanged — continues from the existing point per §6 of the 07-12 document)

---

## 0. This document is a reversal, stated plainly

Earlier the same day (2026-07-30), `reports/edge_search_2026/VERDICT_2026_07_30.md` was written and marked **FINAL**, with **Option A — Stop completely** checked, Option B explicitly unchecked, and this text in its consequence clause:

> "No further hypothesis trials against `research/trial_ledger.json`'s counter... asking again later does not silently reopen this search."

That verdict is attributed to "user (via AskUserQuestion, session 2026-07-30)" in a session this document's author has no visibility into. When this reversal was proposed, that provenance gap was surfaced explicitly to the user, who — in a separate, later exchange the same day — confirmed: **reverse it, write the override, proceed.** This document is that reversal, done in the open rather than by quietly picking a bigger cap number. `VERDICT_2026_07_30.md` is being annotated (not deleted) to point here.

**This does not use the Option B path defined in §4 of the 07-12 document.** That path requires "a genuinely untried mechanism/instrument class" before reopening. What follows is a new *instrument scope* (USOIL, USDJPY alongside XAUUSD), not a new *mechanism* — the strategies tested will draw from the same methodology families already exhausted under Direction B. The locked document itself calls this insufficient to reopen ("restating Direction B under a new label would not satisfy the rule's intent" — `VERDICT_2026_07_30.md` §4). This override proceeds anyway, on direct user authorization, over that documented objection. That is what "documented why" means here: the reasoning against doing this is on the record, not omitted.

---

## 1. Scope — instruments

Per `config/tradeable_universe.json` (v1.1.0, 2026-07-26), **only 3 of 21 known symbols have any real cost-calibration data**:

| Symbol | Cost status | Note |
|---|---|---|
| XAUUSD | `FROM_TICKS` | 733,743 real ticks, ~27h session-covering window. Adequate for paper, **not** for live sizing — not true multi-day. |
| USOIL | `SINGLE_SNAPSHOT` | 20 samples, single ~3-minute window (2026-07-03). Adequate for paper, insufficient for live. |
| USDJPY | `FROM_TICKS` | 386,245 real ticks, ~27h session-covering window. Same caveat as XAUUSD. |

The other 18 symbols (EURUSD, GBPUSD, SILVER, NAS100, +14 more) are **excluded — no cost data at all.** A trial against any of them would not be testing an edge net of real costs; it would be testing an edge net of an assumption. **This direction's scope is XAUUSD, USOIL, USDJPY only.** "Trade every instrument," as literally requested, is not achievable under this pre-registration — it would require real tick collection for 18 more symbols first, which is calendar-bound data work, not something this document can authorize into existence.

Also on the record: commit `33b90c31` previously fabricated cost numbers for USOIL and USDJPY (a false 3-day window, an invented 0.80bps figure) before being caught and corrected on 2026-07-26. The numbers in the table above are the corrected ones. Any analysis referencing pre-07-26 cost figures for these two symbols inherited fabricated data.

**Precondition on running any trial in this direction:** none of XAUUSD, USOIL, or USDJPY currently has true multi-day (repeated-calendar-day) cost measurement — only single-window snapshots. Per this session's own priority ordering, trials run against single-window cost assumptions produce results no more trustworthy than the ones already sitting in the 1022-trial ledger. Trials MAY be pre-registered and coded under this direction's budget, but **should not be treated as informative for a go-live decision until multi-day cost measurement exists for the specific symbol traded.**

---

## 2. Scope — methodology

**Regime conditioning is explicitly OUT OF SCOPE for this direction.** `validation/regime_detector.py` exists and is real, but `scripts/edge_search_all.py` has zero regime references today — wiring regime detection into the validation pipeline would change how every hypothesis under this direction gets gated, on top of already changing the instrument scope. Stacking two simultaneous methodology changes (new instruments + regime conditioning) compounds researcher-degrees-of-freedom risk in exactly the way the original 07-12 document's §1 exists to prevent. If regime conditioning is wanted later, it needs its own explicit decision and its own accounting — not silent inclusion here.

All other methodology (gate stack: p-value, WFA-OOS, WFE, DSR, PBO-CSCV, bootstrap CI, min-independent-trades) carries over unchanged from Direction B.

---

## 3. Trial budget

- **New hypothesis budget for this direction:** 20 (same size as the original Direction A/B allowance — not enlarged, not shrunk, just extended to the new scope).
- **New cumulative trial cap:** 1042 (1022 + 20).
- **Cumulative trial count continues from 1022** — no counter reset, per the 07-12 document's own §6 rule for revisions.

## 4. Stopping conditions (unchanged from 07-12 §3, restated for this direction)

Research under this direction stops when **any** of:
- **3.1** New hypothesis count reaches 20, or cumulative count reaches 1042.
- **3.2** 3 months elapse from this lock date (deadline: 2026-10-30).
- **3.3** 80 research-hours are logged against this direction.
- **3.4** 3 consecutive hypotheses fail at the same gate — stop and re-examine calibration, data, or framing, same as before.

§3.5 and §4 (decision protocol at stop) of the 07-12 document apply unchanged: stopping is archive-not-continue, and reopening again requires the same honesty this document is trying to model — state plainly what's being reversed and why, don't quietly pick a new number.

---

## 5. Acknowledgment

By locking this document:

1. This reverses a same-day "stop completely" verdict, on direct user instruction, over the locked rule's own documented objection that instrument-only expansion doesn't meet the reopening bar.
2. 18 of 21 known tradeable-universe symbols have zero cost data and are out of scope regardless of this cap increase.
3. None of the 3 in-scope symbols has true multi-day cost measurement yet — trials run before that exists are not go-live evidence.
4. Regime conditioning is deliberately excluded from this direction to avoid compounding methodology changes.
5. The 20-hypothesis budget for this direction is real, not aspirational, same as the original.
