import { client, publicClient } from "../lib/api";

// ── Types ─────────────────────────────────────────────────────────────────

export interface DigitalProduct {
  id: string;
  organization_id: string;
  name: string;
  slug: string;
  description?: string;
  short_description?: string;
  product_type: string;
  price_amount: number | string;
  currency: string;
  status: string;
  stripe_price_id?: string;
  stripe_product_id?: string;
  cover_image_url?: string;
  sales_page_content?: string;
  published_at?: string;
  created_at: string;
  updated_at: string;
}

export interface DeliveryAsset {
  id: string;
  product_id: string;
  organization_id: string;
  asset_type: string;
  title: string;
  description?: string;
  storage_path?: string;
  external_url?: string;
  content_body?: string;
  is_active: boolean;
  created_at: string;
  updated_at: string;
}

export interface LeadMagnet {
  id: string;
  organization_id: string;
  name: string;
  slug: string;
  target_product_id?: string;
  promise?: string;
  file_url?: string;
  landing_page_url?: string;
  status: string;
  opt_in_count: number;
  created_at: string;
  updated_at: string;
}

export interface FunnelCheckout {
  id: string;
  organization_id: string;
  product_id: string;
  status: string;
  stripe_session_id?: string;
  checkout_url?: string;
  amount: number | string;
  currency: string;
  customer_email?: string;
  created_at: string;
}

export interface FunnelAnalyticsSummary {
  views: number;
  unique_visitors: number;
  leads: number;
  checkout_starts: number;
  purchases: number;
  delivery_opened: number;
  lead_conversion_rate: number;
  checkout_rate: number;
  purchase_conversion_rate: number;
  checkout_to_purchase_rate: number;
  sales_count: number;
  total_revenue: number;
  average_order_value: number;
}

export interface FunnelDailyAnalytics {
  date: string;
  views: number;
  leads: number;
  purchases: number;
  revenue: number;
}

export interface DeliveryPayload {
  product_name: string;
  asset_title: string;
  asset_type: string;
  content_body?: string;
  external_url?: string;
  expires_at?: string;
  downloads_remaining?: number;
}

// ── API Wrapper ───────────────────────────────────────────────────────────

