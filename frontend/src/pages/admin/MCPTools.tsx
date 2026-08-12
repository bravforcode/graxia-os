import { useState, useEffect } from "react";
import { useNavigate } from "react-router-dom";
import { Search, RefreshCw } from "lucide-react";
import { RiskBadge } from "@/components/admin/RiskBadge";
import { StatusBadge } from "@/components/admin/StatusBadge";
import { PageHeader } from "@/components/ui/page-header";

import { Input } from "@/components/ui/input";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";
import { listTools, type MCPToolDefinition } from "@/lib/admin-api";

const riskFilters = ["all", "READ_ONLY", "LOW_WRITE", "APPROVAL_REQUIRED", "DANGEROUS_BLOCKED"];

export default function MCPTools() {
  const navigate = useNavigate();
  const [tools, setTools] = useState<MCPToolDefinition[]>([]);
  const [loading, setLoading] = useState(true);
  const [search, setSearch] = useState("");
  const [riskFilter, setRiskFilter] = useState("all");

  useEffect(() => {
    loadTools();
  }, []);

  async function loadTools() {
    setLoading(true);
    const result = await listTools();
    setTools(result);
    setLoading(false);
  }

  const filtered = tools.filter((t) => {
    if (riskFilter !== "all" && t.risk_level !== riskFilter) return false;
    if (search && !t.name.toLowerCase().includes(search.toLowerCase()) && !t.description?.toLowerCase().includes(search.toLowerCase())) return false;
    return true;
  });

  return (
    <div className="space-y-6">
      <PageHeader
        title="MCP Tools"
        description="Browse and safely run MCP tools."
        actions={
          <Button variant="outline" size="sm" onClick={loadTools} loading={loading}>
            <RefreshCw className="h-4 w-4" /> Refresh
          </Button>
        }
      />

      {/* Filters */}
      <div className="flex flex-wrap items-center gap-3">
        <div className="relative flex-1 max-w-xs">
          <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-zinc-500" />
          <Input
            placeholder="Search tools..."
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            className="pl-9 h-9 bg-zinc-900 border-zinc-800 text-sm"
          />
        </div>
        <div className="flex gap-1">
          {riskFilters.map((rf) => (
            <button
              key={rf}
              onClick={() => setRiskFilter(rf)}
              className={cn(
                "rounded-md px-2.5 py-1 text-xs font-medium transition-colors",
                riskFilter === rf
                  ? "bg-zinc-800 text-white"
                  : "text-zinc-500 hover:text-zinc-300"
              )}
            >
              {rf === "all" ? "All" : rf.replace(/_/g, " ")}
            </button>
          ))}
        </div>
      </div>

      {/* Loading */}
      {loading && (
        <div className="flex items-center justify-center py-12">
          <div className="h-6 w-6 animate-spin rounded-full border-2 border-zinc-600 border-t-white" />
        </div>
      )}

      {/* Tool Grid */}
      {!loading && (
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-3">
          {filtered.map((tool) => (
            <button
              key={tool.name}
              onClick={() => navigate(`/admin/mcp-tools/${encodeURIComponent(tool.name)}`)}
              className="rounded-xl border border-zinc-800 bg-zinc-900/40 p-4 text-left transition-all hover:border-zinc-700 hover:bg-zinc-900/80"
            >
              <div className="flex items-start justify-between gap-2 mb-2">
                <span className="text-sm font-medium text-white font-mono truncate">{tool.name}</span>
                <RiskBadge riskLevel={tool.risk_level} compact />
              </div>
              <p className="text-xs text-zinc-500 line-clamp-2 mb-3">{tool.description || "No description"}</p>
              <div className="flex items-center gap-2">
                {tool.requires_approval && <StatusBadge status="approval_required" />}
              </div>
            </button>
          ))}
        </div>
      )}

      {!loading && filtered.length === 0 && (
        <div className="rounded-xl border border-dashed border-zinc-800 py-12 text-center text-sm text-zinc-500">
          No tools match your filters.
        </div>
      )}
    </div>
  );
}
