import React from 'react';
import { 
  TrendingUp, 
  Users, 
  Activity, 
  DollarSign, 
  LayoutDashboard, 
  Settings, 
  ShieldCheck,
  Menu
} from 'lucide-react';

export default function DashboardPage() {
  return (
    <div className="flex h-screen bg-slate-50 font-sans text-slate-900">
      {/* Sidebar */}
      <aside className="w-64 bg-slate-900 text-white flex flex-col hidden md:flex">
        <div className="p-6 border-b border-slate-800">
          <h1 className="text-xl font-bold tracking-tight text-white flex items-center gap-2">
            <ShieldCheck className="text-blue-400" />
            BravOS
          </h1>
        </div>
        <nav className="flex-1 p-4 space-y-2">
          <a href="#" className="flex items-center gap-3 px-3 py-2 bg-blue-600 rounded-md text-sm font-medium">
            <LayoutDashboard size={18} />
            CEO Console
          </a>
          <a href="#" className="flex items-center gap-3 px-3 py-2 text-slate-400 hover:text-white hover:bg-slate-800 rounded-md text-sm font-medium transition-colors">
            <Users size={18} />
            Agents
          </a>
          <a href="#" className="flex items-center gap-3 px-3 py-2 text-slate-400 hover:text-white hover:bg-slate-800 rounded-md text-sm font-medium transition-colors">
            <Activity size={18} />
            Analytics
          </a>
          <a href="#" className="flex items-center gap-3 px-3 py-2 text-slate-400 hover:text-white hover:bg-slate-800 rounded-md text-sm font-medium transition-colors">
            <Settings size={18} />
            Settings
          </a>
        </nav>
        <div className="p-4 border-t border-slate-800 text-xs text-slate-500">
          v1.0.0-alpha
        </div>
      </aside>

      {/* Main Content */}
      <main className="flex-1 flex flex-col overflow-hidden">
        {/* Top Header */}
        <header className="h-16 bg-white border-b border-slate-200 flex items-center justify-between px-6">
          <div className="flex items-center gap-4">
            <button className="md:hidden text-slate-500">
              <Menu size={24} />
            </button>
            <h2 className="text-lg font-semibold text-slate-800">CEO Console</h2>
          </div>
          <div className="flex items-center gap-3">
            <div className="h-8 w-8 rounded-full bg-blue-100 flex items-center justify-center text-blue-700 font-bold text-xs">
              AD
            </div>
          </div>
        </header>

        {/* Scrollable Dashboard area */}
        <div className="flex-1 overflow-y-auto p-6 space-y-6">
          <div className="flex items-center justify-between">
            <h3 className="text-2xl font-bold tracking-tight">Executive Overview</h3>
            <div className="flex gap-2 text-sm text-slate-500 bg-white p-1 rounded-lg border border-slate-200">
              <button className="px-3 py-1 bg-slate-100 text-slate-900 rounded-md font-medium">Last 24h</button>
              <button className="px-3 py-1 hover:text-slate-900 transition-colors">7d</button>
              <button className="px-3 py-1 hover:text-slate-900 transition-colors">30d</button>
            </div>
          </div>

          {/* KPI Cards */}
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-6">
            <div className="bg-white p-6 rounded-xl border border-slate-200 shadow-sm">
              <div className="flex items-center justify-between mb-4">
                <div className="p-2 bg-emerald-50 text-emerald-600 rounded-lg">
                  <DollarSign size={20} />
                </div>
                <span className="text-xs font-medium text-emerald-600 flex items-center gap-1">
                  <TrendingUp size={12} />
                  +12.5%
                </span>
              </div>
              <p className="text-sm font-medium text-slate-500">Daily Revenue</p>
              <h4 className="text-2xl font-bold">$12,450</h4>
            </div>

            <div className="bg-white p-6 rounded-xl border border-slate-200 shadow-sm">
              <div className="flex items-center justify-between mb-4">
                <div className="p-2 bg-blue-50 text-blue-600 rounded-lg">
                  <Users size={20} />
                </div>
                <span className="text-xs font-medium text-blue-600 flex items-center gap-1">
                  <TrendingUp size={12} />
                  +4.2%
                </span>
              </div>
              <p className="text-sm font-medium text-slate-500">Active Agents</p>
              <h4 className="text-2xl font-bold">1,284</h4>
            </div>

            <div className="bg-white p-6 rounded-xl border border-slate-200 shadow-sm">
              <div className="flex items-center justify-between mb-4">
                <div className="p-2 bg-purple-50 text-purple-600 rounded-lg">
                  <Activity size={20} />
                </div>
                <span className="text-xs font-medium text-purple-600 flex items-center gap-1">
                  Stable
                </span>
              </div>
              <p className="text-sm font-medium text-slate-500">System Health</p>
              <h4 className="text-2xl font-bold">99.98%</h4>
            </div>

            <div className="bg-white p-6 rounded-xl border border-slate-200 shadow-sm">
              <div className="flex items-center justify-between mb-4">
                <div className="p-2 bg-amber-50 text-amber-600 rounded-lg">
                  <LayoutDashboard size={20} />
                </div>
              </div>
              <p className="text-sm font-medium text-slate-500">Queue Load</p>
              <h4 className="text-2xl font-bold">Low</h4>
            </div>
          </div>

          {/* Placeholder Chart / Activity Area */}
          <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
            <div className="bg-white p-6 rounded-xl border border-slate-200 shadow-sm min-h-[300px] flex flex-col">
              <h5 className="font-bold mb-4">Revenue Trend (Mock)</h5>
              <div className="flex-1 bg-slate-50 rounded-lg border border-dashed border-slate-200 flex items-center justify-center text-slate-400 italic">
                Revenue Chart Visualization Placeholder
              </div>
            </div>
            <div className="bg-white p-6 rounded-xl border border-slate-200 shadow-sm min-h-[300px] flex flex-col">
              <h5 className="font-bold mb-4">Recent Agent Activity</h5>
              <div className="space-y-4">
                {[1, 2, 3, 4].map((i) => (
                  <div key={i} className="flex items-center justify-between pb-4 border-b border-slate-100 last:border-0 last:pb-0">
                    <div className="flex items-center gap-3">
                      <div className="h-8 w-8 rounded bg-slate-100" />
                      <div>
                        <p className="text-sm font-medium">Agent-X-{i}0{i}</p>
                        <p className="text-xs text-slate-500">Completed data synthesis task</p>
                      </div>
                    </div>
                    <span className="text-xs text-slate-400">{i * 5}m ago</span>
                  </div>
                ))}
              </div>
            </div>
          </div>
        </div>
      </main>
    </div>
  );
}
