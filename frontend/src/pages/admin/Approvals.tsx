import { useState, useEffect } from "react";
import { useNavigate } from "react-router-dom";
import { RefreshCw } from "lucide-react";
import { ApprovalCard } from "@/components/admin/ApprovalCard";
import { PageHeader } from "@/components/ui/page-header";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";
import { getApprovals, approveApproval, rejectApproval, type ApprovalRequestSummary } from "@/lib/admin-api";

const statusFilters = ["all", "pending", "approved", "rejected"];

export default function ApprovalsPage() {
  const navigate = useNavigate();
  const [approvals, setApprovals] = useState<ApprovalRequestSummary[]>([]);
  const [loading, setLoading] = useState(true);
  const [filter, setFilter] = useState("pending");

  useEffect(() => {
    load();
  }, []);

  async function load() {
    setLoading(true);
    const result = await getApprovals({ limit: 50 });
    setApprovals(result);
    setLoading(false);
  }

  const filtered = filter === "all" ? approvals : approvals.filter((a) => a.status === filter);
  const pendingCount = approvals.filter((a) => a.status === "pending").length;

  async function handleApprove(id: string) {
    const ok = await approveApproval(id);
    if (ok) load();
  }

  async function handleReject(id: string) {
    const ok = await rejectApproval(id);
    if (ok) load();
  }

  return (
    <div className="space-y-6">
      <PageHeader
        title="Approvals"
        description="Human review inbox."
        actions={
          <div className="flex items-center gap-2">
            {pendingCount > 0 && (
              <span className="rounded-full bg-amber-500/10 px-2.5 py-0.5 text-xs font-medium text-amber-400">
                {pendingCount} pending
              </span>
            )}
            <Button variant="outline" size="sm" onClick={load} loading={loading}>
              <RefreshCw className="h-4 w-4" /> Refresh
            </Button>
          </div>
        }
      />

      {/* Filters */}
      <div className="flex gap-1">
        {statusFilters.map((sf) => (
          <button
            key={sf}
            onClick={() => setFilter(sf)}
            className={cn(
              "rounded-md px-2.5 py-1 text-xs font-medium transition-colors",
              filter === sf ? "bg-zinc-800 text-white" : "text-zinc-500 hover:text-zinc-300"
            )}
          >
            {sf.charAt(0).toUpperCase() + sf.slice(1)}
          </button>
        ))}
      </div>

      {loading && (
        <div className="flex items-center justify-center py-12">
          <div className="h-6 w-6 animate-spin rounded-full border-2 border-zinc-600 border-t-white" />
        </div>
      )}

      {!loading && (
        <div className="space-y-3">
          {filtered.length === 0 ? (
            <div className="rounded-xl border border-dashed border-zinc-800 py-12 text-center text-sm text-zinc-500">
              No {filter === "all" ? "" : filter} approvals.
            </div>
          ) : (
            filtered.map((approval) => (
              <div
                key={approval.id}
                className="cursor-pointer"
                onClick={() => navigate(`/admin/approvals/${approval.id}`)}
              >
                <ApprovalCard
                  id={approval.id}
                  title={approval.title}
                  actionType={approval.action_type}
                  status={approval.status}
                  createdAt={approval.created_at}
                  onApprove={approval.status === "pending" ? () => handleApprove(approval.id) : undefined}
                  onReject={approval.status === "pending" ? () => handleReject(approval.id) : undefined}
                />
              </div>
            ))
          )}
        </div>
      )}
    </div>
  );
}
