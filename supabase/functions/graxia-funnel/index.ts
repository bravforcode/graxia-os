import "jsr:@supabase/functions-js/edge-runtime.d.ts";

type JsonObject = Record<string, unknown>;

const SUPABASE_URL = Deno.env.get("SUPABASE_URL") ?? "";
const SUPABASE_SERVICE_ROLE_KEY =
  Deno.env.get("SUPABASE_SERVICE_ROLE_KEY") ??
  (() => {
    try {
      return JSON.parse(Deno.env.get("SUPABASE_SECRET_KEYS") ?? "{}").default ?? "";
    } catch {
      return "";
    }
  })();
const STRIPE_SECRET_KEY = Deno.env.get("STRIPE_SECRET_KEY") ?? "";
const STRIPE_WEBHOOK_SECRET = Deno.env.get("STRIPE_WEBHOOK_SECRET") ?? "";
const PUBLIC_ORG_ID = Deno.env.get("PUBLIC_FUNNEL_ORGANIZATION_ID") ?? "";
const FRONTEND_URL =
  Deno.env.get("FRONTEND_URL") ??
  "https://bravforcode.github.io/graxia";
const FRONTEND_ORIGIN = new URL(FRONTEND_URL).origin;
const encoder = new TextEncoder();

class HttpError extends Error {
  constructor(
    public readonly status: number,
    message: string,
  ) {
    super(message);
  }
}

const corsHeaders = {
  "Access-Control-Allow-Origin": FRONTEND_ORIGIN,
  "Access-Control-Allow-Headers":
    "authorization, x-client-info, apikey, content-type, stripe-signature",
  "Access-Control-Allow-Methods": "GET, POST, OPTIONS",
  Vary: "Origin",
};

function response(body: unknown, status = 200, headers: HeadersInit = {}) {
  return new Response(JSON.stringify(body), {
    status,
    headers: {
      ...corsHeaders,
      "Content-Type": "application/json",
      ...headers,
    },
  });
}

function requireConfig() {
  if (!SUPABASE_URL || !SUPABASE_SERVICE_ROLE_KEY) {
    throw new HttpError(503, "Public funnel runtime is not configured");
  }
  if (!PUBLIC_ORG_ID) {
    throw new HttpError(503, "Public funnel tenant is not configured");
  }
}

function requireStripeConfig() {
  requireConfig();
  if (!STRIPE_SECRET_KEY) throw new HttpError(503, "Stripe is not configured");
}

function adminHeaders(): Record<string, string> {
  const headers: Record<string, string> = {
    apikey: SUPABASE_SERVICE_ROLE_KEY,
    "Content-Type": "application/json",
  };
  if (Deno.env.get("SUPABASE_SERVICE_ROLE_KEY")) {
    headers.Authorization = `Bearer ${SUPABASE_SERVICE_ROLE_KEY}`;
  }
  return headers;
}

async function supabaseRequest(
  path: string,
  init: RequestInit = {},
): Promise<unknown> {
  const res = await fetch(`${SUPABASE_URL}/rest/v1/${path}`, {
    ...init,
    headers: {
      ...adminHeaders(),
      ...(init.headers as Record<string, string> | undefined),
    },
  });
  const text = await res.text();
  let data: unknown = null;
  try {
    data = text ? JSON.parse(text) : null;
  } catch {
    data = text;
  }
  if (!res.ok) {
    throw new Error(`Supabase ${res.status}: ${text.slice(0, 300)}`);
  }
  return data;
}

async function stripeRequest(
  path: string,
  init: RequestInit = {},
): Promise<JsonObject> {
  if (!STRIPE_SECRET_KEY) throw new HttpError(503, "Stripe is not configured");
  const res = await fetch(`https://api.stripe.com${path}`, {
    ...init,
    headers: {
      Authorization: `Bearer ${STRIPE_SECRET_KEY}`,
      ...(init.headers as Record<string, string> | undefined),
    },
  });
  const text = await res.text();
  let data: JsonObject = {};
  try {
    data = text ? JSON.parse(text) : {};
  } catch {
    data = { error: { message: text.slice(0, 300) } };
  }
  if (!res.ok) {
    throw new Error(`Stripe ${res.status}: ${text.slice(0, 300)}`);
  }
  return data;
}

function requireOrganization(value: unknown): string {
  if (typeof value !== "string" || value !== PUBLIC_ORG_ID) {
    throw new HttpError(404, "Public funnel tenant not found");
  }
  return PUBLIC_ORG_ID;
}

function safeMetadata(value: unknown): Record<string, string> {
  const allowed = new Set([
    "source",
    "medium",
    "campaign",
    "referrer",
    "session_id",
    "content_id",
    "cta",
    "channel",
    "locale",
    "landing_path",
    "referral_code",
    "first_touch",
    "last_touch",
    "lead_magnet_id",
    "lead_magnet_slug",
    "delivery_access_id",
  ]);
  const result: Record<string, string> = {};
  if (!value || typeof value !== "object") return result;
  for (const [key, raw] of Object.entries(value as JsonObject)) {
    if (!allowed.has(key) || raw == null) continue;
    const serialized =
      typeof raw === "object" ? JSON.stringify(raw) : String(raw);
    if (serialized.length > 200) continue;
    result[key] = serialized;
  }
  return result;
}

