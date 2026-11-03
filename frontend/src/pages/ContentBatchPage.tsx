import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { client } from "../lib/api";

type Batch = {
  id: string;
  status: string;
  item_count: number;
  live: boolean;
  dry_run: boolean;
  fallback_used: boolean;
  block_codes?: string[];
};

export default function ContentBatchPage() {
  const [batches, setBatches] = useState<Batch[]>([]);
  const [topic, setTopic] = useState("");
  const [loading, setLoading] = useState(true);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState("");

  const refresh = async () => {
    try {
      setLoading(true);
      const { data } = await client.get<Batch[]>("/content-batches");
      setBatches(data);
      setError("");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Unable to load content batches");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => { void refresh(); }, []);

  const createBatch = async () => {
    if (!topic.trim()) return;
    try {
      setSubmitting(true);
      await client.post("/content-batches", {
        topic: topic.trim(),
        canonical_url: `${window.location.origin}/guides/${topic.trim().toLowerCase().replace(/[^a-z0-9]+/g, "-")}`,
        utm_source: "organic",
        utm_medium: "content",
        utm_campaign: topic.trim().toLowerCase().replace(/[^a-z0-9]+/g, "-").slice(0, 80),
        dry_run: true,
        live: false,
      }, { headers: { "Idempotency-Key": `content-${Date.now()}` } });
      setTopic("");
      await refresh();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Unable to queue content batch");
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <div className="space-y-6 p-6">
      <div>
        <Link to="/app" className="text-xs text-slate-400 hover:text-slate-200">← Dashboard</Link>
        <h1 className="mt-3 text-2xl font-bold text-slate-100">Organic content batches</h1>
        <p className="mt-1 text-sm text-slate-400">Queue one approved batch at a time. Default output is a 9-item dry-run export.</p>
      </div>

      <div className="flex gap-2 rounded-2xl border border-slate-800 bg-slate-900/50 p-4">
        <input
          value={topic}
          onChange={(event) => setTopic(event.target.value)}
          placeholder="e.g. AI automation for Thai SMEs"
          className="min-w-0 flex-1 rounded-xl border border-slate-700 bg-slate-950 px-3 py-2 text-sm text-slate-100 outline-none focus:border-indigo-500"
        />
        <button onClick={() => void createBatch()} disabled={submitting || !topic.trim()} className="rounded-xl bg-indigo-600 px-4 py-2 text-sm font-semibold text-white disabled:opacity-50">
          {submitting ? "Queueing…" : "Create batch"}
        </button>
      </div>

      {error && <div className="rounded-xl border border-rose-500/30 bg-rose-500/10 p-3 text-sm text-rose-300">{error}</div>}
      {loading ? <p className="text-sm text-slate-400">Loading queue…</p> : (
        <div className="space-y-3">
          {batches.map((batch) => (
            <div key={batch.id} className="flex items-center justify-between rounded-2xl border border-slate-800 bg-slate-900/40 p-4">
              <div>
                <p className="text-sm font-semibold text-slate-100">{batch.id}</p>
                <p className="mt-1 text-xs text-slate-400">{batch.item_count} items · {batch.live ? "live request" : "dry-run"}{batch.fallback_used ? " · fallback draft" : ""}</p>
              </div>
              <span className={`rounded-full px-2.5 py-1 text-xs font-semibold ${batch.status === "blocked" || batch.status === "failed" ? "bg-rose-500/10 text-rose-300" : "bg-indigo-500/10 text-indigo-300"}`}>{batch.status}</span>
            </div>
          ))}
          {!batches.length && <p className="rounded-2xl border border-dashed border-slate-800 p-8 text-center text-sm text-slate-500">No batches yet.</p>}
        </div>
      )}
    </div>
  );
}
