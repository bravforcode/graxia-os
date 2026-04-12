import { useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { AlertTriangle, CheckSquare, Clock, RefreshCw, Workflow } from 'lucide-react'

import { Button } from '@/components/ui/Button'
import { EmptyState } from '@/components/ui/EmptyState'
import { MetricCard } from '@/components/ui/MetricCard'
import { PageHeader } from '@/components/ui/PageHeader'
import { Panel } from '@/components/ui/Panel'
import { StatusPill } from '@/components/ui/StatusPill'
import { api, type AssistantTask } from '@/lib/api'
import { formatDate } from '@/lib/utils'

function statusTone(status: string) {
  switch (status) {
    case 'completed':
      return 'success' as const
    case 'in_progress':
      return 'info' as const
    case 'pending':
      return 'warning' as const
    default:
      return 'neutral' as const
  }
}

function priorityTone(priority: number) {
  if (priority >= 8) {
    return 'danger' as const
  }
  if (priority >= 6) {
    return 'warning' as const
  }
  return 'info' as const
}

function isOverdue(dueDate?: string) {
  return Boolean(dueDate) && new Date(dueDate as string) < new Date()
}

function isDueSoon(dueDate?: string) {
  if (!dueDate) {
    return false
  }
  const due = new Date(dueDate)
  const now = new Date()
  const diff = due.getTime() - now.getTime()
  const days = diff / (1000 * 60 * 60 * 24)
  return days <= 1 && days > 0
}

export default function Tasks() {
  const queryClient = useQueryClient()
  const [status, setStatus] = useState('pending')
  const [minPriority, setMinPriority] = useState(0)

  const { data: tasks, isLoading, refetch } = useQuery({
    queryKey: ['tasks', status, minPriority],
    queryFn: () => api.getTasks({ status, priority_min: minPriority }),
  })

  const { data: stats } = useQuery({
    queryKey: ['tasks-stats'],
    queryFn: api.getTaskStats,
  })

  const startMutation = useMutation({
    mutationFn: (taskId: string) => api.updateTask(taskId, { status: 'in_progress' }),
    onSuccess: async () => {
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: ['tasks'] }),
        queryClient.invalidateQueries({ queryKey: ['tasks-stats'] }),
        refetch(),
      ])
    },
  })

  const completeMutation = useMutation({
    mutationFn: (taskId: string) => api.completeTask(taskId),
    onSuccess: async () => {
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: ['tasks'] }),
        queryClient.invalidateQueries({ queryKey: ['tasks-stats'] }),
        refetch(),
      ])
    },
  })

  const items = tasks?.items ?? []

  return (
    <div className="space-y-6">
      <PageHeader
        eyebrow="Execution"
        title="Tasks and reminders"
        description="Track the assistant task queue with only the real state transitions exposed: start and complete."
        actions={
          <Button variant="secondary" icon={<RefreshCw size={16} />} onClick={() => void refetch()}>
            Refresh
          </Button>
        }
      />

      <section className="grid gap-4 md:grid-cols-2 xl:grid-cols-4">
        <MetricCard
          label="Total tasks"
          value={String(stats?.total_tasks ?? 0)}
          helper="Known tasks in the workspace."
          icon={CheckSquare}
          accent="cyan"
        />
        <MetricCard
          label="Pending"
          value={String(stats?.by_status?.pending ?? 0)}
          helper="Tasks waiting for work to begin."
          icon={Workflow}
          accent="blue"
        />
        <MetricCard
          label="Overdue"
          value={String(stats?.overdue_count ?? 0)}
          helper="Tasks whose due date is already in the past."
          icon={AlertTriangle}
          accent="orange"
        />
        <MetricCard
          label="Due today"
          value={String(stats?.due_today_count ?? 0)}
          helper="Tasks due inside the current day."
          icon={Clock}
          accent="green"
        />
      </section>

      <Panel eyebrow="Filters" title="Queue controls">
        <div className="grid gap-4 md:grid-cols-2">
          <label className="space-y-2 text-sm text-[var(--color-text-secondary)]">
            <span>Status</span>
            <select value={status} onChange={(event) => setStatus(event.target.value)} className="input-field">
              <option value="pending">Pending</option>
              <option value="in_progress">In progress</option>
              <option value="completed">Completed</option>
              <option value="cancelled">Cancelled</option>
            </select>
          </label>
          <label className="space-y-2 text-sm text-[var(--color-text-secondary)]">
            <span>Minimum priority</span>
            <select
              value={minPriority}
              onChange={(event) => setMinPriority(Number(event.target.value))}
              className="input-field"
            >
              <option value="0">All priorities</option>
              <option value="5">5+</option>
              <option value="7">7+</option>
              <option value="9">9+</option>
            </select>
          </label>
        </div>
      </Panel>

      <Panel eyebrow="Task queue" title="Task list">
        {isLoading ? (
          <EmptyState message="Loading tasks..." />
        ) : items.length === 0 ? (
          <EmptyState message="No tasks match the current filters." />
        ) : (
          <div className="space-y-4">
            {items.map((task) => (
              <TaskCard
                key={task.id}
                task={task}
                starting={startMutation.isPending && startMutation.variables === task.id}
                completing={completeMutation.isPending && completeMutation.variables === task.id}
                onStart={() => startMutation.mutate(task.id)}
                onComplete={() => completeMutation.mutate(task.id)}
              />
            ))}
          </div>
        )}
      </Panel>
    </div>
  )
}