function safeReturnUrl(value: unknown, fallbackPath: string): string {
  const fallback = frontendUrl(fallbackPath);
  const candidate = typeof value === "string" && value.trim() ? value : fallback;
  let parsed: URL;
  try {
    parsed = new URL(candidate);
  } catch {
    throw new HttpError(400, "Invalid return URL");
  }
  if (parsed.origin !== FRONTEND_ORIGIN) {
    throw new HttpError(400, "Return URL is not allowlisted");
  }
  return parsed.toString();
}

function frontendUrl(path: string): string {
  const base = FRONTEND_URL.replace(/\/+$/, "");
  return `${base}/${path.replace(/^\/+/, "")}`;
}

function validEmail(value: unknown): string {
  const email = typeof value === "string" ? value.trim().toLowerCase() : "";
  if (email.length > 320 || !/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email)) {
    throw new HttpError(400, "Invalid email");
  }
  return email;
}

function boundedString(value: unknown, max = 200): string {
  return typeof value === "string" ? value.trim().slice(0, max) : "";
}

async function digestText(value: string): Promise<string> {
  return hex(await crypto.subtle.digest("SHA-256", encoder.encode(value)));
}

async function opaqueDeliveryToken(reference: string): Promise<string> {
  return digestText(`graxia-delivery:${SUPABASE_SERVICE_ROLE_KEY}:${reference}`);
}

function productQuery(filters: string): Promise<unknown> {
  return supabaseRequest(
    `digital_products?select=id,name,short_description,price_amount,currency,stripe_price_id&${filters}`,
  );
}

async function createCheckout(productId: string, body: JsonObject) {
  const organizationId = requireOrganization(body.organization_id);
  const customerEmail =
    typeof body.customer_email === "string" ? body.customer_email.trim() : "";
  if (customerEmail && (customerEmail.length > 320 || !customerEmail.includes("@"))) {
    throw new HttpError(400, "Invalid customer email");
  }

  const products = (await productQuery(
    [
      `organization_id=eq.${encodeURIComponent(organizationId)}`,
      `id=eq.${encodeURIComponent(productId)}`,
      "status=eq.published",
      "is_deleted=eq.false",
    ].join("&"),
  )) as JsonObject[];
  const product = products[0];
  if (!product || typeof product.stripe_price_id !== "string") {
    throw new HttpError(404, "Product not found or payment is not configured");
  }

  const checkoutId = crypto.randomUUID();
  const metadata = safeMetadata(body.metadata);
  const expiresAt = new Date(Date.now() + 24 * 60 * 60 * 1000).toISOString();
  await supabaseRequest("funnel_checkout_sessions", {
    method: "POST",
    headers: { Prefer: "return=minimal" },
    body: JSON.stringify({
      id: checkoutId,
      organization_id: organizationId,
      product_id: product.id,
      status: "created",
      amount: Number(product.price_amount),
      currency: product.currency,
      customer_email: customerEmail || null,
      metadata_json: metadata,
      expires_at: expiresAt,
    }),
  });

  const successUrl = safeReturnUrl(
    body.success_url,
    "/checkout/success?session_id={CHECKOUT_SESSION_ID}",
  );
  const cancelUrl = safeReturnUrl(body.cancel_url, "/store");
  const stripeBody = new URLSearchParams();
  stripeBody.set("mode", "payment");
  stripeBody.set("line_items[0][price]", product.stripe_price_id);
  stripeBody.set("line_items[0][quantity]", "1");
  stripeBody.set("success_url", successUrl);
  stripeBody.set("cancel_url", cancelUrl);
  if (customerEmail) stripeBody.set("customer_email", customerEmail);
  stripeBody.set("client_reference_id", checkoutId);
  stripeBody.set("metadata[organization_id]", organizationId);
  stripeBody.set("metadata[product_id]", String(product.id));
  stripeBody.set("metadata[funnel_checkout_session_id]", checkoutId);
  for (const [key, value] of Object.entries(metadata)) {
    stripeBody.set(`metadata[${key}]`, value);
  }

  try {
    const stripeSession = await stripeRequest("/v1/checkout/sessions", {
      method: "POST",
      headers: { "Content-Type": "application/x-www-form-urlencoded" },
      body: stripeBody.toString(),
    });
    await supabaseRequest(
      `funnel_checkout_sessions?id=eq.${encodeURIComponent(checkoutId)}`,
      {
        method: "PATCH",
        headers: { Prefer: "return=minimal" },
        body: JSON.stringify({
          stripe_session_id: stripeSession.id,
          status: "pending",
        }),
      },
    );
    return {
      id: checkoutId,
      organization_id: organizationId,
      product_id: product.id,
      stripe_session_id: stripeSession.id,
      checkout_url: stripeSession.url,
      status: "pending",
      amount: product.price_amount,
      currency: product.currency,
      created_at: new Date().toISOString(),
    };
  } catch (error) {
    await supabaseRequest(
      `funnel_checkout_sessions?id=eq.${encodeURIComponent(checkoutId)}`,
      {
        method: "PATCH",
        headers: { Prefer: "return=minimal" },
        body: JSON.stringify({ status: "failed" }),
      },
    ).catch(() => undefined);
    throw error;
  }
}

