import type { ReactNode } from 'react'

type AuthShellProps = {
  title: string
  subtitle: string
  children: ReactNode
}

export function AuthShell({ title, subtitle, children }: AuthShellProps) {
  return (
    <div className="relative min-h-screen overflow-hidden bg-[var(--color-bg-primary)] px-4 py-10">
      <a href="#auth-content" className="skip-link">
        Skip to authentication form
      </a>
      <div className="pointer-events-none absolute inset-0 bg-[radial-gradient(circle_at_top_left,rgba(0,212,255,0.14),transparent_30%),radial-gradient(circle_at_bottom_right,rgba(0,255,157,0.12),transparent_28%)]" />
      <main id="auth-content" className="relative mx-auto flex min-h-[calc(100vh-5rem)] max-w-6xl items-center justify-center">
        <div className="grid w-full gap-8 lg:grid-cols-[1.1fr_0.9fr]">
          <aside className="hidden rounded-[32px] border border-[var(--color-border)] bg-[var(--panel-bg)] p-10 shadow-[var(--shadow-xl)] lg:block">
            <div className="inline-flex rounded-full border border-[rgba(0,212,255,0.25)] bg-[rgba(0,212,255,0.08)] px-4 py-1 text-[11px] font-semibold uppercase tracking-[0.32em] text-[var(--color-accent-cyan)]">
              Personal OS
            </div>
            <h2 className="mt-8 max-w-xl text-5xl font-semibold leading-tight text-[var(--color-text-primary)]">
              Mission control for autonomous opportunity execution.
            </h2>
            <p className="mt-5 max-w-xl text-base leading-7 text-[var(--color-text-secondary)]">
              Track opportunities, jobs, drafts, costs, and agent health from a single operating surface built for
              deliberate action.
            </p>
            <div className="mt-10 grid gap-4 md:grid-cols-3">
              {[
                ['Realtime pulse', 'Agent activity, queue state, and runtime mode in one feed.'],
                ['Decision lane', 'High-signal approvals and drafts surfaced without noise.'],
                ['Budget guardrails', 'Cost, fallback, and degraded-mode visibility built into the shell.'],
              ].map(([heading, body]) => (
                <div key={heading} className="rounded-[24px] border border-[var(--color-border)] bg-[var(--color-bg-secondary)]/80 p-5">
                  <div className="text-sm font-semibold text-[var(--color-text-primary)]">{heading}</div>
                  <div className="mt-2 text-sm leading-6 text-[var(--color-text-secondary)]">{body}</div>
                </div>
              ))}
            </div>
          </aside>
          <section aria-labelledby="auth-shell-title" className="rounded-[32px] border border-[var(--color-border)] bg-[var(--panel-bg)] p-6 shadow-[var(--shadow-xl)] backdrop-blur-xl sm:p-8">
            <div className="mb-8">
              <div className="text-[11px] font-semibold uppercase tracking-[0.32em] text-[var(--color-accent-cyan)]">
                Secure access
              </div>
              <h1 id="auth-shell-title" className="mt-3 text-3xl font-semibold tracking-tight text-[var(--color-text-primary)]">
                {title}
              </h1>
              <p className="mt-3 text-sm leading-6 text-[var(--color-text-secondary)]">{subtitle}</p>
            </div>
            {children}
          </section>
        </div>
      </main>
    </div>
  )
}
