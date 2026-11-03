/// <reference types="vite/client" />

interface ImportMetaEnv {
  readonly VITE_SITE_URL?: string;
  readonly VITE_BASE_PATH?: string;
  readonly VITE_PUBLIC_FUNNEL_API_BASE_URL?: string;
  readonly VITE_API_URL: string;
  readonly VITE_WS_URL: string;
  readonly VITE_AGENT_STREAM_URL: string;
  readonly VITE_SUPABASE_URL: string;
  readonly VITE_SUPABASE_ANON_KEY: string;
  // VITE_REVENUE_OS_API_KEY removed — API key must stay server-side (backend proxy)
}

interface ImportMeta {
  readonly env: ImportMetaEnv;
}
