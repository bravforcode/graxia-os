import { useEffect, useState } from "react";
import { useParams } from "react-router-dom";
import { 
  Download, 
  Lock, 
  ExternalLink, 
  AlertTriangle,
  Clock,
  CheckCircle
} from "lucide-react";
import { funnelApi, type DeliveryPayload } from "../../api/funnel";

export default function DeliveryAccessPage() {
  const { token } = useParams<{ token: string }>();
  const [loading, setLoading] = useState(true);
  const [errorMsg, setErrorMsg] = useState("");
  const [payload, setPayload] = useState<DeliveryPayload | null>(null);
  const [consuming, setConsuming] = useState(false);
  const [assetUnlocked, setAssetUnlocked] = useState(false);
  const [unlockedPayload, setUnlockedPayload] = useState<DeliveryPayload | null>(null);

  const rawToken = token || "";

  useEffect(() => {
    if (rawToken) {
      fetchPayload();
    }
  }, [rawToken]);

  const fetchPayload = async () => {
    try {
      setLoading(true);
      setErrorMsg("");
      const res = await funnelApi.getDeliveryPayload(rawToken);
      setPayload(res);
    } catch (err: any) {
      console.error("Failed to retrieve delivery payload", err);
      setErrorMsg(err.response?.data?.detail || "Invalid, expired, or capped delivery token. Access Denied.");
    } finally {
      setLoading(false);
    }
  };

  const handleConsume = async () => {
    if (!rawToken) return;
    try {
      setConsuming(true);
      setErrorMsg("");
      const res = await funnelApi.consumeDeliveryPayload(rawToken);
      setUnlockedPayload(res);
      setAssetUnlocked(true);
      
      // Update the generic view too
      setPayload(res);
    } catch (err: any) {
      console.error("Failed to consume delivery asset", err);
      setErrorMsg(err.response?.data?.detail || "Failed to download asset. Access might have expired or hit limit.");
    } finally {
      setConsuming(false);
    }
  };

  if (loading) {
    return (
      <div className="min-h-screen bg-slate-950 flex flex-col items-center justify-center text-slate-400">
        <div className="w-12 h-12 border-4 border-indigo-500 border-t-transparent rounded-full animate-spin mb-4" />
        <p className="text-sm font-medium tracking-wide">Validating Secure Credentials...</p>
      </div>
    );
  }

  if (errorMsg || !payload) {
    return (
      <div className="min-h-screen bg-slate-950 flex flex-col items-center justify-center text-slate-400 p-6">
        <div className="w-16 h-16 bg-rose-500/10 border border-rose-500/20 text-rose-400 rounded-3xl flex items-center justify-center mb-6">
          <AlertTriangle size={32} />
        </div>
        <h2 className="text-2xl font-bold text-slate-100">Access Denied</h2>
        <p className="text-sm text-slate-500 text-center max-w-md mt-2">
          {errorMsg || "The credentials provided are invalid, expired, or have exceeded download limits."}
        </p>
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-slate-950 text-slate-100 flex flex-col items-center justify-center p-6 font-sans relative selection:bg-indigo-500 selection:text-white">
      {/* Blurs */}
      <div className="absolute inset-0 pointer-events-none overflow-hidden">
        <div className="absolute top-[20%] left-[20%] w-[45%] h-[45%] rounded-full bg-indigo-500/10 blur-[130px]" />
        <div className="absolute bottom-[20%] right-[20%] w-[45%] h-[45%] rounded-full bg-cyan-500/10 blur-[130px]" />
      </div>

      <div className="w-full max-w-xl bg-slate-900/40 border border-slate-800 rounded-[32px] p-8 shadow-2xl backdrop-blur-xl relative z-10 space-y-6">
        {/* Token status indicator header */}
        <div className="flex justify-between items-center pb-4 border-b border-slate-850">
          <div className="flex items-center gap-2">
            <div className="w-8 h-8 rounded-lg bg-indigo-500/10 flex items-center justify-center text-indigo-400">
              <Lock size={16} />
            </div>
            <div>
              <div className="text-[10px] text-slate-500 font-semibold uppercase tracking-wider">Vault Access Portal</div>
              <div className="text-xs font-bold text-slate-300">Graxia Secure Delivery</div>
            </div>
          </div>
          <span className="inline-flex items-center gap-1.5 px-2.5 py-0.5 rounded-full text-[10px] font-semibold bg-indigo-500/10 text-indigo-300 border border-indigo-500/20">
            SECURE ACTIVE KEY
          </span>
        </div>

        {/* Product Details Block */}
        <div className="space-y-2">
          <h2 className="text-2xl font-bold tracking-tight text-slate-100">
            {payload.product_name}
          </h2>
          <p className="text-sm text-slate-400">
            Item Attached: <span className="font-semibold text-slate-200">{payload.asset_title}</span>
          </p>
        </div>

        {/* Security Parameters / Download Caps / Expiry */}
        <div className="grid grid-cols-2 gap-4 bg-slate-950/40 border border-slate-850 p-4 rounded-2xl text-xs">
          <div className="space-y-1">
            <span className="text-slate-500 flex items-center gap-1">
              <Clock size={12} /> Expiry Limit
            </span>
            <span className="font-semibold text-slate-300 block">
              {payload.expires_at ? new Date(payload.expires_at).toLocaleString() : "Never Expires"}
            </span>
          </div>

          <div className="space-y-1 border-l border-slate-850 pl-4">
            <span className="text-slate-500 flex items-center gap-1">
              <Download size={12} /> Downloads Left
            </span>
            <span className="font-semibold text-slate-300 block">
              {payload.downloads_remaining !== undefined && payload.downloads_remaining !== null 
                ? `${payload.downloads_remaining} Hits` 
                : "Unlimited Downloads"}
            </span>
          </div>
        </div>

        {/* Access panel showing actual download options */}
        {!assetUnlocked ? (
          <div className="space-y-4">
            <div className="p-4 bg-indigo-500/5 border border-indigo-500/10 text-slate-400 rounded-2xl text-xs text-center">
              Clicking the unlock button registers 1 download hit. Exceeding your download cap will terminate this token.
            </div>

            <button
              onClick={handleConsume}
              disabled={consuming}
              className="w-full py-4 bg-gradient-to-r from-indigo-500 to-purple-600 hover:from-indigo-600 hover:to-purple-700 disabled:opacity-50 text-white font-bold rounded-xl text-sm shadow-lg transition-all transform hover:-translate-y-0.5 flex items-center justify-center gap-2"
            >
              {consuming ? "Unlocking Vault Content..." : "Verify & Unlock Content"}
              <CheckCircle size={16} />
            </button>
          </div>
        ) : (
          <div className="space-y-6 border-t border-slate-850 pt-5 animate-fade-in">
            <div className="p-3 bg-emerald-500/5 border border-emerald-500/10 text-emerald-400 rounded-2xl text-xs flex items-center gap-2 font-medium">
              <CheckCircle size={16} /> Verified! Content Decrypted Successfully.
            </div>

            {/* Asset delivery display depending on type */}
            {unlockedPayload?.asset_type === "text" ? (
              <div className="space-y-2">
                <label className="text-xs font-semibold text-slate-400">Exclusive Content Content:</label>
                <div className="bg-slate-950/60 border border-slate-800 p-4 rounded-2xl font-mono text-xs text-slate-300 overflow-x-auto max-h-80 select-all whitespace-pre-wrap">
                  {unlockedPayload.content_body}
                </div>
              </div>
            ) : unlockedPayload?.asset_type === "external" ? (
              <div className="space-y-3">
                <p className="text-xs text-slate-400">
                  This asset invitation is hosted externally. Use the secure link below to redirect to your contents.
                </p>
                <a
                  href={unlockedPayload.external_url}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="w-full py-3 bg-emerald-500 hover:bg-emerald-600 text-slate-950 font-bold rounded-xl text-sm transition-all flex items-center justify-center gap-2"
                >
                  Visit External Platform URL
                  <ExternalLink size={16} />
                </a>
              </div>
            ) : (
              <div className="space-y-3">
                <p className="text-xs text-slate-400">
                  Your secured file `{unlockedPayload?.asset_title}` can be downloaded below.
                </p>
                <button
                  onClick={() => alert(`Initiating direct download of file from path: ${unlockedPayload?.content_body || unlockedPayload?.external_url}`)}
                  className="w-full py-3.5 bg-indigo-500 hover:bg-indigo-600 text-white font-bold rounded-xl text-sm transition-all flex items-center justify-center gap-2 shadow-lg"
                >
                  Download Secured {unlockedPayload?.asset_type.toUpperCase()} File
                  <Download size={16} />
                </button>
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  );
}
