import { createClient, type SupabaseClient } from '@supabase/supabase-js'

const supabaseUrl = import.meta.env.VITE_SUPABASE_URL || ''
const supabaseAnonKey = import.meta.env.VITE_SUPABASE_ANON_KEY || ''

export const isSupabaseConfigured = Boolean(supabaseUrl && supabaseAnonKey)

const disabledSupabaseClient = {
  auth: {
    getSession: async () => ({ data: { session: null }, error: null }),
    signInWithOAuth: async () => ({
      data: null,
      error: new Error('Supabase OAuth is not configured.'),
    }),
  },
} as unknown as SupabaseClient

let _client: SupabaseClient | null = null

function getClient(): SupabaseClient {
  if (!_client) {
    _client = isSupabaseConfigured
      ? createClient(supabaseUrl, supabaseAnonKey)
      : disabledSupabaseClient
  }
  return _client
}

// Lazily initialize the Supabase client on first use so importing this module
// (e.g. via AuthContext -> App) does not eagerly create the client at load time.
// The Proxy preserves the exact public API: consumers still import `supabase`
// and call `.from()`, `.auth`, etc. directly.
export const supabase = new Proxy({} as SupabaseClient, {
  get(_t, prop, receiver) {
    const client = getClient()
    const value = Reflect.get(client, prop, receiver)
    return typeof value === 'function' ? value.bind(client) : value
  },
  set(_t, prop, value, receiver) {
    return Reflect.set(getClient(), prop, value, receiver)
  },
})
