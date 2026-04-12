# Frontend Component Guide

This file describes the shared primitives that are currently treated as the canonical frontend building blocks.

## Core Primitives

- `Button`
  - default button type is `button`
  - use `type="submit"` explicitly inside forms
  - supports `primary`, `secondary`, `ghost`, and `danger`
- `Dialog`
  - traps focus while open
  - closes on `Escape`
  - restores focus when dismissed
  - use this instead of browser `confirm()` or `prompt()`
- `NoticeBanner`
  - use for action feedback after mutations
  - danger banners render as alerts; non-danger banners render as polite status updates
- `EmptyState`
  - use for empty and loading placeholders inside data panels
- `PageHeader`
  - standardizes eyebrow, title, description, and top-level page actions
- `MetricCard`
  - use for top-line summaries above dense data sections

## Shell Rules

- `Layout.tsx` owns navigation, runtime badges, theme toggle, and the `main` landmark
- every app route should render inside the shell unless it is part of the auth surface
- keep page-level actions in `PageHeader.actions`
- prefer `Panel` + shared primitives over one-off inline card markup

## Accessibility Rules

- prefer semantic controls over clickable `div`s
- give destructive/failed mutation feedback through `NoticeBanner`
- all modal flows should use `Dialog`
- preserve keyboard access for navigation and action flows
- when adding a new app surface, verify it still works with:
  - `bun run lint`
  - `bun run test`
  - `bun run build`

## Current Regression Coverage

- auth session restoration
- protected-route loading, redirect, and authenticated states
- button primitive behavior
- dialog rendering, close, escape handling, and focus trap
- `useAgentStream` fallback polling behavior
- automated axe checks for auth pages, protected-route loading, dialog, shell baseline, dashboard, opportunities, drafts, jobs, contacts, inbox, tasks, metrics, costs, event bus, and settings

## Storybook

- run `bun run storybook` for local component review
- run `bun run build-storybook` to verify the documentation build
- current story coverage includes the overview page plus Button, Dialog, NoticeBanner, EmptyState, MetricCard, PageHeader, and StatusPill