function hex(bytes: ArrayBuffer): string {
  return [...new Uint8Array(bytes)]
    .map((value) => value.toString(16).padStart(2, "0"))
    .join("");
}

function constantTimeEqual(left: string, right: string): boolean {
  if (left.length !== right.length) return false;
  let result = 0;
  for (let index = 0; index < left.length; index += 1) {
    result |= left.charCodeAt(index) ^ right.charCodeAt(index);
  }
  return result === 0;
}

async function verifyStripeSignature(rawBody: string, signature: string) {
  if (!STRIPE_WEBHOOK_SECRET || !signature) {
    throw new HttpError(400, "Webhook signature is not configured");
  }
  const parts = Object.fromEntries(
    signature.split(",").map((part) => {
      const [key, value] = part.split("=", 2);
      return [key, value];
    }),
  );
  const timestamp = Number(parts.t);
  if (!Number.isFinite(timestamp) || Math.abs(Date.now() / 1000 - timestamp) > 300) {
    throw new HttpError(400, "Webhook timestamp outside tolerance");
  }
  const key = await crypto.subtle.importKey(
    "raw",
    encoder.encode(STRIPE_WEBHOOK_SECRET),
    { name: "HMAC", hash: "SHA-256" },
    false,
    ["sign"],
  );
  const digest = hex(
    await crypto.subtle.sign("HMAC", key, encoder.encode(`${timestamp}.${rawBody}`)),
  );
  const signatures = signature
    .split(",")
    .filter((part) => part.startsWith("v1="))
    .map((part) => part.slice(3));
  if (!signatures.some((value) => constantTimeEqual(value, digest))) {
    throw new HttpError(400, "Invalid webhook signature");
  }
}

function readTouch(metadata: JsonObject | null, key: string) {
  const raw = metadata?.[key];
  if (typeof raw !== "string") return {};
  try {
    const parsed = JSON.parse(raw);
    return parsed && typeof parsed === "object" ? parsed : {};
  } catch {
    return {};
  }
}

async function recordConversion(
  eventType: string,
  organizationId: string,
  orderId: string | null,
  productId: string | null,
  sessionId: string,
  metadata: JsonObject | null,
  idempotencyKey: string,
) {
  const safe = safeMetadata(metadata);
  const first = readTouch(safe, "first_touch") as JsonObject;
  const last = readTouch(safe, "last_touch") as JsonObject;
  await supabaseRequest("conversion_events", {
    method: "POST",
    headers: { Prefer: "return=minimal" },
    body: JSON.stringify({
      id: crypto.randomUUID(),
      organization_id: organizationId,
      event_type: eventType,
      product_id: productId,
      order_id: orderId,
      session_id: sessionId,
      source: safe.source ?? null,
      medium: safe.medium ?? null,
      campaign: safe.campaign ?? null,
      referrer: safe.referrer ?? null,
      metadata_json: safe,
      occurred_at: new Date().toISOString(),
      idempotency_key: idempotencyKey,
      first_touch_source: first.source ?? null,
      first_touch_medium: first.medium ?? null,
      first_touch_campaign: first.campaign ?? null,
      first_touch_referrer: first.referrer ?? null,
      first_touch_path: first.path ?? null,
      last_touch_source: last.source ?? null,
      last_touch_medium: last.medium ?? null,
      last_touch_campaign: last.campaign ?? null,
      last_touch_referrer: last.referrer ?? null,
      last_touch_path: last.path ?? null,
      landing_path: safe.landing_path ?? null,
      content_id: safe.content_id ?? null,
      referral_code: safe.referral_code ?? null,
    }),
  }).catch((error) => {
    if (!String(error).includes("duplicate") && !String(error).includes("409")) {
      throw error;
    }
  });
}

