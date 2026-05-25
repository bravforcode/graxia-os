import { useState, useEffect } from "react";
import { useParams, useNavigate } from "react-router-dom";
import { ArrowLeft } from "lucide-react";
import { StatusBadge } from "@/components/admin/StatusBadge";
import { SafeJsonViewer } from "@/components/admin/SafeJsonViewer";
import { PageHeader } from "@/components/ui/page-header";
import { Panel } from "@/components/ui/panel";
import { Button } from "@/components/ui/button";
import { getApprovalById, approveApproval, rejectApproval } from "@/lib/admin-api";

interface ApprovalDetail {
  id: string;
  title: string;
  action_type: string;
  subject_type: string | null;
  subject_id: string | null;
  status: string;
  policy_class: string;
  requested_by: string | null;
  details: Record<string, unknown> | null;
  preview: Record<string, unknown> | null;
  expires_at: string | null;
  resolved_at: string | null;
  resolution_note: string | null;
  created_at: string | null;
}

export default function ApprovalDetailPage() {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const [approval, setApproval] = useState<ApprovalDetail | null>(null);
  const [loading, setLoading] = useState(true);
  const [actionLoading, setActionLoading] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!id) return;
    loadApproval();
  }, [id]);

  async function loadApproval() {
    setLoading(true);
    try {
      const result = await getApprovalById(id!);
      setApproval(result as unknown as ApprovalDetail);
    } catch {
      setApproval(null);
    }
    setLoading(false);
  }

  async function handleApprove() {
    if (!id) return;
    setActionLoading("approve");
    const ok = await approveApproval(id);
    if (ok) loadApproval();
    else setError("Failed to approve");
    setActionLoading(null);
  }

  async function handleReject() {
    if (!id) return;
    setActionLoading("reject");
    const ok = await rejectApproval(id);
    if (ok) loadApproval();
    else setError("Failed to reject");
    setActionLoading(null);
  }

  if (loading) {
    return <div className="flex items-center justify-center py-12"><div className="h-6 w-6 animate-spin rounded-full border-2 border-zinc-600 border-t-white" /></div>;
  }

  if (!approval) {
    return (
      <div className="space-y-4">
        <Button variant="ghost" onClick={() => navigate("/admin/approvals")}><ArrowLeft className="h-4 w-4" /> Back</Button>
        <div className="rounded-xl border border-dashed border-zinc-800 py-12 text-center text-sm text-zinc-500">Approval not found.</div>
      </div>
    );
  }

  const riskMap: Record<string, string> = {
    send_customer_email: "APPROVAL_REQUIRED",
    share_public_doc: "APPROVAL_REQUIRED",
    default: "REVIEW",
  };

  return (
    <div className="space-y-6">
      <div className="flex items-center gap-3">
        <Button variant="ghost" size="sm" onClick={() => navigate("/admin/approvals")}>
          <ArrowLeft className="h-4 w-4" /> Back
        </Button>
      </div>

      <PageHeader
        title={approval.title}
        description={`${approval.action_type} · ${approval.policy_class}`}
        actions={<StatusBadge status={approval.status} />}
      />

      {error && (
        <div className="rounded-lg bg-red-500/10 px-3 py-2 text-xs text-red-400">{error}</div>
      )}

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        {/* Details */}
        <Panel title="Details" eyebrow="INFO">
          <div className="space-y-3 text-xs">
            <div className="grid grid-cols-2 gap-2">
              <div className="text-zinc-500">Approval ID</div>
              <div className="text-zinc-300 font-mono">{approval.id}</div>
              <div className="text-zinc-500">Action Type</div>
              <div className="text-zinc-300">{approval.action_type}</div>
              <div className="text-zinc-500">Status</div>
              <div><StatusBadge status={approval.status} /></div>
              <div className="text-zinc-500">Policy Class</div>
              <div className="text-zinc-300">{approval.policy_class}</div>
              <div className="text-zinc-500">Subject Type</div>
              <div className="text-zinc-300">{approval.subject_type || "-"}</div>
              <div className="text-zinc-500">Subject ID</div>
              <div className="text-zinc-300 font-mono text-[10px]">{approval.subject_id || "-"}</div>
              <div className="text-zinc-500">Requested By</div>
              <div className="text-zinc-300">{approval.requested_by || "-"}</div>
              <div className="text-zinc-500">Created</div>
              <div className="text-zinc-300">{approval.created_at || "-"}</div>
              <div className="text-zinc-500">Expires</div>
              <div className="text-zinc-300">{approval.expires_at || "-"}</div>
              {approval.resolved_at && (
                <>
                  <div className="text-zinc-500">Resolved</div>
                  <div className="text-zinc-300">{approval.resolved_at}</div>
                </>
              )}
              {approval.resolution_note && (
                <>
                  <div className="text-zinc-500">Note</div>
                  <div className="text-zinc-300">{approval.resolution_note}</div>
                </>
              )}
            </div>
          </div>
        </Panel>

        {/* Actions */}
        <div className="space-y-4">
          <Panel title="Actions" eyebrow="DECIDE">
            <div className="space-y-3">
              <div className="text-xs text-zinc-500">
                Risk: <span className="font-mono text-violet-400">{riskMap[approval.action_type] || riskMap.default}</span>
              </div>
              <div className="text-xs text-zinc-500">
                This action requires human review before execution.
                {approval.status !== "pending" && (
                  <span className="block mt-1 text-amber-400">Already {approval.status}.</span>
                )}
              </div>
              {approval.status === "pending" && (
                <div className="flex items-center gap-3">
                  <Button onClick={handleApprove} loading={actionLoading === "approve"} disabled={actionLoading !== null}>
                    Approve
                  </Button>
                  <Button variant="destructive" onClick={handleReject} loading={actionLoading === "reject"} disabled={actionLoading !== null}>
                    Reject
                  </Button>
                </div>
              )}
            </div>
          </Panel>

          {/* Details preview */}
          {approval.details && Object.keys(approval.details).length > 0 && (
            <Panel title="Details" eyebrow="DATA">
              <SafeJsonViewer data={approval.details} />
            </Panel>
          )}

          {approval.preview && Object.keys(approval.preview).length > 0 && (
            <Panel title="Preview" eyebrow="DATA">
              <SafeJsonViewer data={approval.preview} />
            </Panel>
          )}
        </div>
      </div>
    </div>
  );
}
