import { useEffect, useRef, useState } from "react";
import { useParams } from "react-router-dom";
import { funnelApi } from "../api/funnel";
import { captureAttribution } from "../lib/attribution";

const REFERRAL_CODE_PATTERN = /^r1\.[A-Za-z0-9_-]+\.[a-f0-9]{64}$/;

export default function ReferralRedirect() {
  const { code } = useParams<{ code: string }>();
  const redirected = useRef(false);
  const [invalid, setInvalid] = useState(false);

  useEffect(() => {
    if (!code || redirected.current || !REFERRAL_CODE_PATTERN.test(code)) return;
    redirected.current = true;
    void funnelApi.resolveReferral(code)
      .then(({ redirect_url: target }) => {
        captureAttribution(target);
        window.location.replace(target);
      })
      .catch(() => setInvalid(true));
  }, [code]);

  if (invalid || (code && !REFERRAL_CODE_PATTERN.test(code))) {
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