async function logPublicEvent(body: JsonObject) {
  const organizationId = requireOrganization(body.organization_id);
  const allowedEvents = new Set([
    "page_view",
    "lead_capture",
    "checkout_start",
    "checkout_success",
    "purchase",
    "delivery_opened",
  ]);
  const eventType = String(body.event_type ?? "");
  if (!allowedEvents.has(eventType)) {
    throw new HttpError(400, "Unsupported event type");
  }
  const productId =
    typeof body.product_id === "string" ? body.product_id : null;
  if (productId) {
    const products = (await productQuery(
      `organization_id=eq.${encodeURIComponent(organizationId)}&id=eq.${encodeURIComponent(productId)}&select=id`,
    )) as JsonObject[];
    if (!products[0]) throw new HttpError(404, "Product not found");
  }
  const metadata = safeMetadata({
    ...(body.metadata_json as JsonObject | undefined),
    source: body.source,
    medium: body.medium,
    campaign: body.campaign,
    referrer: body.referrer,
    first_touch: body.first_touch,
    last_touch: body.last_touch,
    landing_path: body.landing_path,
    content_id: body.content_id,
    referral_code: body.referral_code,
  });
  const requestedKey =
    typeof body.idempotency_key === "string" ? body.idempotency_key : "";
  const idempotencyKey =
    requestedKey.length > 0 && requestedKey.length <= 200
      ? `public:${organizationId}:${requestedKey}`
      : `public:${organizationId}:${eventType}:${boundedString(body.session_id)}:${productId ?? ""}:${metadata.content_id ?? ""}:${metadata.landing_path ?? ""}`;
  await recordConversion(
    eventType,
    organizationId,
    null,
    productId,
    typeof body.session_id === "string" ? body.session_id.slice(0, 200) : "",
    metadata,
    idempotencyKey,
  );
  return { accepted: true };
}

