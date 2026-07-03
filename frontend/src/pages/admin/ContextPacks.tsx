import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { Search } from "lucide-react";
import { SafeJsonViewer } from "@/components/admin/SafeJsonViewer";
import { ContextPackSummary } from "@/components/admin/ContextPackSummary";
import { PageHeader } from "@/components/ui/page-header";
import { Panel } from "@/components/ui/panel";
import { Input } from "@/components/ui/input";
import { Button } from "@/components/ui/button";

import { buildContextPack, searchProjectContext, type ContextPack } from "@/lib/admin-api";

export default function ContextPacksPage() {
  const navigate = useNavigate();
  const [taskType, setTaskType] = useState("funnel_review");
  const [goal, setGoal] = useState("daily funnel brief");
  const [query, setQuery] = useState("");
  const [tokenBudget, setTokenBudget] = useState(4000);
  const [building, setBuilding] = useState(false);
  const [searching, setSearching] = useState(false);
  const [result, setResult] = useState<Record<string, unknown> | null>(null);
  const [searchResult, setSearchResult] = useState<Record<string, unknown> | null>(null);
  const [buildError, setBuildError] = useState<string | null>(null);

  async function handleBuild() {
    setBuilding(true);
    setBuildError(null);
    setResult(null);
    const res = await buildContextPack({
      task_type: taskType,
      goal,
      token_budget: tokenBudget,
      query: query || undefined,
      must_preserve: ["Makefile", "README.md"],
    });
    if (res) {
      setResult(res);
    } else {
      setBuildError("Failed to build context pack. Is the backend running?");
    }
    setBuilding(false);
  }

  async function handleSearch() {
    if (!query.trim()) return;
    setSearching(true);
    setSearchResult(null);
    const res = await searchProjectContext(query);
    setSearchResult(res);
    setSearching(false);
  }

  return (
    <div className="space-y-6">
      <PageHeader
        title="Context Packs"
        description="Build and inspect context packs."
      />

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        {/* Build form */}
        <Panel title="Build Context Pack" eyebrow="CREATE">
          <div className="space-y-4">
            <div>
              <label className="block text-xs text-zinc-500 mb-1">Task Type</label>
              <select
                value={taskType}
                onChange={(e) => setTaskType(e.target.value)}
                className="w-full rounded-lg border border-zinc-800 bg-zinc-900 px-3 py-2 text-sm text-white focus:outline-none focus:border-zinc-700"
              >
                <option value="funnel_review">funnel_review</option>
                <option value="workspace_review">workspace_review</option>
                <option value="security_review">security_review</option>
                <option value="release_review">release_review</option>
                <option value="context_engine_review">context_engine_review</option>
              </select>
            </div>
            <div>
              <label className="block text-xs text-zinc-500 mb-1">Goal</label>
              <Input
                value={goal}
                onChange={(e) => setGoal(e.target.value)}
                className="bg-zinc-900 border-zinc-800 text-sm"
              />
            </div>
            <div>
              <label className="block text-xs text-zinc-500 mb-1">Token Budget</label>
              <Input
                type="number"
                value={tokenBudget}
                onChange={(e) => setTokenBudget(Number(e.target.value))}
                className="bg-zinc-900 border-zinc-800 text-sm"
              />
            </div>
            <div>
              <label className="block text-xs text-zinc-500 mb-1">Query (optional)</label>
              <Input
                value={query}
                onChange={(e) => setQuery(e.target.value)}
                placeholder="Search query..."
                className="bg-zinc-900 border-zinc-800 text-sm"
              />
            </div>
            <Button onClick={handleBuild} loading={building} className="w-full">
              Build Context Pack
            </Button>
            {buildError && (
              <div className="rounded-lg bg-red-500/10 px-3 py-2 text-xs text-red-400">{buildError}</div>
            )}
          </div>
        </Panel>

        {/* Search */}
        <Panel title="Search Project Context" eyebrow="FIND">
          <div className="space-y-3">
            <div className="flex gap-2">
              <Input
                value={query}
                onChange={(e) => setQuery(e.target.value)}
                placeholder="Search query..."
                className="bg-zinc-900 border-zinc-800 text-sm flex-1"
                onKeyDown={(e) => e.key === "Enter" && handleSearch()}
              />
              <Button size="sm" onClick={handleSearch} loading={searching}>
                <Search className="h-4 w-4" />
              </Button>
            </div>
            {searchResult && (
              <SafeJsonViewer data={searchResult} />
            )}
          </div>
        </Panel>
      </div>

      {/* Build result */}
      {result && (
        <Panel title="Context Pack Result" eyebrow="BUILT">
          <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
            <ContextPackSummary contextPack={result as unknown as ContextPack} />
            <SafeJsonViewer data={result} />
          </div>
          {(result?.context_pack_id as string | undefined) ? (
            <div className="mt-3">
              <Button
                variant="outline"
                size="sm"
                onClick={() => navigate(`/admin/context-packs/${String(result?.context_pack_id ?? '')}`)}
              >
                Open context pack
              </Button>
            </div>
          ) : null}
        </Panel>
      )}
    </div>
  );
}
