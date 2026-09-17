import { useQuery } from '@tanstack/react-query'
import { useOutletContext } from 'react-router-dom'
import { BrainCircuit, Database, RefreshCw, ShieldCheck, Workflow } from 'lucide-react'

import { Button } from '@/components/ui/button'
import { MetricCard } from '@/components/ui/metric-card'
import { PageHeader } from '@/components/ui/page-header'
import { Panel } from '@/components/ui/panel'
import { StatusPill } from '@/components/ui/status-pill'
import type { AppShellContext } from '@/components/Layout'
import { api } from '@/lib/api'

function formatTimeSince(seconds: number | null) {
  if (!seconds) return 'Never'
  if (seconds < 60) return `${seconds}s ago`
  if (seconds < 3600) return `${Math.floor(seconds / 60)}m ago`
  if (seconds < 86400) return `${Math.floor(seconds / 3600)}h ago`
  return `${Math.floor(seconds / 86400)}d ago`
}

export default function Settings() {
  const { health, refreshRuntime } = useOutletContext<AppShellContext>()

  const { data: scraperSummary, refetch, isFetching } = useQuery({
    queryKey: ['scrapers', 'health'],
    queryFn: api.getScraperHealth,
    refetchInterval: 30000,
  })

  const scrapers = scraperSummary?.scrapers ?? []

  return (
    <div className="space-y-6">
      <PageHeader
        eyebrow="Runtime"
        title="System settings"
        description="Operational health, scraper fleet posture, and active runtime safeguards across the backend control plane."
        actions={
          <>
            <Button variant="secondary" icon={<RefreshCw size={16} />} loading={isFetching} onClick={() => void refetch()}>
              Refresh scrapers
            </Button>
            <Button variant="secondary" icon={<Workflow size={16} />} onClick={() => void refreshRuntime()}>
              Refresh runtime
            </Button>
          </>
        }
      />

      <section className="grid gap-4 md:grid-cols-2 xl:grid-cols-4">
        <MetricCard
          label="Runtime mode"
          value={health?.readiness.mode ?? 'unknown'}
          helper="Current readiness envelope."
          icon={ShieldCheck}
          accent="cyan"
        />
        <MetricCard
          label="LLM posture"
          value={health?.llm_degraded ? 'Degraded' : 'Healthy'}
          helper={health?.llm_cost_paused ? 'Cost pause active.' : 'Cost guardrails clear.'}
          icon={BrainCircuit}
          accent={health?.llm_degraded ? 'orange' : 'green'}
        />
        <MetricCard
          label="Scrapers healthy"
          value={`${health?.scraper_summary.healthy ?? 0}/${health?.scraper_summary.total ?? 0}`}
          helper="Healthy scraper count."
          icon={Database}
          accent="blue"
        />
        <MetricCard
          label="API calls today"
          value={String(health?.gemini_calls_today ?? 0)}
          helper="Daily backend LLM activity."
          icon={Workflow}
          accent="orange"
        />
      </section>

      <Panel eyebrow="Runtime state" title="System health">
        <div className="grid gap-4 lg:grid-cols-[minmax(0,0.9fr)_minmax(0,1.1fr)]">
          <div className="space-y-4">
            <div className="panel-muted p-4">
              <div className="flex items-center justify-between">
                <span className="text-sm text-[var(--color-text-secondary)]">System status</span>
                <StatusPill
                  label={health?.status ?? 'unknown'}
                  tone={health?.status === 'ok' || health?.status === 'full' ? 'success' : 'warning'}
                />
              </div>
              <p className="mt-4 text-sm leading-6 text-[var(--color-text-secondary)]">
                {health?.readiness.issues?.length
                  ? 'The runtime is operating with active readiness issues that should be resolved before full automation.'
                  : 'No active readiness issues detected.'}
              </p>
            </div>

            <div className="panel-muted p-4">
              <div className="text-xs uppercase tracking-[0.22em] text-[var(--color-text-tertiary)]">Frontend origin</div>
              <div className="mt-2 text-sm text-[var(--color-text-primary)]">{window.location.origin}</div>
            </div>

            <div className="panel-muted p-4">
              <div className="text-xs uppercase tracking-[0.22em] text-[var(--color-text-tertiary)]">Budget controls</div>
              <div className="mt-2 flex flex-wrap gap-2">
                <StatusPill label={health?.llm_cost_paused ? 'Paused' : 'Open'} tone={health?.llm_cost_paused ? 'danger' : 'success'} />
                <StatusPill label={health?.llm_degraded ? 'Fallback' : 'Primary'} tone={health?.llm_degraded ? 'warning' : 'info'} />
              </div>
            </div>
          </div>

          <div className="panel-muted p-4">
            <div className="text-xs uppercase tracking-[0.22em] text-[var(--color-text-tertiary)]">Readiness issues</div>
            <div className="mt-4 space-y-3">
              {health?.readiness.issues?.length ? (
                health.readiness.issues.map((issue) => (
                  <div
                    key={issue}
                    className="rounded-2xl border border-[rgba(255,174,87,0.2)] bg-[rgba(255,174,87,0.08)] px-4 py-3 text-sm leading-6 text-[var(--color-text-secondary)]"
                  >
                    {issue}
                  </div>
                ))
              ) : (
                <div className="rounded-2xl border border-dashed border-[var(--color-border)] px-4 py-8 text-center text-sm text-[var(--color-text-tertiary)]">
                  Runtime is clear. No readiness issues reported.
                </div>
              )}
            </div>
          </div>
        </div>
      </Panel>

      <Panel eyebrow="Scraper fleet" title="Collector health">
        <div className="space-y-4">
          {scrapers.length ? (
            scrapers.map((scraper) => (
              <article
                key={scraper.name}
                className="rounded-[24px] border border-[var(--color-border)] bg-[var(--color-bg-secondary)]/70 p-5"
              >
                <div className="flex flex-col gap-4 lg:flex-row lg:items-center lg:justify-between">
                  <div>
                    <div className="flex flex-wrap items-center gap-2">
                      <h3 className="text-lg font-semibold text-[var(--color-text-primary)]">{scraper.name}</h3>
                      <StatusPill
                        label={scraper.status}
                        tone={
                          scraper.status === 'success'
                            ? 'success'
                            : scraper.status === 'muted'
                              ? 'neutral'
                              : 'danger'
                        }
                      />
                    </div>
                    <div className="mt-3 grid gap-3 text-sm text-[var(--color-text-secondary)] md:grid-cols-3">
                      <span>Last run {formatTimeSince(scraper.time_since_run_seconds)}</span>
                      <span>Avg results {scraper.results_count}</span>
                      <span>{scraper.is_healthy ? 'Collector healthy' : 'Collector requires attention'}</span>
                    </div>
                    {scraper.error_message ? (
                      <div className="mt-3 rounded-2xl border border-[rgba(239,95,86,0.2)] bg-[rgba(239,95,86,0.08)] px-4 py-3 text-sm text-[var(--color-accent-red)]">
                        {scraper.error_message}
                      </div>
                    ) : null}
                  </div>
                </div>
              </article>
            ))
          ) : (
            <div className="rounded-[24px] border border-dashed border-[var(--color-border)] px-4 py-8 text-center text-sm text-[var(--color-text-tertiary)]">
              No scraper health data is available yet.
            </div>
          )}
        </div>
      </Panel>
    </div>
  )
}
