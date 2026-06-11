import { useState } from 'react'
import { Link, Outlet, useLocation } from 'react-router-dom'
import {
  Activity,
  BarChart3,
  Briefcase,
  CheckSquare,
  DollarSign,
  FileText,
  LogOut,
  Mail,
  Menu,
  RefreshCw,
  Settings,
  ShieldCheck,
  ShoppingBag,
  Target,
  UserPlus,
  Users,
  X,
} from 'lucide-react'

import { Button } from '@/components/ui/Button'
import { StatusPill } from '@/components/ui/StatusPill'
import { ThemeToggle } from '@/components/ui/ThemeToggle'
import { useAuth } from '@/contexts/AuthContext'
import { useAgentStream, type AgentConnectionState, type AgentFeedItem, type AgentTransport } from '@/hooks/useAgentStream'
import type { EventStats, SystemHealth } from '@/lib/api'
import { cn, formatNumber } from '@/lib/utils'
import { useUIStore } from '@/store/uiStore'
import { CommandBar } from './layout/CommandBar'

export type AppShellContext = {
  connectionState: AgentConnectionState
  transport: AgentTransport
  health: SystemHealth | null
  stats: EventStats | null
  feed: AgentFeedItem[]
  refreshRuntime: () => Promise<void>
}

const navItems = [
  { path: '/', label: 'Dashboard', icon: BarChart3 },
  { path: '/approvals', label: 'Approvals', icon: ShieldCheck },
  { path: '/opportunities', label: 'Opportunities', icon: Target },
  { path: '/jobs', label: 'Jobs', icon: Briefcase },
  { path: '/emails', label: 'Inbox', icon: Mail },
  { path: '/tasks', label: 'Tasks', icon: CheckSquare },
  { path: '/drafts', label: 'Drafts', icon: FileText },
  { path: '/products', label: 'Funnels', icon: ShoppingBag },
  { path: '/leads', label: 'Leads', icon: UserPlus },
  { path: '/contacts', label: 'Contacts', icon: Users },
  { path: '/costs', label: 'Costs', icon: DollarSign },
  { path: '/metrics', label: 'Metrics', icon: BarChart3 },
  { path: '/settings', label: 'Settings', icon: Settings },
]

// Developer/system-level routes — not shown in primary nav
const systemNavItems = [
  { path: '/event-bus', label: 'Event Bus', icon: Activity },
]

function isActivePath(pathname: string, path: string) {
  return path === '/' ? pathname === path : pathname === path || pathname.startsWith(`${path}/`)
}

function runtimeTone(connectionState: AgentConnectionState, health: SystemHealth | null) {
  if (connectionState === 'offline') {
    return 'danger' as const
  }
  if (!health || health.llm_degraded || health.readiness.mode !== 'full') {
    return 'warning' as const
  }
  return 'success' as const
}