async function captureLead(slug: string, body: JsonObject) {
  const organizationId = requireOrganization(body.organization_id);
  const email = validEmail(body.email);
  const name = boundedString(body.name, 300);
  const sessionId = boundedString(body.session_id);
  const marketingConsent = body.marketing_consent === true;
  const consentVersion = boundedString(body.consent_version, 100);
  if (marketingConsent && !consentVersion) {
    throw new HttpError(400, "consent_version is required when marketing_consent is true");
  }

  const magnets = (await supabaseRequest(
    `funnel_lead_magnets?organization_id=eq.${encodeURIComponent(organizationId)}&slug=eq.${encodeURIComponent(slug)}&status=eq.published&select=*&limit=1`,
  )) as JsonObject[];
  const magnet = magnets[0];
  if (!magnet) throw new HttpError(404, "Lead magnet not found");

  const contacts = (await supabaseRequest(
    `contacts?organization_id=eq.${encodeURIComponent(organizationId)}&email=eq.${encodeURIComponent(email)}&is_deleted=eq.false&select=id,marketing_consent,marketing_unsubscribed&limit=1`,
  )) as JsonObject[];
  let contact = contacts[0];
  if (!contact?.id) {
    const created = (await supabaseRequest("contacts", {
      method: "POST",
      headers: { Prefer: "return=representation" },
      body: JSON.stringify({
        id: crypto.randomUUID(),
        organization_id: organizationId,
        name: name || email.split("@")[0],
        email,
        contact_type: "lead",
        relationship_strength: 1,
        marketing_consent: marketingConsent,
        marketing_consent_at: marketingConsent ? new Date().toISOString() : null,
        consent_version: marketingConsent ? consentVersion : null,
        marketing_unsubscribed: false,
      }),
    })) as JsonObject[];
    contact = created[0];
  } else if (marketingConsent) {
    await supabaseRequest(
      `contacts?id=eq.${encodeURIComponent(String(contact.id))}&organization_id=eq.${encodeURIComponent(organizationId)}`,
      {
        method: "PATCH",
        headers: { Prefer: "return=minimal" },
        body: JSON.stringify({
          marketing_consent: true,
          marketing_consent_at: new Date().toISOString(),
          consent_version: consentVersion,
          marketing_unsubscribed: false,
          marketing_unsubscribed_at: null,
        }),
      },
    );
  }
  if (!contact?.id) throw new HttpError(503, "Lead capture contact could not be created");

  const captureDigest = await digestText(
    `${organizationId}:${slug}:${email}:${sessionId || "email"}`,
  );
  const attribution = safeMetadata({
    source: body.source,
    medium: body.medium,
    campaign: body.campaign,
    referrer: body.referrer,
    session_id: sessionId,
    channel: "lead_magnet",
    lead_magnet_id: magnet.id,
    lead_magnet_slug: slug,
    referral_code: body.referral_code,
  });
  await recordConversion(
    "lead_capture",
    organizationId,
    null,
    typeof magnet.target_product_id === "string" ? magnet.target_product_id : null,
    sessionId,
    attribution,
    `lead_capture:${captureDigest}`,
  );

  const currentCount = Number(magnet.opt_in_count ?? 0);
  await supabaseRequest(
    `funnel_lead_magnets?id=eq.${encodeURIComponent(String(magnet.id))}&organization_id=eq.${encodeURIComponent(organizationId)}`,
    {
      method: "PATCH",
      headers: { Prefer: "return=minimal" },
      body: JSON.stringify({ opt_in_count: currentCount + 1 }),
    },
  ).catch(() => undefined);

  const targetProductId = typeof magnet.target_product_id === "string"
    ? magnet.target_product_id
    : "";
  if (!targetProductId) return { contact_id: contact.id };
  const products = (await supabaseRequest(
    `digital_products?organization_id=eq.${encodeURIComponent(organizationId)}&id=eq.${encodeURIComponent(targetProductId)}&status=eq.published&is_deleted=eq.false&select=id,currency&limit=1`,
  )) as JsonObject[];
  const product = products[0];
  if (!product) return { contact_id: contact.id };
  const assets = (await supabaseRequest(
    `delivery_assets?organization_id=eq.${encodeURIComponent(organizationId)}&product_id=eq.${encodeURIComponent(targetProductId)}&is_active=eq.true&select=id&limit=1`,
  )) as JsonObject[];
  const asset = assets[0];
  if (!asset?.id) return { contact_id: contact.id };

  const freeReference = `free:${captureDigest}`;
  const rawToken = await opaqueDeliveryToken(freeReference);
  const tokenHash = await digestText(rawToken);
  const existingOrders = (await supabaseRequest(
    `funnel_orders?organization_id=eq.${encodeURIComponent(organizationId)}&stripe_session_id=eq.${encodeURIComponent(freeReference)}&select=id&limit=1`,
  )) as JsonObject[];
  let order = existingOrders[0];
  if (!order?.id) {
    const inserted = (await supabaseRequest("funnel_orders", {
      method: "POST",
      headers: { Prefer: "resolution=ignore-duplicates,return=representation" },
      body: JSON.stringify({
        id: crypto.randomUUID(),
        organization_id: organizationId,
        contact_id: contact.id,
        stripe_session_id: freeReference,
        status: "paid",
        subtotal_amount: 0,
        total_amount: 0,
        currency: product.currency ?? "THB",
        customer_email: email,
        paid_at: new Date().toISOString(),
      }),
    })) as JsonObject[];
    order = inserted[0];
    if (!order?.id) {
      const retry = (await supabaseRequest(
        `funnel_orders?organization_id=eq.${encodeURIComponent(organizationId)}&stripe_session_id=eq.${encodeURIComponent(freeReference)}&select=id&limit=1`,
      )) as JsonObject[];
      order = retry[0];
    }
    if (order?.id && inserted[0]?.id) {
      await supabaseRequest("funnel_order_items", {
        method: "POST",
        headers: { Prefer: "resolution=ignore-duplicates,return=minimal" },
        body: JSON.stringify({
          id: crypto.randomUUID(),
          organization_id: organizationId,
          order_id: order.id,
          product_id: targetProductId,
          quantity: 1,
          unit_amount: 0,
          total_amount: 0,
          currency: product.currency ?? "THB",
        }),
      });
    }
  }
  if (!order?.id) throw new HttpError(503, "Lead delivery order could not be created");

  const accesses = (await supabaseRequest(
    `delivery_accesses?organization_id=eq.${encodeURIComponent(organizationId)}&order_id=eq.${encodeURIComponent(String(order.id))}&asset_id=eq.${encodeURIComponent(String(asset.id))}&select=id&limit=1`,
  )) as JsonObject[];
  if (!accesses[0]?.id) {
    await supabaseRequest("delivery_accesses", {
      method: "POST",
      headers: { Prefer: "resolution=ignore-duplicates,return=minimal" },
      body: JSON.stringify({
        id: crypto.randomUUID(),
        organization_id: organizationId,
        order_id: order.id,
        product_id: targetProductId,
        asset_id: asset.id,
        contact_id: contact.id,
        access_token_hash: tokenHash,
        status: "active",
        expires_at: new Date(Date.now() + 30 * 86400000).toISOString(),
        download_count: 0,
        max_downloads: 10,
      }),
    }).catch((error) => {
      if (!String(error).includes("duplicate") && !String(error).includes("409")) throw error;
    });
  }
  return {
    contact_id: contact.id,
    raw_token: rawToken,
    delivery_url: frontendUrl(`/delivery/${rawToken}`),
  };
}

