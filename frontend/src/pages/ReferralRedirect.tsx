import { useEffect, useRef } from "react";
import { useParams } from "react-router-dom";
import { captureAttribution } from "../lib/attribution";
import { siteUrl } from "../lib/site";

const REFERRAL_CODE_PATTERN = /^[A-Za-z0-9_-]{4,160}$/;

export default function ReferralRedirect() {
  const { code } = useParams<{ code: string }>();
  const redirected = useRef(false);

  useEffect(() => {
    if (!code || redirected.current || !REFERRAL_CODE_PATTERN.test(code)) return;
    redirected.current = true;
    const target = siteUrl(`/store?referral_code=${encodeURIComponent(code)}`);
    captureAttribution(target);
    window.location.replace(target);
  }, [code]);

  if (code && !REFERRAL_CODE_PATTERN.test(code)) {
    return (
      <main className="min-h-screen bg-slate-950 px-6 py-16 text-center text-slate-300">
        <p className="text-sm">This referral link is not valid.</p>
      </main>
    );
  }

  return (
    <main className="min-h-screen bg-slate-950 px-6 py-16 text-center text-slate-300">
      <p className="text-sm">Opening your referral link...</p>
    </main>
  );
}
