# Personal OS — Frontend

Canonical React SPA for the Personal OS control plane.

## Verified Commands

```bash
bun install
bun run lint
bun run test
bun run build
bun run test:e2e
bun run build-storybook
bun run preview
```

At the time of this update:

- lint passes
- Vitest passes with `33` tests, including automated axe-based accessibility checks
- Playwright passes with `3` browser E2E flows and auto-builds the current production bundle before preview
- production build passes
- Storybook build passes for the shared UI primitives
- the main production JS chunk remains below the project target at roughly `418 kB`

## Stack

- React 18
- TypeScript
- Vite
- Tailwind CSS
- React Router
- TanStack Query
- Zustand
- Axios
- Lucide React
- date-fns

## Structure

```text
src/
├── components/
│   ├── ui/              # Shared primitives used across pages
│   ├── Layout.tsx       # Mission-control shell
│   ├── AuthShell.tsx    # Login/register shell
│   └── ProtectedRoute.tsx
├── contexts/            # Auth provider
├── hooks/               # App hooks including useAgentStream
├── lib/                 # API client + utilities
├── pages/               # Route surfaces
├── store/               # Zustand UI state
├── App.tsx
├── main.tsx
└── index.css
```

## Current UI Surface

- Auth: login and register
- Shell: sidebar navigation, runtime badges, theme toggle, skip link, refresh path
- Operations pages: dashboard, opportunities, drafts, jobs, contacts, inbox, tasks, costs, metrics, event bus, settings
- Shared modal/notice/empty-state primitives reused across the operations pages
- Storybook coverage for Button, Dialog, NoticeBanner, EmptyState, MetricCard, PageHeader, StatusPill, and an overview page

## Accessibility Baseline

- keyboard-safe `Dialog` primitive with focus trapping and `Escape` close
- `ProtectedRoute` loading and redirect states covered by tests
- skip link and main-content landmark in the app shell
- status/alert semantics on banners and empty states
- automated axe checks for login, register, protected-route loading state, dialog, shell baseline, dashboard, opportunities, drafts, jobs, contacts, inbox, tasks, metrics, costs, event bus, and settings

See [COMPONENT_GUIDE.md](C:/brav%20os/frontend/COMPONENT_GUIDE.md) for the current primitives and usage rules.

## API Integration

All frontend API calls go through `src/lib/api.ts`, which targets `/api/v1` via Vite proxying in local development.

## Design Direction

- A+C hybrid visual system: Claude Code dark precision + mission-control HUD
- `IBM Plex Sans` for body copy, `Space Grotesk` for display, `JetBrains Mono` for telemetry
- cyan / lime / blue accents over deep slate surfaces
- glass-panel and HUD treatment without relying on generic purple-on-white defaults
