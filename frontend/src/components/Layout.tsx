import { useState } from 'react'
import { Link, Outlet, useLocation } from 'react-router-dom'
import {
  Activity,
  BarChart3,
  Bot,
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
    Command,
  TerminalSquare,
  Gauge,
  Workflow,
  ScrollText,
  Server,
  HardDrive,
  Database
} from 'lucide-react'

import { Button } from '@/components/ui/button'
import { ScrollArea } from '@/components/ui/scroll-area'
import { Sheet, SheetContent } from '@/components/ui/sheet'
import { DropdownMenu, DropdownMenuContent, DropdownMenuItem, DropdownMenuLabel, DropdownMenuSeparator, DropdownMenuTrigger } from '@/components/ui/dropdown-menu'

import { StatusPill } from '@/components/ui/status-pill'
import { ThemeToggle } from '@/components/ui/theme-toggle'
import { useAuth } from '@/contexts/AuthContext'
import { useAgentStream, type AgentConnectionState, type AgentFeedItem, type AgentTransport } from '@/hooks/useAgentStream'
import type { EventStats, SystemHealth } from '@/lib/api'
import { cn } from '@/lib/utils'
import { useUIStore } from '@/store/uiStore'
import { CommandBar } from './layout/CommandBar'
import { AnimatedTooltip } from '@/components/ui/animated-tooltip'

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
  { path: '/agents', label: 'Agents', icon: Bot },
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

const systemNavItems = [
  { path: '/event-bus', label: 'Event Bus', icon: Activity },
]

const adminNavItems: never[] = []

function isActivePath(pathname: string, path: string) {
  return path === '/' ? pathname === path : pathname === path || pathname.startsWith(`${path}/`)
}