async function getTokenDelivery(rawToken: string, consume: boolean) {
  if (!rawToken || rawToken.length > 256) throw new HttpError(400, "Invalid delivery token");
  const tokenHash = await digestText(rawToken);
  const accesses = (await supabaseRequest(
    `delivery_accesses?access_token_hash=eq.${encodeURIComponent(tokenHash)}&status=eq.active&select=*&limit=1`,
  )) as JsonObject[];
  const access = accesses[0];
  if (!access) throw new HttpError(404, "Delivery token not found");
  const organizationId = requireOrganization(access.organization_id);
  if (access.expires_at && new Date(String(access.expires_at)).getTime() <= Date.now()) {
    throw new HttpError(410, "Delivery token expired");
  }

  const orders = (await supabaseRequest(
    `funnel_orders?id=eq.${encodeURIComponent(String(access.order_id))}&organization_id=eq.${encodeURIComponent(organizationId)}&status=eq.paid&select=id,stripe_session_id&limit=1`,
  )) as JsonObject[];
  const order = orders[0];
  if (!order) throw new HttpError(402, "Payment is not verified");
  const stripeSessionId = String(order.stripe_session_id ?? "");
  if (stripeSessionId && !stripeSessionId.startsWith("free:")) {
    requireStripeConfig();
    const stripeSession = await stripeRequest(
      `/v1/checkout/sessions/${encodeURIComponent(stripeSessionId)}`,
    );
    if (stripeSession.payment_status !== "paid") {
      throw new HttpError(402, "Payment is not verified");
    }
  }

  const assets = (await supabaseRequest(
    `delivery_assets?id=eq.${encodeURIComponent(String(access.asset_id))}&organization_id=eq.${encodeURIComponent(organizationId)}&is_active=eq.true&select=*&limit=1`,
  )) as JsonObject[];
  const asset = assets[0];
  if (!asset || (!asset.content_body && !asset.external_url && !asset.storage_path)) {
    throw new HttpError(503, "Delivery asset is not ready");
  }

  let downloadCount = Number(access.download_count ?? 0);
  if (consume) {
    const maxDownloads = access.max_downloads == null ? null : Number(access.max_downloads);
    if (maxDownloads !== null && downloadCount >= maxDownloads) {
      throw new HttpError(410, "Download limit reached");
    }
    const now = new Date().toISOString();
    const updated = (await supabaseRequest(
      `delivery_accesses?id=eq.${encodeURIComponent(String(access.id))}&status=eq.active&download_count=eq.${downloadCount}`,
      {
        method: "PATCH",
        headers: { Prefer: "return=representation" },
        body: JSON.stringify({
          download_count: downloadCount + 1,
          first_accessed_at: access.first_accessed_at ?? now,
          last_accessed_at: now,
        }),
      },
    )) as JsonObject[];
    if (!updated[0]) throw new HttpError(409, "Delivery request already in progress");
    downloadCount += 1;
    await recordConversion(
      "delivery_opened",
      organizationId,
      String(order.id),
      String(access.product_id),
      String(order.id),
      { channel: "delivery", delivery_access_id: access.id },
      `delivery:${access.id}:${downloadCount}`,
    );
  }
  return {
    product_name: "Graxia product",
    asset_title: asset.title,
    asset_type: asset.asset_type,
    content_body: asset.content_body ?? undefined,
    external_url: asset.external_url ?? undefined,
    storage_path: asset.storage_path ?? undefined,
    expires_at: access.expires_at,
    downloads_remaining: access.max_downloads == null
      ? undefined
      : Math.max(0, Number(access.max_downloads) - downloadCount),
  };
}

async function completeCheckout(session: JsonObject, eventId: string) {
  const metadata = (session.metadata ?? {}) as JsonObject;
  const organizationId = requireOrganization(metadata.organization_id);
  const checkoutId = String(metadata.funnel_checkout_session_id ?? "");
  const productId = String(metadata.product_id ?? "");
  if (!checkoutId || !productId) return;

  const existingOrders = (await supabaseRequest(
    `funnel_orders?stripe_session_id=eq.${encodeURIComponent(String(session.id))}&select=id`,
  )) as JsonObject[];
  if (existingOrders[0]?.id) return;

  const checkouts = (await supabaseRequest(
    `funnel_checkout_sessions?id=eq.${encodeURIComponent(checkoutId)}&organization_id=eq.${encodeURIComponent(organizationId)}&select=*`,
  )) as JsonObject[];
  const checkout = checkouts[0];
  const products = (await productQuery(
    `organization_id=eq.${encodeURIComponent(organizationId)}&id=eq.${encodeURIComponent(productId)}`,
  )) as JsonObject[];
  const product = products[0];
  if (!checkout || !product) return;

  const orderId = crypto.randomUUID();
  const total = Number(product.price_amount);
  const email =
    ((session.customer_details as JsonObject | undefined)?.email as string | undefined) ??
    (checkout.customer_email as string | undefined) ??
    null;
  await supabaseRequest("funnel_orders", {
    method: "POST",
    headers: { Prefer: "return=minimal" },
    body: JSON.stringify({
      id: orderId,
      organization_id: organizationId,
      checkout_session_id: checkout.id,
      stripe_session_id: session.id,
      stripe_payment_intent_id: session.payment_intent ?? null,
      status: "paid",
      subtotal_amount: total,
      total_amount: total,
      currency: product.currency,
      customer_email: email,
      paid_at: new Date().toISOString(),
    }),
  });

  const orderItemId = crypto.randomUUID();
  await supabaseRequest("funnel_order_items", {
    method: "POST",
    headers: { Prefer: "return=minimal" },
    body: JSON.stringify({
      id: orderItemId,
      organization_id: organizationId,
      order_id: orderId,
      product_id: product.id,
      quantity: 1,
      unit_amount: total,
      total_amount: total,
      currency: product.currency,
    }),
  });

  const assets = (await supabaseRequest(
    `delivery_assets?organization_id=eq.${encodeURIComponent(organizationId)}&product_id=eq.${encodeURIComponent(product.id)}&is_active=eq.true&select=id&limit=1`,
  )) as JsonObject[];
  const asset = assets[0];
  if (asset?.id) {
    const tokenHash = await crypto.subtle.digest(
      "SHA-256",
      encoder.encode(`${session.id}:${product.id}`),
    );
    await supabaseRequest("delivery_accesses", {
      method: "POST",
      headers: { Prefer: "return=minimal" },
      body: JSON.stringify({
        id: crypto.randomUUID(),
        organization_id: organizationId,
        order_id: orderId,
        product_id: product.id,
        asset_id: asset.id,
        access_token_hash: hex(tokenHash),
        status: "active",
        expires_at: new Date(Date.now() + 30 * 86400000).toISOString(),
        download_count: 0,
        max_downloads: 10,
      }),
    });
  }

  await supabaseRequest(
    `funnel_checkout_sessions?id=eq.${encodeURIComponent(checkoutId)}`,
    {
      method: "PATCH",
      headers: { Prefer: "return=minimal" },
      body: JSON.stringify({
        status: "completed",
        completed_at: new Date().toISOString(),
      }),
    },
  );
  const checkoutMetadata = (checkout.metadata_json ?? metadata) as JsonObject;
  await recordConversion(
    "checkout_success",
    organizationId,
    orderId,
    product.id,
    String(session.id),
    checkoutMetadata,
    `stripe:${eventId}:checkout_success`,
  );
  await recordConversion(
    "purchase",
    organizationId,
    orderId,
    product.id,
    String(session.id),
    checkoutMetadata,
    `stripe:${eventId}:purchase`,
  );
}