export default function Layout() {
  const location = useLocation()
  const { user, logout } = useAuth()
  const sidebarOpen = useUIStore((state) => state.sidebarOpen)
  const toggleSidebar = useUIStore((state) => state.toggleSidebar)
  const closeSidebar = useUIStore((state) => state.closeSidebar)
  const { connectionState, transport, health, stats, feed, refresh } = useAgentStream()
  const [refreshing, setRefreshing] = useState(false)

  const shellContext: AppShellContext = {
    connectionState,
    transport,
    health,
    stats,
    feed,
    refreshRuntime: refresh,
  }

  async function handleRefresh() {
    setRefreshing(true)
    try {
      await refresh()
    } finally {
      setRefreshing(false)
    }
  }

  const readinessLabel = health?.readiness.mode ?? 'booting'
  const runtimeLabel =
    connectionState === 'live'
      ? 'Live'
      : connectionState === 'fallback'
        ? 'Fallback'
        : connectionState === 'offline'
          ? 'Offline'
          : 'Connecting'

  return (
    <div className="relative min-h-screen overflow-hidden surface-grid">
      <CommandBar />
      <a href="#main-content" className="skip-link">
        Skip to main content
      </a>
      <div className="pointer-events-none absolute inset-0 bg-[radial-gradient(circle_at_top_left,rgba(88,224,255,0.12),transparent_26%),radial-gradient(circle_at_bottom_right,rgba(90,123,255,0.12),transparent_28%)]" />
      <div className="relative flex min-h-screen">
        <div
          className={cn(
            'fixed inset-0 z-40 bg-slate-950/60 backdrop-blur-sm transition-opacity lg:hidden',
            sidebarOpen ? 'opacity-100' : 'pointer-events-none opacity-0'
          )}
          onClick={closeSidebar}
          aria-hidden="true"
        />

        <aside
          id="app-navigation"
          aria-label="Primary navigation"
          className={cn(
            'fixed inset-y-4 left-4 z-50 flex w-[18rem] flex-col rounded-[30px] border border-[var(--color-border)] bg-[var(--panel-bg)] p-4 shadow-[var(--shadow-xl)] backdrop-blur-xl transition-transform duration-200 lg:translate-x-0',
            sidebarOpen ? 'translate-x-0' : '-translate-x-[120%]'
          )}
        >
          <div className="flex items-center justify-between gap-3 border-b border-[var(--color-border)] px-2 pb-4">
            <div className="flex items-center gap-3">
              <div className="relative flex h-11 w-11 items-center justify-center rounded-2xl border border-[rgba(88,224,255,0.3)] bg-[rgba(88,224,255,0.08)]">
                <div className="absolute inset-1 rounded-xl border border-[rgba(125,252,176,0.24)]" />
                <span className="relative font-mono text-sm font-semibold tracking-[0.24em] text-[var(--color-accent-cyan)]">
                  POS
                </span>
              </div>
              <div>
                <div className="text-sm font-semibold uppercase tracking-[0.28em] text-[var(--color-accent-cyan)]">
                  Personal OS
                </div>
                <div className="mt-1 text-xs text-[var(--color-text-tertiary)]">Mission control shell</div>
              </div>
            </div>
            <button
              type="button"
              onClick={closeSidebar}
              className="rounded-xl p-2 text-[var(--color-text-secondary)] transition hover:bg-[var(--color-bg-tertiary)] hover:text-[var(--color-text-primary)] lg:hidden"
              aria-label="Close navigation"
            >
              <X size={18} />
            </button>
          </div>

          <nav aria-label="Sidebar" className="mt-5 flex-1 space-y-1 overflow-y-auto px-1">
            {navItems.map((item) => {
              const Icon = item.icon
              const active = isActivePath(location.pathname, item.path)

              return (
                <Link
                  key={item.path}
                  to={item.path}
                  onClick={closeSidebar}
                  className={cn(
                    'group flex items-center gap-3 rounded-2xl px-3 py-3 text-sm font-medium transition duration-150',
                    active
                      ? 'bg-[rgba(88,224,255,0.12)] text-[var(--color-text-primary)]'
                      : 'text-[var(--color-text-secondary)] hover:bg-[var(--color-bg-tertiary)] hover:text-[var(--color-text-primary)]'
                  )}
                >
                  <Icon
                    size={18}
                    className={active ? 'text-[var(--color-accent-cyan)]' : 'text-[var(--color-text-tertiary)]'}
                  />
                  <span className="flex-1">{item.label}</span>
                  <span
                    className={cn(
                      'h-2 w-2 rounded-full transition',
                      active ? 'bg-[var(--color-accent-lime)]' : 'bg-transparent'
                    )}
                  />
                </Link>
              )
            })}
          </nav>

          <nav aria-label="System" className="mt-2 px-1">
            <p className="mb-1 px-3 text-[10px] font-semibold uppercase tracking-[0.2em] text-[var(--color-text-tertiary)]">
              System
            </p>
            {systemNavItems.map((item) => {
              const Icon = item.icon
              const active = isActivePath(location.pathname, item.path)
              return (
                <Link
                  key={item.path}
                  to={item.path}
                  onClick={closeSidebar}
                  className={cn(
                    'group flex items-center gap-3 rounded-2xl px-3 py-2 text-xs font-medium transition duration-150',
                    active
                      ? 'bg-[rgba(88,224,255,0.12)] text-[var(--color-text-primary)]'
                      : 'text-[var(--color-text-tertiary)] hover:bg-[var(--color-bg-tertiary)] hover:text-[var(--color-text-secondary)]'
                  )}
                >
                  <Icon size={15} />
                  <span>{item.label}</span>
                </Link>
              )
            })}
          </nav>

          <div className="mt-4 space-y-3 border-t border-[var(--color-border)] px-2 pt-4">
            <div className="panel-muted p-4">
              <div className="mb-3 flex items-center justify-between">
                <div>
                  <div className="text-[11px] font-semibold uppercase tracking-[0.28em] text-[var(--color-text-tertiary)]">
                    Runtime
                  </div>
                  <div className="mt-1 text-sm font-semibold text-[var(--color-text-primary)]">Ops status</div>
                </div>
                <StatusPill label={runtimeLabel} tone={runtimeTone(connectionState, health)} pulse={connectionState !== 'offline'} />
              </div>
              <div className="space-y-3 text-sm">
                <div className="flex items-center justify-between text-[var(--color-text-secondary)]">
                  <span>Mode</span>
                  <span className="font-medium uppercase tracking-[0.18em] text-[var(--color-text-primary)]">
                    {readinessLabel}
                  </span>
                </div>
                <div className="flex items-center justify-between text-[var(--color-text-secondary)]">
                  <span>Transport</span>
                  <span className="font-medium uppercase tracking-[0.18em] text-[var(--color-text-primary)]">
                    {transport}
                  </span>
                </div>
                <div className="flex items-center justify-between text-[var(--color-text-secondary)]">
                  <span>Total events</span>
                  <span className="font-mono text-[var(--color-text-primary)]">
                    {formatNumber(stats?.total_events ?? 0)}
                  </span>
                </div>
              </div>
            </div>

            <div className="panel-muted p-4">
              <div className="text-[11px] font-semibold uppercase tracking-[0.28em] text-[var(--color-text-tertiary)]">
                Operator
              </div>
              <div className="mt-2 truncate text-sm font-medium text-[var(--color-text-primary)]">{user?.email}</div>
              <div className="mt-1 text-sm text-[var(--color-text-secondary)]">
                LLM {health?.llm_degraded ? 'fallback mode' : 'primary mode'}
              </div>
            </div>
          </div>
        </aside>

        <div className="flex min-h-screen flex-1 flex-col lg:pl-[21rem]">
          <header className="sticky top-0 z-30 px-4 pb-4 pt-4 sm:px-6 lg:px-8">
            <div className="rounded-[28px] border border-[var(--color-border)] bg-[var(--color-bg-elevated)] px-4 py-4 shadow-[var(--shadow-lg)] backdrop-blur-xl">
              <div className="flex flex-col gap-4 xl:flex-row xl:items-center xl:justify-between">
                <div className="flex items-center gap-3">
                  <button
                    type="button"
                    onClick={toggleSidebar}
                    aria-controls="app-navigation"
                    aria-expanded={sidebarOpen}
                    className="rounded-2xl border border-[var(--color-border)] bg-[var(--color-bg-secondary)]/70 p-3 text-[var(--color-text-primary)] transition hover:border-[rgba(88,224,255,0.3)] lg:hidden"
                    aria-label="Open navigation"
                  >
                    <Menu size={18} />
                  </button>
                  <div>
                    <div className="text-[11px] font-semibold uppercase tracking-[0.3em] text-[var(--color-accent-cyan)]">
                      Autonomous Opportunity Engine
                    </div>
                    <div className="mt-2 text-2xl font-semibold text-[var(--color-text-primary)]">
                      Enterprise execution surface
                    </div>
                  </div>
                </div>

                <div className="flex flex-wrap items-center gap-2">
                  <StatusPill label={runtimeLabel} tone={runtimeTone(connectionState, health)} pulse={connectionState !== 'offline'} />
                  <StatusPill
                    label={transport === 'websocket' ? 'WebSocket' : 'Polling'}
                    tone={transport === 'websocket' ? 'info' : 'neutral'}
                  />
                  <StatusPill
                    label={health?.llm_cost_paused ? 'Budget pause' : 'Budget clear'}
                    tone={health?.llm_cost_paused ? 'danger' : 'success'}
                  />
                  <ThemeToggle />
                  <Button
                    variant="secondary"
                    size="sm"
                    loading={refreshing}
                    icon={<RefreshCw size={16} />}
                    onClick={() => void handleRefresh()}
                  >
                    Refresh
                  </Button>
                  <Button variant="ghost" size="sm" icon={<LogOut size={16} />} onClick={logout}>
                    Sign out
                  </Button>
                </div>
              </div>
            </div>
          </header>

          <main id="main-content" tabIndex={-1} className="flex-1 px-4 pb-8 sm:px-6 lg:px-8">
            <Outlet context={shellContext} />
          </main>
        </div>
      </div>
    </div>
  )
}
