import { api } from "@/lib/api";
import { useEffect, useState } from "react";

type Plan = "free" | "starter" | "pro";

interface UsageData {
  plan: Plan;
  status: string;
  trial_ends_at: string | null;
  limits: { leads_per_month: number; ai_credits_cents: number; seats: number };
  usage: { leads: number; drafts: number; emails: number };
}

const PLANS = [
  {
    id: "free" as Plan,
    name: "Free",
    price: 0,
    highlight: false,
    perks: ["10 leads/month", "$2 AI credits", "1 seat", "Basic CRM"],
  },
  {
    id: "starter" as Plan,
    name: "Starter",
    price: 29,
    highlight: true,
    perks: [
      "100 leads/month",
      "$10 AI credits",
      "1 seat",
      "AI proposal drafting",
      "Email sending",
    ],
  },
  {
    id: "pro" as Plan,
    name: "Pro",
    price: 79,
    highlight: false,
    perks: [
      "Unlimited leads",
      "$50 AI credits",
      "3 seats",
      "Priority scraping",
      "API access",
    ],
  },
];

export default function Billing() {
  const [usage, setUsage] = useState<UsageData | null>(null);
  const [loading, setLoading] = useState(false);
  const [err, setErr] = useState("");

  useEffect(() => {
    api
      .getBillingUsage()
      .then((data: UsageData) => setUsage(data))
      .catch(() => {});
  }, []);

  const upgrade = async (plan: Plan) => {
    setLoading(true);
    setErr("");
    try {
      const data = await api.startCheckout(plan);
      if (data.client_secret) {
        // Load Stripe.js and confirm payment
        window.location.href = `${import.meta.env.VITE_FRONTEND_URL}/billing/confirm?secret=${data.client_secret}`;
      }
    } catch (e: unknown) {
      const err = e as { response?: { data?: { detail?: string } } };
      setErr(err.response?.data?.detail || "Checkout failed");
    } finally {
      setLoading(false);
    }
  };

  const portal = async () => {
    const data = await api.openBillingPortal();
    window.open(data.url, "_blank");
  };

  const pct = (used: number, limit: number) =>
    Math.min(100, Math.round((used / Math.max(1, limit)) * 100));

  return (
    <div className="max-w-5xl mx-auto p-6 space-y-8">
      <div>
        <h1 className="text-2xl font-bold text-gray-900 dark:text-white">
          Billing
        </h1>
        <p className="text-sm text-gray-500 mt-1">Manage your plan and usage</p>
      </div>

      {/* Usage card */}
      {usage && (
        <div className="border rounded-xl p-5 space-y-4 bg-white dark:bg-gray-900">
          <div className="flex items-center justify-between">
            <span className="font-semibold capitalize">{usage.plan} plan</span>
            <span
              className={`text-xs px-2 py-0.5 rounded-full ${
                usage.status === "active"
                  ? "bg-green-100 text-green-700"
                  : usage.status === "trialing"
                    ? "bg-blue-100 text-blue-700"
                    : "bg-red-100 text-red-700"
              }`}
            >
              {usage.status}
            </span>
          </div>
          {usage.trial_ends_at && (
            <p className="text-sm text-amber-600">
              Trial ends {new Date(usage.trial_ends_at).toLocaleDateString()}
            </p>
          )}
          <div className="space-y-2">
            <UsageBar
              label="Leads"
              used={usage.usage.leads}
              limit={usage.limits.leads_per_month}
              pct={pct}
            />
          </div>
        </div>
      )}

      {/* Plan grid */}
      {err && <p className="text-red-500 text-sm">{err}</p>}
      <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
        {PLANS.map((p) => {
          const current = usage?.plan === p.id;
          return (
            <div
              key={p.id}
              className={`relative rounded-xl border p-5 space-y-4 bg-white dark:bg-gray-900 ${
                p.highlight ? "border-blue-500 shadow-md" : "border-gray-200"
              }`}
            >
              {p.highlight && (
                <span className="absolute -top-3 left-1/2 -translate-x-1/2 bg-blue-500 text-white text-xs px-2 py-0.5 rounded-full">
                  Most Popular
                </span>
              )}
              <h3 className="font-bold text-lg">{p.name}</h3>
              <p className="text-3xl font-extrabold">
                ${p.price}
                <span className="text-base font-normal text-gray-400">/mo</span>
              </p>
              <ul className="space-y-1 text-sm text-gray-600 dark:text-gray-300">
                {p.perks.map((k) => (
                  <li key={k}>✓ {k}</li>
                ))}
              </ul>
              {current ? (
                <div className="space-y-2">
                  <span className="block text-center text-sm font-medium text-green-600">
                    Current plan
                  </span>
                  {p.id !== "free" && (
                    <button
                      onClick={portal}
                      className="w-full text-sm text-blue-600 underline"
                    >
                      Manage billing →
                    </button>
                  )}
                </div>
              ) : p.id !== "free" ? (
                <button
                  onClick={() => upgrade(p.id)}
                  disabled={loading}
                  className="w-full py-2 rounded-lg bg-blue-600 text-white text-sm font-semibold hover:bg-blue-700 disabled:opacity-50"
                >
                  {loading ? "…" : "Start 14-day free trial"}
                </button>
              ) : null}
            </div>
          );
        })}
      </div>
    </div>
  );
}

function UsageBar({
  label,
  used,
  limit,
  pct,
}: {
  label: string;
  used: number;
  limit: number;
  pct: (u: number, l: number) => number;
}) {
  const p = pct(used, limit);
  const unlimited = limit >= 9999;
  return (
    <div>
      <div className="flex justify-between text-xs text-gray-500 mb-1">
        <span>{label}</span>
        <span>
          {used} / {unlimited ? "∞" : limit}
        </span>
      </div>
      {!unlimited && (
        <div className="h-1.5 bg-gray-100 rounded-full overflow-hidden">
          <div
            className={`h-full rounded-full transition-all ${p > 80 ? "bg-red-400" : "bg-blue-500"}`}
            style={{ width: `${p}%` }}
          />
        </div>
      )}
    </div>
  );
}