async function handleWebhook(rawBody: string, signature: string) {
  await verifyStripeSignature(rawBody, signature);
  let event: JsonObject;
  try {
    event = JSON.parse(rawBody) as JsonObject;
  } catch {
    throw new HttpError(400, "Invalid webhook payload");
  }
  const type = String(event.type ?? "");
  const eventId = String(event.id ?? "");
  const object = ((event.data as JsonObject | undefined)?.object ?? {}) as JsonObject;
  if (type === "checkout.session.completed") {
    await completeCheckout(object, eventId);
  } else if (type === "checkout.session.expired") {
    const metadata = (object.metadata ?? {}) as JsonObject;
    const org = typeof metadata.organization_id === "string" ? metadata.organization_id : "";
    const checkoutId = typeof metadata.funnel_checkout_session_id === "string"
      ? metadata.funnel_checkout_session_id
      : "";
    if (org === PUBLIC_ORG_ID && checkoutId) {
      await supabaseRequest(
        `funnel_checkout_sessions?id=eq.${encodeURIComponent(checkoutId)}&organization_id=eq.${encodeURIComponent(org)}`,
        {
          method: "PATCH",
          headers: { Prefer: "return=minimal" },
          body: JSON.stringify({ status: "expired" }),
        },
      );
    }
  } else if (type === "charge.refunded") {
    const paymentIntent = String(object.payment_intent ?? "");
    if (paymentIntent) {
      const orders = (await supabaseRequest(
        `funnel_orders?stripe_payment_intent_id=eq.${encodeURIComponent(paymentIntent)}&select=id`,
      )) as JsonObject[];
      if (orders[0]?.id) {
        await supabaseRequest(
          `funnel_orders?id=eq.${encodeURIComponent(String(orders[0].id))}`,
          {
            method: "PATCH",
            headers: { Prefer: "return=minimal" },
            body: JSON.stringify({
              status: "refunded",
              refunded_at: new Date().toISOString(),
            }),
          },
        );
        await supabaseRequest(
          `delivery_accesses?order_id=eq.${encodeURIComponent(String(orders[0].id))}`,
          {
            method: "PATCH",
            headers: { Prefer: "return=minimal" },
            body: JSON.stringify({ status: "revoked" }),
          },
        );
      }
    }
  }
  return { received: true, event_type: type };
}

