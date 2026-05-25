import { useState, useEffect } from "react";
import { useParams, useNavigate } from "react-router-dom";
import { ArrowLeft } from "lucide-react";
import { ContextPackSummary } from "@/components/admin/ContextPackSummary";
import { SafeJsonViewer } from "@/components/admin/SafeJsonViewer";
import { PageHeader } from "@/components/ui/page-header";
import { Panel } from "@/components/ui/panel";
import { Button } from "@/components/ui/button";
import { getContextPack, type ContextPack } from "@/lib/admin-api";

export default function ContextPackDetailPage() {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const [pack, setPack] = useState<ContextPack | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    if (!id) return;
    setLoading(true);
    getContextPack(id).then((result) => {
      setPack(result);
      setLoading(false);
    });
  }, [id]);

  if (loading) {
    return <div className="flex items-center justify-center py-12"><div className="h-6 w-6 animate-spin rounded-full border-2 border-zinc-600 border-t-white" /></div>;
  }

  if (!pack) {
    return (
      <div className="space-y-4">
        <Button variant="ghost" onClick={() => navigate("/admin/context-packs")}><ArrowLeft className="h-4 w-4" /> Back</Button>
        <div className="rounded-xl border border-dashed border-zinc-800 py-12 text-center text-sm text-zinc-500">Context pack not found.</div>
      </div>
    );
  }

  return (
    <div className="space-y-6">
      <div className="flex items-center gap-3">
        <Button variant="ghost" size="sm" onClick={() => navigate("/admin/context-packs")}>
          <ArrowLeft className="h-4 w-4" /> Back
        </Button>
      </div>

      <PageHeader
        title={pack.task_type}
        description={`Pack ${pack.context_pack_id?.slice(0, 16)}...`}
      />

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        <ContextPackSummary contextPack={pack} />

        <Panel title="Full Data" eyebrow="RAW">
          <SafeJsonViewer data={pack} />
        </Panel>
      </div>
    </div>
  );
}