function TaskCard({
  task,
  starting,
  completing,
  onStart,
  onComplete,
}: {
  task: AssistantTask
  starting: boolean
  completing: boolean
  onStart: () => void
  onComplete: () => void
}) {
  const overdue = isOverdue(task.due_date)
  const dueSoon = isDueSoon(task.due_date)

  return (
    <article className="rounded-[24px] border border-[var(--color-border)] bg-[var(--color-bg-secondary)]/70 p-5">
      <div className="flex flex-col gap-5 xl:flex-row xl:items-start xl:justify-between">
        <div className="min-w-0 flex-1">
          <div className="flex flex-wrap items-center gap-2">
            <StatusPill label={`Priority ${task.priority}`} tone={priorityTone(task.priority)} />
            <StatusPill label={task.status} tone={statusTone(task.status)} />
            {task.task_type ? <span className="badge">{task.task_type}</span> : null}
            {overdue ? <span className="badge-danger">Overdue</span> : null}
            {!overdue && dueSoon ? <span className="badge-warning">Due soon</span> : null}
          </div>

          <h3 className="mt-4 text-xl font-semibold text-[var(--color-text-primary)]">{task.title}</h3>
          {task.description ? (
            <p className="mt-3 text-sm leading-6 text-[var(--color-text-secondary)]">{task.description}</p>
          ) : null}

          <div className="mt-4 flex flex-wrap items-center gap-4 text-sm text-[var(--color-text-tertiary)]">
            {task.due_date ? (
              <span>{overdue ? 'Due' : 'Deadline'} {formatDate(task.due_date)}</span>
            ) : null}
            {task.related_entity_type ? <span>Related to {task.related_entity_type}</span> : null}
            {task.completed_at ? <span>Completed {formatDate(task.completed_at)}</span> : null}
          </div>
        </div>

        <div className="flex flex-wrap gap-3 xl:w-auto xl:flex-col">
          {task.status === 'pending' ? (
            <Button size="sm" variant="secondary" loading={starting} onClick={onStart}>
              Start
            </Button>
          ) : null}
          {task.status === 'pending' || task.status === 'in_progress' ? (
            <Button size="sm" loading={completing} onClick={onComplete}>
              Complete
            </Button>
          ) : null}
          {task.status === 'completed' ? <StatusPill label="Done" tone="success" /> : null}
        </div>
      </div>
    </article>
  )
}