async function getDelivery(sessionId: string) {
  if (!sessionId || !STRIPE_SECRET_KEY) throw new HttpError(400, "Missing session");
  const stripeSession = await stripeRequest(
    `/v1/checkout/sessions/${encodeURIComponent(sessionId)}`,
  );
  if (stripeSession.payment_status !== "paid") {
    throw new HttpError(402, "Payment is not verified");
  }
  const orders = (await supabaseRequest(
    `funnel_orders?organization_id=eq.${encodeURIComponent(PUBLIC_ORG_ID)}&stripe_session_id=eq.${encodeURIComponent(sessionId)}&status=eq.paid&select=*&limit=1`,
  )) as JsonObject[];
  const order = orders[0];
  if (!order) throw new HttpError(404, "Verified order not found");
  const items = (await supabaseRequest(
    `funnel_order_items?order_id=eq.${encodeURIComponent(String(order.id))}&select=product_id&limit=1`,
  )) as JsonObject[];
  const productId = String(items[0]?.product_id ?? "");
  const products = (await productQuery(
    `organization_id=eq.${encodeURIComponent(String(order.organization_id))}&id=eq.${encodeURIComponent(productId)}`,
  )) as JsonObject[];
  const assets = (await supabaseRequest(
    `delivery_assets?organization_id=eq.${encodeURIComponent(String(order.organization_id))}&product_id=eq.${encodeURIComponent(productId)}&is_active=eq.true&select=*&limit=1`,
  )) as JsonObject[];
  const asset = assets[0];
  if (!asset || (!asset.content_body && !asset.external_url && !asset.storage_path)) {
    throw new HttpError(503, "Delivery asset is not ready");
  }
  await supabaseRequest(
    `delivery_accesses?order_id=eq.${encodeURIComponent(String(order.id))}`,
    {
      method: "PATCH",
      headers: { Prefer: "return=minimal" },
      body: JSON.stringify({
        first_accessed_at: new Date().toISOString(),
        last_accessed_at: new Date().toISOString(),
      }),
    },
  ).catch(() => undefined);
  return {
    product_name: products[0]?.name ?? "Graxia product",
    asset_title: asset.title,
    asset_type: asset.asset_type,
    content_body: asset.content_body ?? undefined,
    external_url: asset.external_url ?? undefined,
    storage_path: asset.storage_path ?? undefined,
    expires_at: new Date(Date.now() + 30 * 86400000).toISOString(),
  };
}

async function route(request: Request) {
  const url = new URL(request.url);
  const pathParts = url.pathname.split("/").filter(Boolean);
  const functionIndex = pathParts.indexOf("graxia-funnel");
  const path = functionIndex >= 0
    ? `/${pathParts.slice(functionIndex + 1).join("/")}` || "/"
    : url.pathname;
  if (request.method === "OPTIONS") return response({ ok: true });
  requireConfig();
  if (request.method === "GET" && path === "/health") {
    return response({ ok: true, service: "graxia-funnel", stripe: Boolean(STRIPE_SECRET_KEY) });
  }
  if (request.method === "GET" && path === "/delivery") {
    requireStripeConfig();
    return response(await getDelivery(url.searchParams.get("session_id") ?? ""));
  }
  if (request.method === "POST" && path === "/webhooks/stripe") {
    requireStripeConfig();
    return response(
      await handleWebhook(
        await request.text(),
        request.headers.get("stripe-signature") ?? "",
      ),
    );
  }
  if (request.method === "POST" && path === "/funnel/events") {
    return response(await logPublicEvent((await request.json()) as JsonObject));
  }
  const leadCaptureMatch = path.match(
    /^\/(?:funnel\/public|public\/funnel)\/lead-magnets\/([^/]+)\/capture$/,
  );
  if (request.method === "POST" && leadCaptureMatch) {
    return response(await captureLead(leadCaptureMatch[1], (await request.json()) as JsonObject), 201);
  }
  const deliveryTokenMatch = path.match(/^\/(?:funnel\/)?delivery\/([^/]+)$/);
  if (request.method === "GET" && deliveryTokenMatch) {
    return response(await getTokenDelivery(deliveryTokenMatch[1], false));
  }
  const consumeDeliveryMatch = path.match(/^\/(?:funnel\/)?delivery\/([^/]+)\/consume$/);
  if (request.method === "POST" && consumeDeliveryMatch) {
    return response(await getTokenDelivery(consumeDeliveryMatch[1], true));
  }
  const productMatch = path.match(
    /^\/funnel\/public\/products\/([^/]+)\/checkout$/,
  );
  if (request.method === "POST" && productMatch) {
    requireStripeConfig();
    const body = (await request.json()) as JsonObject;
    return response(await createCheckout(productMatch[1], body), 201);
  }
  const publicProductMatch = path.match(
    /^\/funnel\/public\/products\/([^/]+)\/([^/]+)$/,
  );
  if (request.method === "GET" && publicProductMatch) {
    const organizationId = requireOrganization(publicProductMatch[1]);
    const products = await productQuery(
      [
        `organization_id=eq.${encodeURIComponent(organizationId)}`,
        `slug=eq.${encodeURIComponent(publicProductMatch[2])}`,
        "status=eq.published",
        "is_deleted=eq.false",
      ].join("&"),
    );
    const product = (products as JsonObject[])[0];
    if (!product) throw new HttpError(404, "Product not found");
    return response(product);
  }
  throw new HttpError(404, "Route not found");
}

Deno.serve(async (request) => {
  try {
    return await route(request);
  } catch (error) {
    if (error instanceof HttpError) return response({ error: error.message }, error.status);
    console.error(error);
    return response({ error: "Payment runtime error" }, 500);
  }
});
