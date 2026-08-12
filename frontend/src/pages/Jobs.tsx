import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { Briefcase, ExternalLink, MapPin, RefreshCw, Target, TrendingUp, Workflow } from 'lucide-react'

import { Button } from '@/components/ui/button'
import { EmptyState } from '@/components/ui/empty-state'
import { MetricCard } from '@/components/ui/metric-card'
import { PageHeader } from '@/components/ui/page-header'
import { Panel } from '@/components/ui/panel'
import { StatusPill } from '@/components/ui/status-pill'
import { api, type JobPosting } from '@/lib/api'
import { formatDate } from '@/lib/utils'

function scoreTone(score: number) {
  if (score >= 8) {
    return 'success' as const
  }
  if (score >= 6) {
    return 'warning' as const
  }
  return 'danger' as const
}

export default function Jobs() {
  const [minScore, setMinScore] = useState(7)
  const [status, setStatus] = useState('discovered')

  const { data: jobs, isLoading, refetch } = useQuery({
    queryKey: ['jobs', status, minScore],
    queryFn: () => api.getJobs({ status, min_score: minScore }),
  })

  const { data: stats } = useQuery({
    queryKey: ['jobs-stats'],
    queryFn: api.getJobStats,
  })

  const items = jobs?.items ?? []
  const highFitCount = items.filter((job) => (job.match_score ?? 0) >= 8).length

  return (
    <div className="space-y-6">
      <PageHeader
        eyebrow="Specialized agent"
        title="Job opportunities"
        description="A ranked view of the job discovery pipeline with fit score, skill alignment, and application-stage filters."
        actions={
          <Button variant="secondary" icon={<RefreshCw size={16} />} onClick={() => void refetch()}>
            Refresh
          </Button>
        }
      />

      <section className="grid gap-4 md:grid-cols-2 xl:grid-cols-4">
        <MetricCard
          label="Total jobs"
          value={String(stats?.total_jobs ?? 0)}
          helper="Rows discovered across all statuses."
          icon={Briefcase}
          accent="cyan"
        />
        <MetricCard
          label="Discovered"
          value={String(stats?.by_status?.discovered ?? 0)}
          helper="Jobs waiting for application action."
          icon={Workflow}
          accent="blue"
        />
        <MetricCard
          label="Applied"
          value={String(stats?.by_status?.applied ?? 0)}
          helper="Jobs already converted into active applications."
          icon={Target}
          accent="green"
        />
        <MetricCard
          label="High-fit"
          value={String(highFitCount)}
          helper="Visible jobs scoring 8 or above."
          icon={TrendingUp}
          accent="orange"
        />
      </section>

      <Panel eyebrow="Filters" title="Search controls">
        <div className="grid gap-4 md:grid-cols-2">
          <label className="space-y-2 text-sm text-[var(--color-text-secondary)]">
            <span>Status</span>
            <select value={status} onChange={(event) => setStatus(event.target.value)} className="input-field">
              <option value="discovered">Discovered</option>
              <option value="applied">Applied</option>
              <option value="rejected">Rejected</option>
            </select>
          </label>
          <label className="space-y-2 text-sm text-[var(--color-text-secondary)]">
            <span>Minimum fit score</span>
            <select
              value={minScore}
              onChange={(event) => setMinScore(Number(event.target.value))}
              className="input-field"
            >
              <option value="0">All scores</option>
              <option value="5">5+</option>
              <option value="7">7+</option>
              <option value="8">8+</option>
            </select>
          </label>
        </div>
      </Panel>

      <Panel eyebrow="Ranked queue" title="Job list">
        {isLoading ? (
          <EmptyState message="Loading jobs..." />
        ) : items.length === 0 ? (
          <EmptyState message="No jobs match the current filters." />
        ) : (
          <div className="space-y-4">
            {items.map((job) => (
              <JobCard key={job.id} job={job} />
            ))}
          </div>
        )}
      </Panel>
    </div>
  )
}

function JobCard({ job }: { job: JobPosting }) {
  const score = Number(job.match_score ?? 0)
  const createdAt = job.created_at ?? new Date().toISOString()

  return (
    <article className="rounded-[24px] border border-[var(--color-border)] bg-[var(--color-bg-secondary)]/70 p-5">
      <div className="flex flex-col gap-5 xl:flex-row xl:items-start xl:justify-between">
        <div className="min-w-0 flex-1">
          <div className="flex flex-wrap items-center gap-2">
            <StatusPill label={`${score.toFixed(1)}/10`} tone={scoreTone(score)} />
            <span className="badge">{job.job_type}</span>
            {job.status ? <span className="badge-info">{job.status}</span> : null}
            {job.source_platform ? <span className="badge">{job.source_platform}</span> : null}
          </div>

          <h3 className="mt-4 text-xl font-semibold text-[var(--color-text-primary)]">{job.title}</h3>
          <p className="mt-2 text-sm text-[var(--color-text-secondary)]">{job.company || 'Unknown company'}</p>

          <div className="mt-4 flex flex-wrap items-center gap-4 text-sm text-[var(--color-text-tertiary)]">
            {job.location ? (
              <span className="inline-flex items-center gap-1">
                <MapPin size={14} />
                {job.location}
              </span>
            ) : null}
            <span>{formatDate(createdAt)}</span>
            {job.employment_type ? <span>{job.employment_type}</span> : null}
          </div>

          {job.fit_summary ? (
            <div className="mt-4 rounded-2xl border border-[var(--color-border)] bg-[var(--color-bg-primary)]/60 p-4 text-sm leading-6 text-[var(--color-text-secondary)]">
              {job.fit_summary}
            </div>
          ) : null}

          {job.matched_skills?.length ? (
            <div className="mt-4">
              <div className="text-[11px] font-semibold uppercase tracking-[0.24em] text-[var(--color-text-tertiary)]">
                Matched skills
              </div>
              <div className="mt-2 flex flex-wrap gap-2">
                {job.matched_skills.map((skill) => (
                  <span key={skill} className="badge-success">
                    {skill}
                  </span>
                ))}
              </div>
            </div>
          ) : null}

          {job.skill_gap_list?.length ? (
            <div className="mt-4">
              <div className="text-[11px] font-semibold uppercase tracking-[0.24em] text-[var(--color-text-tertiary)]">
                Skill gaps
              </div>
              <div className="mt-2 flex flex-wrap gap-2">
                {job.skill_gap_list.map((skill) => (
                  <span key={skill} className="badge-danger">
                    {skill}
                  </span>
                ))}
              </div>
            </div>
          ) : null}
        </div>

        {job.source_url ? (
          <a
            href={job.source_url}
            target="_blank"
            rel="noopener noreferrer"
            className="inline-flex items-center justify-center gap-2 rounded-xl border border-[var(--color-border)] bg-[var(--color-bg-tertiary)] px-4 py-2.5 text-sm font-medium text-[var(--color-text-primary)] transition hover:border-[var(--color-accent-cyan)]"
          >
            <ExternalLink size={16} />
            View job
          </a>
        ) : null}
      </div>
    </article>
  )
}
