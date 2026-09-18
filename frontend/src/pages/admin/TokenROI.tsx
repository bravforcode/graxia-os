import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { ArrowRight, RefreshCw } from "lucide-react";
import { MetricCard } from "@/components/admin/MetricCard";
import { StatusBadge } from "@/components/admin/StatusBadge";
import { PageHeader } from "@/components/ui/page-header";
import { Panel } from "@/components/ui/panel";
import { Input } from "@/components/ui/input";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";
import {
  getTokenRoiSummary,
  type TokenRoiInput,
  type TokenRoiSummary,
} from "@/lib/admin-api";

const DEFAULT_INPUT: Required<TokenRoiInput> = {
  tokens_saved: 2500,
  retry_count: 1,
  retry_token_cost: 150,
  human_correction_count: 1,
  human_correction_cost: 200,
  quality_gate_passed: true,
  critical_context_lost: false,
  compression_ratio: 0.72,
  cache_hit_rate: 0.4,
  quality_gate_failures: 1,
  auto_escalations: 2,
  stale_context_incidents: 1,
};

function toNumber(value: string, fallback = 0): number {
  const parsed = Number(value);
  return Number.isFinite(parsed) ? parsed : fallback;
}

export default function TokenROIPage() {
  const [loading, setLoading] = useState(true);
  const [submitting, setSubmitting] = useState(false);
  const [input, setInput] = useState<Required<TokenRoiInput>>(DEFAULT_INPUT);
  const [result, setResult] = useState<TokenRoiSummary | null>(null);

  useEffect(() => {
    void load(DEFAULT_INPUT);
  }, []);

  async function load(nextInput: TokenRoiInput = input) {
    setLoading(true);
    const summary = await getTokenRoiSummary(nextInput);
    setResult(summary);
    setLoading(false);
  }

  async function handleEvaluate() {
    setSubmitting(true);
    await load(input);
    setSubmitting(false);
  }

  function updateField<K extends keyof Required<TokenRoiInput>>(key: K, value: Required<TokenRoiInput>[K]) {
    setInput((current) => ({ ...current, [key]: value }));
  }

  return (
    <div className="space-y-6">
      <PageHeader
        eyebrow="TOKEN ROI"
        title="Token ROI Dashboard"
        description="Scenario-based evaluator for token savings, retries, quality gates, and stale-context cost."
        actions={
          <Button variant="outline" size="sm" onClick={() => void load()} loading={loading}>
            <RefreshCw className="h-4 w-4" /> Refresh
          </Button>
        }
      />

      <div className="rounded-xl border border-cyan-500/20 bg-cyan-500/5 p-3 text-xs text-cyan-300">
        This dashboard evaluates operator-supplied scenario metrics through the backend token ROI policy. Persisted live telemetry is not available yet.
      </div>

      <div className="grid grid-cols-1 xl:grid-cols-[1.2fr_0.8fr] gap-6">
        <Panel title="Scenario Inputs" eyebrow="EVALUATE">
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            <div>
              <label className="block text-xs text-zinc-500 mb-1">Tokens saved</label>
              <Input value={input.tokens_saved} type="number" onChange={(e) => updateField("tokens_saved", toNumber(e.target.value))} className="bg-zinc-900 border-zinc-800" />
            </div>
            <div>
              <label className="block text-xs text-zinc-500 mb-1">Retry count</label>
              <Input value={input.retry_count} type="number" onChange={(e) => updateField("retry_count", toNumber(e.target.value))} className="bg-zinc-900 border-zinc-800" />
            </div>
            <div>
              <label className="block text-xs text-zinc-500 mb-1">Retry token cost</label>
              <Input value={input.retry_token_cost} type="number" onChange={(e) => updateField("retry_token_cost", toNumber(e.target.value))} className="bg-zinc-900 border-zinc-800" />
            </div>
            <div>
              <label className="block text-xs text-zinc-500 mb-1">Human correction count</label>
              <Input value={input.human_correction_count} type="number" onChange={(e) => updateField("human_correction_count", toNumber(e.target.value))} className="bg-zinc-900 border-zinc-800" />
            </div>
            <div>
              <label className="block text-xs text-zinc-500 mb-1">Human correction cost</label>
              <Input value={input.human_correction_cost} type="number" onChange={(e) => updateField("human_correction_cost", toNumber(e.target.value))} className="bg-zinc-900 border-zinc-800" />
            </div>
            <div>
              <label className="block text-xs text-zinc-500 mb-1">Compression ratio</label>
              <Input value={input.compression_ratio} type="number" step="0.01" min="0" max="1" onChange={(e) => updateField("compression_ratio", toNumber(e.target.value))} className="bg-zinc-900 border-zinc-800" />
            </div>
            <div>
              <label className="block text-xs text-zinc-500 mb-1">Cache hit rate</label>
              <Input value={input.cache_hit_rate} type="number" step="0.01" min="0" max="1" onChange={(e) => updateField("cache_hit_rate", toNumber(e.target.value))} className="bg-zinc-900 border-zinc-800" />
            </div>
            <div>
              <label className="block text-xs text-zinc-500 mb-1">Quality gate failures</label>
              <Input value={input.quality_gate_failures} type="number" onChange={(e) => updateField("quality_gate_failures", toNumber(e.target.value))} className="bg-zinc-900 border-zinc-800" />
            </div>
            <div>
              <label className="block text-xs text-zinc-500 mb-1">Auto escalations</label>
              <Input value={input.auto_escalations} type="number" onChange={(e) => updateField("auto_escalations", toNumber(e.target.value))} className="bg-zinc-900 border-zinc-800" />
            </div>
            <div>
              <label className="block text-xs text-zinc-500 mb-1">Stale context incidents</label>
              <Input value={input.stale_context_incidents} type="number" onChange={(e) => updateField("stale_context_incidents", toNumber(e.target.value))} className="bg-zinc-900 border-zinc-800" />
            </div>
          </div>

          <div className="mt-4 flex flex-wrap gap-4 text-xs text-zinc-400">
            <label className="inline-flex items-center gap-2">
              <input type="checkbox" checked={input.quality_gate_passed} onChange={(e) => updateField("quality_gate_passed", e.target.checked)} />
              Quality gate passed
            </label>
            <label className="inline-flex items-center gap-2">
              <input type="checkbox" checked={input.critical_context_lost} onChange={(e) => updateField("critical_context_lost", e.target.checked)} />
              Critical context lost
            </label>
          </div>

          <div className="mt-4 flex gap-3">
            <Button onClick={() => void handleEvaluate()} loading={submitting}>
              Evaluate
            </Button>
            <Button
              variant="outline"
              onClick={() => {
                setInput(DEFAULT_INPUT);
                void load(DEFAULT_INPUT);
              }}
            >
              Reset baseline
            </Button>
          </div>
        </Panel>

        <Panel title="Policy Outcome" eyebrow="RESULT">
          {loading ? (
            <div className="flex items-center justify-center py-12">
              <div className="h-6 w-6 animate-spin rounded-full border-2 border-zinc-600 border-t-white" />
            </div>
          ) : (
            <div className="space-y-4">
              <div className="flex items-center gap-2">
                <StatusBadge status={result?.profitable ? "ready" : "not_ready"} />
                <span className={cn("text-sm font-medium", result?.profitable ? "text-emerald-400" : "text-amber-400")}>
                  {result?.profitable ? "Profitable compression policy" : "Escalate or tighten compression"}
                </span>
              </div>
              <div className="rounded-lg border border-zinc-800 bg-zinc-900/40 p-3 text-sm text-zinc-200">
                {result?.recommendation || "No recommendation available."}
              </div>
              <Link to="/admin/runtime" className="inline-flex items-center gap-1 text-cyan-400 hover:text-cyan-300">
                Back to Runtime <ArrowRight className="h-3 w-3" />
              </Link>
            </div>
          )}
        </Panel>
      </div>

      <div className="grid grid-cols-1 sm:grid-cols-2 xl:grid-cols-5 gap-4">
        <MetricCard title="Tokens Saved" value={result?.tokens_saved ?? 0} subtitle="Input savings" />
        <MetricCard title="Net ROI" value={result?.net_roi ?? 0} subtitle="After penalties/credits" status={(result?.net_roi ?? 0) >= 0 ? "up" : "critical"} />
        <MetricCard title="Retry Cost" value={result?.retry_cost ?? 0} subtitle="retry_count × retry_token_cost" />
        <MetricCard title="Correction Cost" value={result?.correction_cost ?? 0} subtitle="human correction overhead" />
        <MetricCard title="Cache Credit" value={result?.cache_credit ?? 0} subtitle="cache hit rate bonus" status="up" />
      </div>

      <div className="grid grid-cols-1 xl:grid-cols-2 gap-6">
        <Panel title="Penalty Breakdown" eyebrow="COSTS">
          <div className="space-y-2 text-xs text-zinc-400">
            <div className="flex items-center justify-between rounded-lg border border-zinc-800 bg-zinc-900/40 px-3 py-2">
              <span>Quality penalty</span>
              <span className="text-zinc-200">{result?.quality_penalty ?? 0}</span>
            </div>
            <div className="flex items-center justify-between rounded-lg border border-zinc-800 bg-zinc-900/40 px-3 py-2">
              <span>Escalation penalty</span>
              <span className="text-zinc-200">{result?.escalation_penalty ?? 0}</span>
            </div>
            <div className="flex items-center justify-between rounded-lg border border-zinc-800 bg-zinc-900/40 px-3 py-2">
              <span>Stale context penalty</span>
              <span className="text-zinc-200">{result?.stale_context_penalty ?? 0}</span>
            </div>
          </div>
        </Panel>

        <Panel title="Signal Summary" eyebrow="QUALITY">
          <div className="space-y-2 text-xs text-zinc-400">
            <div className="flex items-center justify-between rounded-lg border border-zinc-800 bg-zinc-900/40 px-3 py-2">
              <span>Compression ratio</span>
              <span className="text-zinc-200">{result?.compression_ratio ?? 0}</span>
            </div>
            <div className="flex items-center justify-between rounded-lg border border-zinc-800 bg-zinc-900/40 px-3 py-2">
              <span>Cache hit rate</span>
              <span className="text-zinc-200">{result?.cache_hit_rate ?? 0}</span>
            </div>
            <div className="flex items-center justify-between rounded-lg border border-zinc-800 bg-zinc-900/40 px-3 py-2">
              <span>Quality gate failures</span>
              <span className="text-zinc-200">{result?.quality_gate_failures ?? 0}</span>
            </div>
            <div className="flex items-center justify-between rounded-lg border border-zinc-800 bg-zinc-900/40 px-3 py-2">
              <span>Auto escalations</span>
              <span className="text-zinc-200">{result?.auto_escalations ?? 0}</span>
            </div>
            <div className="flex items-center justify-between rounded-lg border border-zinc-800 bg-zinc-900/40 px-3 py-2">
              <span>Stale context incidents</span>
              <span className="text-zinc-200">{result?.stale_context_incidents ?? 0}</span>
            </div>
          </div>
        </Panel>
      </div>
    </div>
  );
}