function runtimeTone(connectionState: AgentConnectionState, health: SystemHealth | null) {
  if (connectionState === 'offline') return 'danger' as const
  if (!health || health.llm_degraded || health.readiness.mode !== 'full') return 'warning' as const
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

    const runtimeLabel =
    connectionState === 'live'
      ? 'Live'
      : connectionState === 'fallback'
        ? 'Fallback'
        : connectionState === 'offline'
          ? 'Offline'
          : 'Connecting'

  const NavLinks = ({ onClick }: { onClick?: () => void }) => (
    <div className="space-y-6">
      <div className="space-y-1">
        {navItems.map((item) => {
          const Icon = item.icon
          const active = isActivePath(location.pathname, item.path)
          return (
            <AnimatedTooltip key={item.path} content={item.label} side="right">
              <Link
                to={item.path}
                onClick={onClick}
                className={cn(
                  'group relative flex items-center gap-3 rounded-md px-3 py-2 text-sm transition-colors',
                  active
                    ? 'bg-zinc-900 text-white font-medium'
                    : 'text-zinc-400 hover:bg-zinc-900 hover:text-white'
                )}
              >
                <Icon size={16} className={cn('shrink-0')} />
                <span className="flex-1 lg:hidden xl:block">{item.label}</span>
              </Link>
            </AnimatedTooltip>
          )
        })}
      </div>

      <div className="space-y-1">
        <p className="px-3 text-xs font-medium text-zinc-500 lg:hidden xl:block">System</p>
        {systemNavItems.map((item) => {
          const Icon = item.icon
          const active = isActivePath(location.pathname, item.path)
          return (
            <AnimatedTooltip key={item.path} content={item.label} side="right">
              <Link
                to={item.path}
                onClick={onClick}
                className={cn(
                  'group relative flex items-center gap-3 rounded-md px-3 py-2 text-sm transition-colors',
                  active
                    ? 'bg-zinc-900 text-white font-medium'
                    : 'text-zinc-400 hover:bg-zinc-900 hover:text-white'
                )}
              >
                <Icon size={16} className={cn('shrink-0')} />
                <span className="flex-1 lg:hidden xl:block">{item.label}</span>
              </Link>
            </AnimatedTooltip>
          )
        })}
      </div>

      {/* Admin section */}
      <div className="space-y-1">
        <p className="px-3 text-xs font-medium text-zinc-500 lg:hidden xl:block">Admin</p>
        {adminNavItems.map((item) => {
          const Icon = item.icon
          const active = isActivePath(location.pathname, item.path)
          return (
            <AnimatedTooltip key={item.path} content={item.label} side="right">
              <Link
                to={item.path}
                onClick={onClick}
                className={cn(
                  'group relative flex items-center gap-3 rounded-md px-3 py-2 text-sm transition-colors',
                  active
                    ? 'bg-zinc-900 text-white font-medium'
                    : 'text-zinc-400 hover:bg-zinc-900 hover:text-white'
                )}
              >
                <Icon size={16} className={cn('shrink-0')} />
                <span className="flex-1 lg:hidden xl:block">{item.label}</span>
              </Link>
            </AnimatedTooltip>
          )
        })}
      </div>
    </div>
  )

  return (
    <div className="relative min-h-screen bg-black text-white font-sans selection:bg-white/30 selection:text-white">
      <CommandBar />
      <a href="#main-content" className="sr-only focus:not-sr-only focus:absolute focus:z-[100] focus:p-4 focus:bg-zinc-900 focus:text-white">
        Skip to main content
      </a>

      <div className="relative z-10 flex min-h-screen">
        {/* Desktop Sidebar */}
        <nav aria-label="Sidebar" className="hidden lg:flex w-20 xl:w-64 flex-col border-r border-zinc-800 bg-black">
          <div className="flex h-16 items-center justify-center xl:justify-start xl:px-6 border-b border-zinc-800">
            <div className="h-6 w-6 rounded bg-white flex items-center justify-center">
              <TerminalSquare className="h-4 w-4 text-black" />
            </div>
            <span className="ml-3 font-semibold text-white hidden xl:block">
              Graxia
            </span>
          </div>

          <ScrollArea className="flex-1 px-3 py-4">
            <NavLinks />
          </ScrollArea>

          <div className="p-4 border-t border-zinc-800">
            <DropdownMenu>
              <DropdownMenuTrigger asChild>
                <button className="w-full flex items-center justify-center xl:justify-start gap-3 rounded-md p-2 hover:bg-zinc-900 transition-colors">
                  <div className="h-8 w-8 rounded-full bg-zinc-800 flex items-center justify-center text-xs font-medium text-white">
                    {user?.email?.charAt(0).toUpperCase() || 'U'}
                  </div>
                  <div className="hidden xl:block text-left overflow-hidden">
                    <p className="text-sm font-medium text-white truncate">{user?.email}</p>
                    <p className="text-xs text-zinc-500">Operator</p>
                  </div>
                </button>
              </DropdownMenuTrigger>
              <DropdownMenuContent align="end" className="w-56 bg-black border-zinc-800 text-white">
                <DropdownMenuLabel>My Account</DropdownMenuLabel>
                <DropdownMenuSeparator className="bg-zinc-800" />
                <DropdownMenuItem className="focus:bg-zinc-900 focus:text-white cursor-pointer">Profile Settings</DropdownMenuItem>
                <DropdownMenuItem className="focus:bg-zinc-900 focus:text-white cursor-pointer" onClick={logout}>
                  <LogOut className="mr-2 h-4 w-4" />
                  <span>Sign out</span>
                </DropdownMenuItem>
              </DropdownMenuContent>
            </DropdownMenu>
          </div>
        </nav>

        {/* Mobile Sidebar via Sheet */}
        <Sheet open={sidebarOpen} onOpenChange={(open) => !open && closeSidebar()}>
          <SheetContent className="w-[280px] bg-black border-zinc-800 p-0 text-white flex flex-col">
            <div className="flex h-16 items-center px-6 border-b border-zinc-800">
              <TerminalSquare className="h-6 w-6 text-white" />
              <span className="ml-3 font-semibold">Graxia</span>
            </div>
            <ScrollArea className="flex-1 px-4 py-4">
              <NavLinks onClick={closeSidebar} />
            </ScrollArea>
          </SheetContent>
        </Sheet>

        {/* Main Content Area */}
        <div className="flex flex-1 flex-col min-w-0">
          {/* Top Header */}
          <header className="sticky top-0 z-30 flex h-16 items-center gap-4 border-b border-zinc-800 bg-black px-4 sm:gap-x-6 sm:px-6 lg:px-8">
            <button
              type="button"
              className="lg:hidden p-2 -ml-2 text-zinc-400 hover:text-white transition-colors rounded-md hover:bg-zinc-900"
              onClick={toggleSidebar}
            >
              <span className="sr-only">Open sidebar</span>
              <Menu className="h-5 w-5" aria-hidden="true" />
            </button>

            <div className="flex flex-1 gap-x-4 self-stretch lg:gap-x-6 justify-between items-center">
              <div className="flex items-center gap-4 flex-1">
                {/* Search/Command trigger mockup */}
                <button className="hidden sm:flex items-center gap-2 px-3 py-1.5 text-sm text-zinc-400 bg-zinc-900 border border-zinc-800 rounded-md hover:border-zinc-700 transition-colors w-64">
                  <Command className="h-4 w-4" />
                  <span>Search commands...</span>
                  <kbd className="ml-auto pointer-events-none inline-flex h-5 items-center gap-1 rounded bg-black px-1.5 font-mono text-[10px] font-medium text-zinc-400 border border-zinc-800">
                    <span className="text-xs">⌘</span>K
                  </kbd>
                </button>
              </div>

              <div className="flex items-center gap-x-3 lg:gap-x-4">
                <div className="hidden sm:flex items-center gap-2">
                  <AnimatedTooltip content={`Runtime: ${runtimeLabel}`}>
                    <div>
                      <StatusPill label={runtimeLabel} tone={runtimeTone(connectionState, health)} pulse={connectionState !== 'offline'} />
                    </div>
                  </AnimatedTooltip>
                  <AnimatedTooltip content="Transport Layer">
                    <div>
                      <StatusPill label={transport} tone={transport === 'websocket' ? 'info' : 'neutral'} />
                    </div>
                  </AnimatedTooltip>
                </div>

                <div className="h-6 w-px bg-zinc-800 hidden sm:block" />

                <ThemeToggle />

                <Button
                  variant="outline"
                  size="icon"
                  className="h-9 w-9 bg-black border-zinc-800 text-zinc-400 hover:text-white hover:bg-zinc-900"
                  onClick={() => void handleRefresh()}
                  disabled={refreshing}
                  aria-label="Refresh runtime"
                >
                  <RefreshCw className={cn("h-4 w-4", refreshing && "animate-spin")} />
                </Button>
              </div>
            </div>
          </header>

          {/* Page Content */}
          <main id="main-content" className="flex-1 p-4 sm:p-6 lg:p-8">
            <div className="min-h-full rounded-xl border border-zinc-800 bg-black p-6">
              <Outlet context={shellContext} />
            </div>
          </main>
        </div>
      </div>
    </div>
  )
}