export const funnelApi = {
  // ── Digital Products (Admin) ───────────────────────────────────────────
  
  listProducts: async (params?: { include_archived?: boolean; limit?: number; offset?: number }): Promise<DigitalProduct[]> => {
    const { data } = await client.get<DigitalProduct[]>("/funnel/products", { params });
    return data;
  },

  getProduct: async (id: string): Promise<DigitalProduct> => {
    const { data } = await client.get<DigitalProduct>(`/funnel/products/${id}`);
    return data;
  },

  createProduct: async (payload: Partial<DigitalProduct>): Promise<DigitalProduct> => {
    const { data } = await client.post<DigitalProduct>("/funnel/products", payload);
    return data;
  },

  updateProduct: async (id: string, payload: Partial<DigitalProduct>): Promise<DigitalProduct> => {
    const { data } = await client.patch<DigitalProduct>(`/funnel/products/${id}`, payload);
    return data;
  },

  publishProduct: async (id: string): Promise<DigitalProduct> => {
    const { data } = await client.post<DigitalProduct>(`/funnel/products/${id}/publish`);
    return data;
  },

  archiveProduct: async (id: string): Promise<DigitalProduct> => {
    const { data } = await client.post<DigitalProduct>(`/funnel/products/${id}/archive`);
    return data;
  },

  deleteProduct: async (id: string): Promise<void> => {
    await client.delete(`/funnel/products/${id}`);
  },

  // ── Delivery Assets (Admin) ────────────────────────────────────────────

  listAssets: async (productId: string): Promise<DeliveryAsset[]> => {
    const { data } = await client.get<DeliveryAsset[]>(`/funnel/products/${productId}/assets`);
    return data;
  },

  getAsset: async (assetId: string): Promise<DeliveryAsset> => {
    const { data } = await client.get<DeliveryAsset>(`/funnel/assets/${assetId}`);
    return data;
  },

  createAsset: async (productId: string, payload: Partial<DeliveryAsset>): Promise<DeliveryAsset> => {
    const { data } = await client.post<DeliveryAsset>(`/funnel/products/${productId}/assets`, payload);
    return data;
  },

  updateAsset: async (assetId: string, payload: Partial<DeliveryAsset>): Promise<DeliveryAsset> => {
    const { data } = await client.patch<DeliveryAsset>(`/funnel/assets/${assetId}`, payload);
    return data;
  },

  deactivateAsset: async (assetId: string): Promise<DeliveryAsset> => {
    const { data } = await client.post<DeliveryAsset>(`/funnel/assets/${assetId}/deactivate`);
    return data;
  },

  // ── Checkout Sessions (Public / Customer) ──────────────────────────────

  createCheckoutSession: async (productId: string, payload: {
    customer_email?: string;
    success_url: string;
    cancel_url: string;
    metadata?: Record<string, any>;
  }): Promise<FunnelCheckout> => {
    const { data } = await client.post<FunnelCheckout>(`/funnel/products/${productId}/checkout`, payload);
    return data;
  },

  getPublicProduct: async (organizationId: string, slug: string): Promise<DigitalProduct> => {
    const { data } = await publicClient.get<DigitalProduct>(`/funnel/public/products/${organizationId}/${slug}`);
    return data;
  },

  createPublicCheckoutSession: async (productId: string, payload: {
    organization_id: string;
    customer_email?: string;
    success_url: string;
    cancel_url: string;
    metadata?: Record<string, any>;
  }): Promise<FunnelCheckout> => {
    const { data } = await publicClient.post<FunnelCheckout>(`/funnel/public/products/${productId}/checkout`, payload);
    return data;
  },

  // ── Lead Magnets (Admin & Public) ──────────────────────────────────────

  listLeadMagnets: async (): Promise<LeadMagnet[]> => {
    const { data } = await client.get<LeadMagnet[]>("/funnel/lead-magnets");
    return data;
  },

  getLeadMagnet: async (id: string): Promise<LeadMagnet> => {
    const { data } = await client.get<LeadMagnet>(`/funnel/lead-magnets/${id}`);
    return data;
  },

  createLeadMagnet: async (payload: Partial<LeadMagnet>): Promise<LeadMagnet> => {
    const { data } = await client.post<LeadMagnet>("/funnel/lead-magnets", payload);
    return data;
  },

  updateLeadMagnet: async (id: string, payload: Partial<LeadMagnet>): Promise<LeadMagnet> => {
    const { data } = await client.put<LeadMagnet>(`/funnel/lead-magnets/${id}`, payload);
    return data;
  },

  deleteLeadMagnet: async (id: string): Promise<void> => {
    await client.delete(`/funnel/lead-magnets/${id}`);
  },

  // Public Lead Capture
  captureLead: async (slug: string, payload: {
    organization_id: string;
    email: string;
    name?: string;
    source?: string;
    medium?: string;
    campaign?: string;
    referrer?: string;
  }): Promise<{ contact_id: string; raw_token?: string; delivery_url?: string }> => {
    const { data } = await publicClient.post(`/public/funnel/lead-magnets/${slug}/capture`, payload);
    return data;
  },

  // ── Public Delivery Access ─────────────────────────────────────────────

  getDeliveryPayload: async (token: string): Promise<DeliveryPayload> => {
    const { data } = await publicClient.get<DeliveryPayload>(`/funnel/delivery/${token}`);
    return data;
  },

  consumeDeliveryPayload: async (token: string): Promise<DeliveryPayload> => {
    const { data } = await publicClient.post<DeliveryPayload>(`/funnel/delivery/${token}/consume`);
    return data;
  },

  // ── Analytics (Admin) ──────────────────────────────────────────────────

  getAnalyticsSummary: async (params?: {
    product_id?: string;
    start_date?: string;
    end_date?: string;
  }): Promise<FunnelAnalyticsSummary> => {
    const { data } = await client.get<FunnelAnalyticsSummary>("/funnel/analytics/summary", { params });
    return data;
  },

  getDailyAnalytics: async (params?: {
    start_date?: string;
    end_date?: string;
  }): Promise<FunnelDailyAnalytics[]> => {
    const { data } = await client.get<FunnelDailyAnalytics[]>("/funnel/analytics/daily", { params });
    return data;
  },

  // Public Event Logging
  logPublicEvent: async (payload: {
    organization_id: string;
    event_type: string;
    product_id?: string;
    contact_id?: string;
    order_id?: string;
    session_id?: string;
    source?: string;
    medium?: string;
    campaign?: string;
    referrer?: string;
    metadata_json?: Record<string, any>;
  }): Promise<void> => {
    await publicClient.post("/funnel/events", payload);
  },
};
