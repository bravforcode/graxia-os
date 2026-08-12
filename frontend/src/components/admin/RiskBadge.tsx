import { cn } from "@/lib/utils";

const riskConfig: Record<string, { bg: string; text: string; label: string }> = {
  READ_ONLY:           { bg: "bg-blue-500/10", text: "text-blue-400",   label: "READ ONLY" },
  LOW_WRITE:           { bg: "bg-amber-500/10", text: "text-amber-400", label: "LOW WRITE" },
  APPROVAL_REQUIRED:   { bg: "bg-violet-500/10", text: "text-violet-400", label: "APPROVAL REQ" },
  DANGEROUS_BLOCKED:   { bg: "bg-red-500/10", text: "text-red-400",    label: "DANGEROUS" },
  DANGEROUS:           { bg: "bg-red-500/10", text: "text-red-400",    label: "DANGEROUS" },
};

export function RiskBadge({ riskLevel, compact }: { riskLevel: string; compact?: boolean }) {
  const config = riskConfig[riskLevel] || { bg: "bg-zinc-500/10", text: "text-zinc-400", label: riskLevel };
  return (
    <span className={cn(
      "inline-flex items-center rounded-full font-semibold tracking-wider",
      compact ? "px-1.5 py-0.5 text-[10px]" : "px-2.5 py-0.5 text-xs",
      config.bg, config.text
    )}>
      {config.label}
    </span>
  );
}
