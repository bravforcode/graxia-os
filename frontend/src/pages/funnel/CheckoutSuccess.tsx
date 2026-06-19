import { useSearchParams, Link } from "react-router-dom";
import { 
  CheckCircle, 
  Mail, 
  ArrowRight, 
  ShieldCheck,
  Clock 
} from "lucide-react";

export default function CheckoutSuccess() {
  const [searchParams] = useSearchParams();
  const sessionId = searchParams.get("session_id") || "";

  return (
    <div className="min-h-screen bg-slate-950 text-slate-100 flex flex-col items-center justify-center p-6 font-sans relative selection:bg-indigo-500 selection:text-white">
      {/* Background Decorative Blurs */}
      <div className="absolute inset-0 pointer-events-none overflow-hidden">
        <div className="absolute top-[25%] left-[25%] w-[40%] h-[40%] rounded-full bg-emerald-500/10 blur-[120px]" />
        <div className="absolute bottom-[25%] right-[25%] w-[40%] h-[40%] rounded-full bg-indigo-500/10 blur-[120px]" />
      </div>

      <div className="w-full max-w-lg bg-slate-900/40 border border-slate-800 rounded-[32px] p-8 shadow-2xl backdrop-blur-xl relative z-10 text-center space-y-6">
        
        {/* Success Icon */}
        <div className="w-20 h-20 bg-emerald-500/10 border border-emerald-500/20 text-emerald-400 rounded-3xl flex items-center justify-center mx-auto animate-bounce-slow">
          <CheckCircle size={40} />
        </div>

        {/* Title */}
        <div className="space-y-2">
          <span className="text-[10px] font-mono tracking-[0.24em] text-emerald-400 uppercase font-semibold bg-emerald-500/5 border border-emerald-500/10 px-3 py-1 rounded-full">
            Payment Completed Successfully
          </span>
          <h1 className="text-3xl font-extrabold tracking-tight text-slate-100 mt-2">
            Unlock Secured!
          </h1>
          <p className="text-sm text-slate-400">
            Thank you for your purchase. Your digital assets have been processed and are ready.
          </p>
        </div>

        {/* Action Steps Dashboard */}
        <div className="bg-slate-950/40 border border-slate-850/80 rounded-2xl p-5 text-left space-y-4">
          <h3 className="text-xs font-bold text-slate-300 uppercase tracking-wider">Next Instructions:</h3>
          
          <div className="flex gap-3">
            <div className="p-2 bg-indigo-500/10 rounded-lg text-indigo-400 shrink-0 h-9 w-9 flex items-center justify-center">
              <Mail size={16} />
            </div>
            <div>
              <h4 className="text-xs font-semibold text-slate-200">Check Your Email Inbox</h4>
              <p className="text-[11px] text-slate-500 mt-0.5">
                We have emailed a unique secure delivery access link to your checkout email. Keep this key private.
              </p>
            </div>
          </div>

          <div className="flex gap-3">
            <div className="p-2 bg-indigo-500/10 rounded-lg text-indigo-400 shrink-0 h-9 w-9 flex items-center justify-center">
              <Clock size={16} />
            </div>
            <div>
              <h4 className="text-xs font-semibold text-slate-200">Delivery Delay Protection</h4>
              <p className="text-[11px] text-slate-500 mt-0.5">
                Emails are dispatched instantly. If not received in 3 minutes, verify your spam/junk folder.
              </p>
            </div>
          </div>
        </div>

        {/* Bottom Actions */}
        <div className="pt-2 flex flex-col gap-3">
          <Link
            to="/"
            className="w-full py-3 bg-gradient-to-r from-indigo-500 to-purple-600 hover:from-indigo-600 hover:to-purple-700 text-white font-semibold rounded-xl text-sm transition-all transform hover:-translate-y-0.5 shadow-lg flex items-center justify-center gap-1.5"
          >
            Go to Portal Dashboard
            <ArrowRight size={15} />
          </Link>
          
          {sessionId && (
            <div className="text-[9px] text-slate-600 font-mono select-all uppercase">
              Stripe Session ID: {sessionId}
            </div>
          )}
        </div>
      </div>
      
      {/* Verification footer */}
      <div className="mt-8 flex items-center gap-1.5 text-xs text-slate-600">
        <ShieldCheck size={14} className="text-emerald-500/60" />
        Secured by Stripe Cryptographic Signatures
      </div>
    </div>
  );
}
