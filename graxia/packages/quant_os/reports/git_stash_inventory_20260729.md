# Git Stash Inventory — 2026-07-29 (P1-10)

**Status: inventory only, per plan instruction. No stash was dropped, popped, or applied.**

13 pre-existing stashes accumulated across prior sessions, never cleaned up:

| Ref | Message |
|---|---|
| @0 | `da0d4303 refactor(quant_os): CodeRabbit review fixes — dedup verify_admin, remove dead code, add traceability` |
| @1 | `86d5193e chore: add .coderabbit.yaml with path_filters for focused review` |
| @2 | `tmp-audit-log-aside` (untitled/WIP stash) |
| @3 | `86c0e61e chore(quant_os): untrack CSV+chroma data, cmt remaining src mods` |
| @4 | `86c0e61e chore(quant_os): untrack CSV+chroma data, cmt remaining src mods` (duplicate message of @3 — different content, needs manual diff to distinguish before any cleanup) |
| @5 | `rewrite` (untitled/WIP stash) |
| @6 | `37bdf27d chore: add CodeRabbit config` |
| @7 | `f64dbbde fix(quant_os): MLPipeline import path for canonical payloads` |
| @8 | `5e8ca1d feat(quant_os): integrate 5 external patterns — jesse, kvrancic, tradeforce, tradingagents, quanttrader` |
| @9 | `866b5a4 feat(quant_os): trading mode config + daily risk limits` |
| @10 | `c23c1aa fix(quant_os): G3.2.3 quote coherence gate` |
| @11 | `2569a6e fix(quant_os): G3.2.2 canonical UTC tick authority` |
| @12 | `5f79e18 fix(quant_os): G3.2.1 time authority fix` |

## Notes

- @3 and @4 share an identical message — this is a red flag that they may contain
  divergent, uncombined work under the same label. Do NOT assume they're duplicates
  of each other without running `git stash show -p stash@{3}` vs `stash@{4}` first.
- @9's message ("trading mode config + daily risk limits") is notable given this
  session's P0-1 finding that `TRADING_MODE` was misconfigured — worth checking
  whether this stash contains relevant, never-applied config work before assuming
  it's safe to discard.
- None of these were dropped, popped, or inspected in detail this session — this is
  a read-only inventory per the plan's explicit instruction ("out of scope for any
  single session... worth a dedicated cleanup pass"). A dedicated pass should diff
  each stash against current HEAD individually before deciding drop vs. cherry-pick.
