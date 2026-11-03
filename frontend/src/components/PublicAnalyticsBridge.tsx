import { useEffect } from "react";
import { useLocation } from "react-router-dom";
import { funnelApi } from "../api/funnel";
import { STORE_ORG_ID } from "../data/products";
import { captureAttribution, getAttributionEventFields } from "../lib/attribution";

const SKIP_PREFIXES = [
  "/app",
  "/login",
  "/register",
  "/checkout",
  "/delivery",
  "/f/",
];

export default function PublicAnalyticsBridge() {
  const location = useLocation();

  useEffect(() => {
    if (SKIP_PREFIXES.some((prefix) => location.pathname.startsWith(prefix))) return;

    const attribution = captureAttribution(window.location.href);
    const guideSlug = location.pathname.startsWith("/guides/")
      ? location.pathname.slice("/guides/".length).split("/")[0]
      : undefined;
    const eventFields = getAttributionEventFields({
      path: location.pathname,
      content_id: guideSlug,
    });
    const idempotencyKey = `page_view:${attribution.session_id}:${location.pathname}`;
    void funnelApi.logPublicEvent({
      organization_id: STORE_ORG_ID,
      event_type: "page_view",
      ...eventFields,
      idempotency_key: idempotencyKey,
    }).catch(() => {
      // Analytics must never block the public funnel.
    });
  }, [location.pathname, location.search]);

  return null;
}
