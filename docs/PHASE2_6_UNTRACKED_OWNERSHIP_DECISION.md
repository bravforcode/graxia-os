# Phase 2.6 Untracked Ownership Decision

## Inputs Reviewed

- `extraterrestrial-escape/package.json`
- `sites/site-a/package.json`
- directory structure under `extraterrestrial-escape/`
- directory structure under `sites/`
- repo reference scan in `README.md`, `docs`, `backend`, `frontend`, `config`, `scripts`, `.github`

## Findings

### `extraterrestrial-escape/`

- independent Astro app
- own `package.json`
- own `astro.config.mjs`
- own `src/`, `public/`, `tsconfig.json`
- not referenced by current Graxia runtime/product code

### `sites/`

- container for multiple independent Astro apps
- `sites/site-a/` and `sites/site-b/` each have their own `package.json`
- each site has own `astro.config.mjs`, `src/`, `public/`
- not referenced by current Graxia runtime/product code

## Decision

- classify both as local-only site experiments outside current Graxia integration scope
- park both via `.gitignore`
- do not delete local directories
- do not commit their contents into Graxia baseline

## Why this is safe

- current repo baseline had no tracked dirty product files left
- only these untracked subprojects remained
- they are structurally independent and unreferenced by the preserved Graxia app/backend/docs flow
- parking them restores attribution clarity for later integration phases

## Follow-up

- if these Astro projects later become product-owned, import them intentionally in a dedicated phase
- until then, they stay out of Graxia baseline commits
