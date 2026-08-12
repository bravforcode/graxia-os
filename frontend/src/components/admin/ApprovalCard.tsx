import { FileText, ShieldAlert, UserCheck } from "lucide-react";
import { StatusBadge } from "./StatusBadge";

interface ApprovalCardProps {
  id: string;
  title: string;
  actionType: string;
  status: string;
  riskNote?: string;
  createdAt?: string | null;
  summary?: string;
  onApprove?: () => void;
  onReject?: () => void;
}

const actionIcons: Record<string, typeof FileText> = {
  send_customer_email: UserCheck,
  share_public_doc: FileText,
  default: ShieldAlert,
};

export function ApprovalCard({ id, title, actionType, status, riskNote, createdAt, summary, onApprove, onReject }: ApprovalCardProps) {
  const Icon = actionIcons[actionType] || actionIcons.default;

  return (
    <div className="rounded-xl border border-zinc-800 bg-zinc-900/60 p-4 transition-colors hover:bg-zinc-900/80">
      <div className="flex items-start justify-between gap-4">
        <div className="flex items-start gap-3 min-w-0">
          <div className="mt-0.5 rounded-lg bg-violet-500/10 p-2">
            <Icon className="h-4 w-4 text-violet-400" />
          </div>
          <div className="min-w-0">
            <div className="flex items-center gap-2 mb-1">
              <span className="text-sm font-medium text-white truncate">{title}</span>
              <StatusBadge status={status} />
            </div>
            <div className="flex items-center gap-3 text-xs text-zinc-500">
              <span className="font-mono text-zinc-600">{actionType}</span>
              <span>ID: <span className="font-mono text-zinc-500">{id.slice(0, 12)}...</span></span>
              {createdAt && <span>{createdAt}</span>}
            </div>
            {riskNote && (
              <div className="mt-2 text-xs text-amber-400 bg-amber-500/10 rounded px-2 py-1 inline-block">
                {riskNote}
              </div>
            )}
            {summary && (
              <div className="mt-2 text-xs text-zinc-400">{summary}</div>
            )}
          </div>
        </div>

        {status === "pending" && (
          <div className="flex items-center gap-2 flex-shrink-0">
            {onApprove && (
              <button
                onClick={onApprove}
                className="rounded-md bg-emerald-500/10 px-3 py-1.5 text-xs font-medium text-emerald-400 hover:bg-emerald-500/20 transition-colors"
              >
                Approve
              </button>
            )}
            {onReject && (
              <button
                onClick={onReject}
                className="rounded-md bg-red-500/10 px-3 py-1.5 text-xs font-medium text-red-400 hover:bg-red-500/20 transition-colors"
              >
                Reject
              </button>
            )}
          </div>
        )}
      </div>
    </div>
  );
}
