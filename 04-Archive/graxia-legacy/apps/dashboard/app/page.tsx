"use client";

import { Activity, Bot, DollarSign, Users, CheckCircle2, PauseCircle, AlertTriangle } from "lucide-react";
import { LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer } from "recharts";

const revenueData = [
  { name: "Jan", value: 40000 },
  { name: "Feb", value: 45000 },
  { name: "Mar", value: 55000 },
  { name: "Apr", value: 62000 },
  { name: "May", value: 85000 },
  { name: "Jun", value: 124500 },
];

export default function CEOHome() {
  return (
    <div className="p-8 max-w-7xl mx-auto space-y-8">
      <header className="mb-8">
        <h1 className="text-3xl font-bold text-gray-900">Overview</h1>
        <p className="text-gray-500 mt-2">Welcome back. Here is the status of your enterprise.</p>
      </header>

      {/* KPIs */}
      <div className="grid grid-cols-1 md:grid-cols-4 gap-6">
        <div className="bg-white rounded-xl p-6 shadow-sm border border-gray-100">
          <div className="flex items-center justify-between">
            <div>
              <p className="text-sm font-medium text-gray-500">Total Revenue</p>
              <h3 className="text-2xl font-bold text-gray-900 mt-1">$124,500</h3>
            </div>
            <div className="w-12 h-12 bg-blue-50 rounded-full flex items-center justify-center text-blue-600">
              <DollarSign size={24} />
            </div>
          </div>
          <p className="text-sm text-green-600 mt-4 font-medium">+14% from last month</p>
        </div>
        <div className="bg-white rounded-xl p-6 shadow-sm border border-gray-100">
          <div className="flex items-center justify-between">
            <div>
              <p className="text-sm font-medium text-gray-500">Active Leads</p>
              <h3 className="text-2xl font-bold text-gray-900 mt-1">842</h3>
            </div>
            <div className="w-12 h-12 bg-indigo-50 rounded-full flex items-center justify-center text-indigo-600">
              <Users size={24} />
            </div>
          </div>
          <p className="text-sm text-green-600 mt-4 font-medium">+5% from last month</p>
        </div>
        <div className="bg-white rounded-xl p-6 shadow-sm border border-gray-100">
          <div className="flex items-center justify-between">
            <div>
              <p className="text-sm font-medium text-gray-500">Active Agents</p>
              <h3 className="text-2xl font-bold text-gray-900 mt-1">4/5</h3>
            </div>
            <div className="w-12 h-12 bg-purple-50 rounded-full flex items-center justify-center text-purple-600">
              <Bot size={24} />
            </div>
          </div>
          <p className="text-sm text-gray-500 mt-4">1 agent currently paused</p>
        </div>
        <div className="bg-white rounded-xl p-6 shadow-sm border border-gray-100">
          <div className="flex items-center justify-between">
            <div>
              <p className="text-sm font-medium text-gray-500">System Status</p>
              <h3 className="text-2xl font-bold text-gray-900 mt-1">Healthy</h3>
            </div>
            <div className="w-12 h-12 bg-green-50 rounded-full flex items-center justify-center text-green-600">
              <Activity size={24} />
            </div>
          </div>
          <p className="text-sm text-gray-500 mt-4">All services operational</p>
        </div>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-8">
        {/* Revenue Chart */}
        <div className="lg:col-span-2 bg-white rounded-xl shadow-sm border border-gray-100 p-6">
          <h2 className="text-lg font-semibold text-gray-900 mb-6">Revenue Growth</h2>
          <div className="h-72 w-full">
            <ResponsiveContainer width="100%" height="100%">
              <LineChart data={revenueData}>
                <CartesianGrid strokeDasharray="3 3" vertical={false} stroke="#E5E7EB" />
                <XAxis dataKey="name" axisLine={false} tickLine={false} tick={{ fill: '#6B7280' }} dy={10} />
                <YAxis axisLine={false} tickLine={false} tick={{ fill: '#6B7280' }} dx={-10} tickFormatter={(val) => `$${val / 1000}k`} />
                <Tooltip 
                  contentStyle={{ borderRadius: '8px', border: 'none', boxShadow: '0 4px 6px -1px rgb(0 0 0 / 0.1)' }}
                  formatter={(value) => [`$${value}`, 'Revenue']}
                />
                <Line 
                  type="monotone" 
                  dataKey="value" 
                  stroke="#3B82F6" 
                  strokeWidth={3}
                  dot={{ r: 4, strokeWidth: 2, fill: '#fff' }}
                  activeDot={{ r: 6, strokeWidth: 0 }}
                />
              </LineChart>
            </ResponsiveContainer>
          </div>
        </div>

        {/* Agent Status */}
        <div className="bg-white rounded-xl shadow-sm border border-gray-100 p-6 flex flex-col">
          <h2 className="text-lg font-semibold text-gray-900 mb-6">AI Workforce Status</h2>
          <div className="space-y-4 flex-1">
            <div className="flex items-center justify-between p-4 bg-gray-50 rounded-lg border border-gray-100">
              <div className="flex items-center space-x-3">
                <CheckCircle2 className="text-green-500" size={20} />
                <div>
                  <p className="font-medium text-gray-900">Sales Agent</p>
                  <p className="text-xs text-gray-500">Processing outreach</p>
                </div>
              </div>
              <span className="inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium bg-green-100 text-green-800">
                Active
              </span>
            </div>
            
            <div className="flex items-center justify-between p-4 bg-gray-50 rounded-lg border border-gray-100">
              <div className="flex items-center space-x-3">
                <CheckCircle2 className="text-green-500" size={20} />
                <div>
                  <p className="font-medium text-gray-900">Support Bot</p>
                  <p className="text-xs text-gray-500">Handling tickets</p>
                </div>
              </div>
              <span className="inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium bg-green-100 text-green-800">
                Active
              </span>
            </div>

            <div className="flex items-center justify-between p-4 bg-gray-50 rounded-lg border border-gray-100">
              <div className="flex items-center space-x-3">
                <PauseCircle className="text-yellow-500" size={20} />
                <div>
                  <p className="font-medium text-gray-900">Trading Bot</p>
                  <p className="text-xs text-gray-500">Market closed</p>
                </div>
              </div>
              <span className="inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium bg-yellow-100 text-yellow-800">
                Paused
              </span>
            </div>

            <div className="flex items-center justify-between p-4 bg-gray-50 rounded-lg border border-gray-100">
              <div className="flex items-center space-x-3">
                <AlertTriangle className="text-red-500" size={20} />
                <div>
                  <p className="font-medium text-gray-900">Data Scraper</p>
                  <p className="text-xs text-gray-500">Rate limited</p>
                </div>
              </div>
              <span className="inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium bg-red-100 text-red-800">
                Error
              </span>
            </div>
          </div>
        </div>
      </div>

      {/* Kanban Pipeline Placeholder */}
      <div className="bg-white rounded-xl shadow-sm border border-gray-100 p-6">
        <h2 className="text-lg font-semibold text-gray-900 mb-6">Sales Pipeline (Kanban)</h2>
        <div className="grid grid-cols-1 md:grid-cols-4 gap-4">
          {/* Stage 1 */}
          <div className="bg-gray-50 rounded-lg p-4 min-h-[300px] border border-gray-200">
            <div className="flex justify-between items-center mb-4">
              <h3 className="font-medium text-gray-700">Lead Generated</h3>
              <span className="bg-gray-200 text-gray-700 text-xs px-2 py-1 rounded-full font-medium">12</span>
            </div>
            <div className="bg-white p-3 rounded shadow-sm border border-gray-100 mb-3 hover:border-blue-300 cursor-pointer transition-colors">
              <p className="font-medium text-sm text-gray-900">Acme Corp</p>
              <p className="text-xs text-gray-500 mt-1">$50,000 potential</p>
              <div className="mt-3 flex items-center justify-between">
                <span className="text-[10px] text-gray-400 bg-gray-100 px-2 py-0.5 rounded">New</span>
                <img src={`https://api.dicebear.com/7.x/initials/svg?seed=AC&backgroundColor=1e3a8a`} alt="Acme" className="w-5 h-5 rounded-full" />
              </div>
            </div>
          </div>
          
          {/* Stage 2 */}
          <div className="bg-gray-50 rounded-lg p-4 min-h-[300px] border border-gray-200">
            <div className="flex justify-between items-center mb-4">
              <h3 className="font-medium text-gray-700">Contacted</h3>
              <span className="bg-gray-200 text-gray-700 text-xs px-2 py-1 rounded-full font-medium">8</span>
            </div>
            <div className="bg-white p-3 rounded shadow-sm border border-gray-100 mb-3 hover:border-blue-300 cursor-pointer transition-colors">
              <p className="font-medium text-sm text-gray-900">TechStart Inc</p>
              <p className="text-xs text-gray-500 mt-1">Meeting scheduled</p>
              <div className="mt-3 flex items-center justify-between">
                <span className="text-[10px] text-yellow-600 bg-yellow-50 border border-yellow-200 px-2 py-0.5 rounded">Warm</span>
                <img src={`https://api.dicebear.com/7.x/initials/svg?seed=TS&backgroundColor=1e3a8a`} alt="TechStart" className="w-5 h-5 rounded-full" />
              </div>
            </div>
            <div className="bg-white p-3 rounded shadow-sm border border-gray-100 mb-3 hover:border-blue-300 cursor-pointer transition-colors">
              <p className="font-medium text-sm text-gray-900">Global Data</p>
              <p className="text-xs text-gray-500 mt-1">Follow-up required</p>
            </div>
          </div>

          {/* Stage 3 */}
          <div className="bg-gray-50 rounded-lg p-4 min-h-[300px] border border-gray-200">
            <div className="flex justify-between items-center mb-4">
              <h3 className="font-medium text-gray-700">In Negotiation</h3>
              <span className="bg-gray-200 text-gray-700 text-xs px-2 py-1 rounded-full font-medium">3</span>
            </div>
            <div className="bg-white p-3 rounded shadow-sm border border-gray-100 mb-3 hover:border-blue-300 cursor-pointer transition-colors">
              <p className="font-medium text-sm text-gray-900">Nova Systems</p>
              <p className="text-xs text-gray-500 mt-1">Contract reviewing</p>
              <div className="mt-3 flex items-center justify-between">
                <span className="text-[10px] text-red-600 bg-red-50 border border-red-200 px-2 py-0.5 rounded">Hot</span>
                <img src={`https://api.dicebear.com/7.x/initials/svg?seed=NS&backgroundColor=1e3a8a`} alt="Nova" className="w-5 h-5 rounded-full" />
              </div>
            </div>
          </div>

          {/* Stage 4 */}
          <div className="bg-gray-50 rounded-lg p-4 min-h-[300px] border border-gray-200">
            <div className="flex justify-between items-center mb-4">
              <h3 className="font-medium text-gray-700">Closed Won</h3>
              <span className="bg-gray-200 text-gray-700 text-xs px-2 py-1 rounded-full font-medium">24</span>
            </div>
            <div className="bg-white p-3 rounded shadow-sm border border-gray-100 border-l-4 border-l-green-500 mb-3 hover:border-blue-300 cursor-pointer transition-colors">
              <p className="font-medium text-sm text-gray-900">MegaCorp Solutions</p>
              <p className="text-xs text-green-600 mt-1 font-medium">Closed at $120k</p>
            </div>
            <div className="bg-white p-3 rounded shadow-sm border border-gray-100 border-l-4 border-l-green-500 mb-3 hover:border-blue-300 cursor-pointer transition-colors">
              <p className="font-medium text-sm text-gray-900">Future Dynamics</p>
              <p className="text-xs text-green-600 mt-1 font-medium">Closed at $85k</p>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
