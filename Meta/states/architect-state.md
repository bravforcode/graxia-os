# Architect State — graxia-os-funnel audit handoff

**Role:** architect
**Date:** 2026-06-05
**Status:** audit complete, awaiting user decision (A/B/C)

## What the user asked
- Read `C:\Users\menum\graxia-os-funnel` end-to-end
- Honest audit, no flattery, no lies (ห้ามอวย ห้ามโกหก)
- Determine if this can make passive income

## What I (architect) actually did
1. Mapped project structure (rtk ls + ctx_tree)
2. Read top-level config: README.md, .env.example, docker-compose.yml, Makefile, package.json
3. Read backend/app/main.py, backend/app/config.py, backend/app/models/funnel.py
4. Read frontend/src/App.tsx, frontend/package.json
5. Dispatched parallel `auditor` subagent for deep analysis (28 files read)
6. Verified the auditor's P0 finding by direct read of .env.graxia and gitleaks-baseline.json
7. Full report saved at: `C:\Users\menum\graxia-os-funnel\Meta\states\audit-report.md` (263 lines)

## Top-level conclusion (architect's read, not the auditor's)
- **Code core is real.** Funnel API (webhook, checkout, delivery token, order model) is production-quality.
- **Project is buried alive.** 5+ competing app trees, 211 archive items, 65 self-congratulatory phase reports.
- **Secrets are leaking right now.** Live Stripe keys + GitHub PAT in `.env.graxia` at root, NOT in .gitignore.
- **No customer can buy anything today** — no domain, no live sales page, no real product, XSS in public page.

## Architecture-level issues
1. **No canonical tree.** `backend/app/main.py` is canonical but the tree has `graxia/packages/revenue_os/`, `core/`, `xiarchitect/`, `04-Archive/` siblings pretending to be live code.
2. **No IaC for funnel deployment.** `docker-compose.yml` has redis+n8n+backend+celery+beat, but no frontend container, no Caddy for the funnel public route, no Supabase wiring.
3. **No public landing-page host.** The funnel public route lives inside React SPA at `/f/:org/:slug` — that means a customer needs (a) the React app running, (b) the org UUID, (c) the slug. There is no entry point for a stranger.
4. **Dual funnel implementations** in `backend/app/models/funnel.py` (canonical) vs `graxia/packages/revenue_os/models.py` (1046 lines, table names `revenue_os_*`). Only one is wired into `main.py`. Phase reports claim both work — only one does.
5. **XSS** in `frontend/src/pages/funnel/PublicProductPage.tsx:205` via `dangerouslySetInnerHTML` on admin-input — multi-tenant future.

## Architect recommendation (A/B/C)
- User wants passive income. A is fastest.
- B is honest middle-ground if user wants to learn.
- C is what has been happening for 6+ months based on the report dates. It produced this repo.

## What I would do next (if user picks B)
1. Rotate exposed Stripe keys + GitHub PAT **today** (non-negotiable regardless of path)
2. Delete `04-Archive/`, `graxia/packages/revenue_os/`, `core/`, `xiarchitect/`, `xiarchitect-vscode/`
3. Move `reports/gitleaks-baseline.json` and `reports/bandit-baseline.json` to a pre-commit hook that actually runs
4. Create a single `infra/` with one docker-compose for the funnel (frontend + backend + postgres + redis + caddy)
5. Create the public landing page as a static HTML in `public/` that the funnel backend serves at `/`
6. Pick a real product (or kill) — the AI placeholder copy in PublicProductPage.tsx is not a product
7. Replace `dangerouslySetInnerHTML` with DOMPurify
8. Bump dependencies (fastapi 0.104 → 0.115+, pydantic 2.5 → 2.9+, stripe 7.8 → 11+, cryptography 41 → 43+)

## Pending questions for the user
- Pick A, B, or C
- If B: which product do you actually want to sell? The funnel is generic — it needs a real offer
- If A: do you have a domain/hosting budget for Gumroad + Stripe Payment Link, or should I suggest free-tier stacks?

## Handoff
Report location: `C:\Users\menum\graxia-os-funnel\Meta\states\audit-report.md`
