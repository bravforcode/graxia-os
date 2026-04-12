import type { Meta, StoryObj } from '@storybook/react-vite'

const OverviewPage = () => (
  <div className="max-w-3xl space-y-6 rounded-[28px] border border-[var(--color-border)] bg-[var(--panel-bg)] p-8 shadow-[var(--shadow-xl)]">
    <div>
      <div className="text-[11px] font-semibold uppercase tracking-[0.32em] text-[var(--color-accent-cyan)]">
        Frontend overview
      </div>
      <h1 className="mt-3 text-3xl font-semibold text-[var(--color-text-primary)]">Personal OS Storybook</h1>
      <p className="mt-3 text-sm leading-6 text-[var(--color-text-secondary)]">
        This Storybook documents the shared UI primitives used by the mission-control shell and the operations pages.
      </p>
    </div>

    <section className="space-y-3">
      <h2 className="text-xl font-semibold text-[var(--color-text-primary)]">Current focus</h2>
      <ul className="space-y-2 text-sm leading-6 text-[var(--color-text-secondary)]">
        <li>Production-safe primitives instead of demo widgets</li>
        <li>Keyboard-safe dialogs and action flows</li>
        <li>Reusable notice and empty-state treatments</li>
        <li>Shell-compatible typography, spacing, and HUD styling</li>
      </ul>
    </section>

    <section className="space-y-3">
      <h2 className="text-xl font-semibold text-[var(--color-text-primary)]">Canonical verification</h2>
      <ul className="space-y-2 font-mono text-sm leading-6 text-[var(--color-text-secondary)]">
        <li>bun run lint</li>
        <li>bun run test</li>
        <li>bun run build</li>
        <li>bun run build-storybook</li>
      </ul>
    </section>

    <section className="space-y-3">
      <h2 className="text-xl font-semibold text-[var(--color-text-primary)]">Usage rules</h2>
      <ul className="space-y-2 text-sm leading-6 text-[var(--color-text-secondary)]">
        <li>Prefer shared primitives over page-local one-off markup</li>
        <li>Use Dialog instead of browser confirm or prompt flows</li>
        <li>Keep page-level actions inside PageHeader</li>
        <li>Use NoticeBanner for mutation feedback and EmptyState for empty/loading placeholders</li>
      </ul>
    </section>
  </div>
)

const meta: Meta<typeof OverviewPage> = {
  title: 'Overview/Frontend',
  component: OverviewPage,
  parameters: {
    layout: 'padded',
  },
}

export default meta

type Story = StoryObj<typeof meta>

export const Default: Story = {}
