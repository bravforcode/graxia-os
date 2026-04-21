import axios, { type AxiosRequestConfig } from 'axios'

const API_BASE_URL = (import.meta.env.VITE_API_BASE_URL || '/api/v1').replace(/\/+$/, '')

const client = axios.create({
  baseURL: API_BASE_URL,
  withCredentials: true,
  headers: {
    'Content-Type': 'application/json',
  },
})

const publicClient = axios.create({
  baseURL: API_BASE_URL,
  withCredentials: true,
  headers: {
    'Content-Type': 'application/json',
  },
})

export interface ListResponse<T> {
  total: number
  items: T[]
}

export interface User {
  id: string
  email: string
  full_name?: string
  role: string
  is_active: boolean
  created_at: string
}

export interface AuthResponse {
  access_token: string
  refresh_token: string
  token_type: string
  user: User
}

export interface Opportunity {
  id: string
  type: string
  title: string
  description?: string
  source_url?: string
  source_platform?: string
  deadline?: string
  total_score?: number
  scoring_rationale?: string
  red_flags?: string[]
  decision?: string
  decision_confidence?: number
  decision_reasoning?: string
  action_priority?: string
  status?: string
  prize_amount?: string
  tags?: string[]
  is_student_eligible?: boolean
  location_type?: string
  fit_summary?: string
  found_at?: string
  money_score?: number
  brand_score?: number
  network_score?: number
  startup_score?: number
  effort_score?: number
}

export interface Draft {
  id: string
  type?: string
  title?: string
  content: string
  status?: string
  context_notes?: string
  opportunity_id?: string
  contact_id?: string
  model_used?: string
  was_fallback_draft?: boolean
  created_at?: string
}

export interface ApprovalRequest {
  id: string
  title: string
  action_type: string
  subject_type?: string | null
  subject_id?: string | null
  status: string
  policy_class: string
  requested_by?: string | null
  batch_key?: string | null
  details?: Record<string, unknown> | null
  preview?: Record<string, unknown> | null
  expires_at?: string | null
  resolved_at?: string | null
  resolution_note?: string | null
  created_at?: string | null
}

export interface ApprovalDecisionResponse {
  id: string
  status: string
  batch_key?: string | null
}

export interface CognitiveState {
  id: string
  date: string
  energy: number
  stress: number
  available_hours_this_week: number
  exam_pressure?: number
  mood_note?: string
  created_at?: string
}

export interface WeeklyMetric {
  id: string
  week_start: string
  opps_found?: number
  opps_actioned?: number
  outreach_sent?: number
  reply_rate?: number
  proposals_won?: number
  revenue_thb?: number
  ai_cost_usd?: number
  avg_energy_this_week?: number
  created_at?: string
}

export interface Contact {
  id: string
  name: string
  role?: string
  company?: string
  contact_type?: string
  email?: string
  telegram_handle?: string
  linkedin_url?: string
  notes?: string
  relationship_strength?: number
  last_contacted_at?: string
  value_score?: number
  next_followup_date?: string
  followup_reason?: string
  updated_at?: string
  created_at?: string
}

export interface ContactStats {
  total: number
  leads: number
  with_email: number
  followup_due: number
  by_type: Record<string, number>
}

export interface SystemStatsHistoryItem {
  name: string
  date: string
  leads: number
  outreach: number
  success: number
  failed: number
}

export interface SystemStats {
  leads_scanned: number
  active_leads: number
  total_contacts: number
  opportunities_found: number
  ai_actions: number
  success_rate: number
  completed_24h: number
  failed_24h: number
  outreach_sent_24h: number
  active_ai_provider: string
  active_ai_model: string
  environment: string
  history: SystemStatsHistoryItem[]
}

export interface JobPosting {
  id: string
  title: string
  company?: string
  source_platform?: string
  source_url?: string
  location?: string
  job_type: string
  employment_type?: string
  description?: string
  required_skills?: string[]
  matched_skills?: string[]
  skill_gap_list?: string[]
  tags?: string[]
  match_score?: number
  fit_summary?: string
  status?: string
  follow_up_due?: string
  applied_at?: string
  last_scored_at?: string
  created_at?: string
  updated_at?: string
}

export interface EmailThread {
  id: string
  thread_id: string
  subject?: string
  participants: Array<{ email?: string; name?: string }>
  category?: string
  priority: number
  last_message_at?: string
  unread_count: number
  has_attachments: boolean
  action_items: Array<{ task: string }>
  status: string
  created_at: string
  updated_at: string
}

export interface AssistantTask {
  id: string
  title: string
  description?: string
  task_type?: string
  priority: number
  status: string
  due_date?: string
  related_entity_type?: string
  related_entity_id?: string
  assigned_to: string
  completed_at?: string
  created_at: string
  updated_at: string
}

export interface SystemHealth {
  status: string
  llm_degraded: boolean
  llm_cost_paused: boolean
  gemini_calls_today: number
  scraper_summary: {
    healthy: number
    total: number
  }
  readiness: {
    is_ready: boolean
    mode: string
    issues: string[]
    updated_at?: string | null
  }
  event_stats: Record<string, number>
}

export interface ScraperHealth {
  name: string
  status: string
  last_run_at: string | null
  time_since_run_seconds: number | null
  results_count: number
  error_message: string | null
  is_healthy: boolean
}

export interface JobStats {
  total_jobs: number
  by_status: Record<string, number>
  average_score: number
}

export interface EmailStats {
  total_threads: number
  unread_count: number
  action_items_count: number
  by_category: Record<string, number>
}

export interface TaskStats {
  total_tasks: number
  by_status: Record<string, number>
  overdue_count: number
  due_today_count: number
}

export interface BudgetWindow {
  cost_usd: number
  budget_usd: number
  percentage: number
}

export interface CostsSummary {
  today: BudgetWindow
  week: BudgetWindow
  month: BudgetWindow
}

export interface CostsUsage {
  period_days: number
  total_requests: number
  total_cost_usd: number
  avg_cost_per_request: number
  by_platform: Record<string, { requests: number; cost_usd: number }>
}

export interface CostsForecast {
  current_cost: number
  forecasted_cost: number
  daily_average: number
  days_elapsed: number
  days_remaining: number
  budget: number
  over_budget: boolean
}

export interface FailedEvent {
  index: number
  event: string
  payload: unknown
  error: string
}

export interface EventStats {
  total_events: number
  by_type: Record<string, number>
}

export interface EventBusHealth {
  status: string
  running: boolean
  queue_size: number
  total_events_processed: number
  failed_events: number
  event_types: number
}

function getCookieValue(name: string) {
  const target = `${name}=`
  return document.cookie
    .split(';')
    .map((part) => part.trim())
    .find((part) => part.startsWith(target))
    ?.slice(target.length) ?? null
}

export function getAccessToken() {
  return null
}

export function storeAuthTokens(accessToken: string, refreshToken: string) {
  void accessToken
  void refreshToken
}

export function clearAuthTokens() {
  return
}

let refreshPromise: Promise<boolean> | null = null

async function refreshAccessToken(): Promise<boolean> {
  if (!refreshPromise) {
    refreshPromise = publicClient
      .post('/auth/refresh')
      .then(() => true)
      .catch(() => {
        clearAuthTokens()
        return false
      })
      .finally(() => {
        refreshPromise = null
      })
  }

  return refreshPromise
}

client.interceptors.request.use((config) => {
  if (['post', 'put', 'patch', 'delete'].includes((config.method || '').toLowerCase())) {
    const csrfToken = getCookieValue('csrf_token')
    if (csrfToken) {
      config.headers['X-CSRF-Token'] = csrfToken
    }
  }
  return config
})

client.interceptors.response.use(
  (response) => response,
  async (error) => {
    const originalRequest = error.config as AxiosRequestConfig & { _retry?: boolean }
    const status = error.response?.status as number | undefined
    const isAuthRoute = typeof originalRequest?.url === 'string' && originalRequest.url.includes('/auth/')

    if (status === 401 && !originalRequest?._retry && !isAuthRoute) {
      originalRequest._retry = true
      const refreshed = await refreshAccessToken()
      if (refreshed) {
        return client(originalRequest)
      }
    }

    if (status === 401) {
      clearAuthTokens()
      if (window.location.pathname !== '/login') {
        window.location.href = '/login'
      }
    }

    return Promise.reject(error)
  }
)

async function loginRequest(email: string, password: string): Promise<AuthResponse> {
  const formData = new URLSearchParams()
  formData.set('username', email)
  formData.set('password', password)
  const { data } = await publicClient.post<AuthResponse>('/auth/login', formData, {
    headers: {
      'Content-Type': 'application/x-www-form-urlencoded',
    },
  })
  return data
}

async function registerRequest(email: string, password: string, fullName?: string): Promise<AuthResponse> {
  const { data } = await publicClient.post<AuthResponse>('/auth/register', {
    email,
    password,
    full_name: fullName,
  })
  return data
}

async function getCurrentUser(): Promise<User> {
  const { data } = await client.get<User>('/auth/me')
  return data
}

async function logoutRequest() {
  const { data } = await publicClient.post('/auth/logout')
  return data
}

export const api = {
  loginRequest,
  registerRequest,
  getCurrentUser,
  logoutRequest,

  getHealth: async (): Promise<SystemHealth> => {
    const { data } = await client.get<SystemHealth>('/system/health')
    return data
  },

  getSystemStats: async (): Promise<SystemStats> => {
    const { data } = await client.get<SystemStats>('/system/stats')
    return data
  },

  getScraperHealth: async (): Promise<{ total_scrapers: number; healthy: number; unhealthy: number; scrapers: ScraperHealth[] }> => {
    const { data } = await client.get('/scrapers/health')
    return data
  },

  triggerScan: async () => {
    const { data } = await client.post('/system/scan/now')
    return data
  },

  triggerBrief: async () => {
    const { data } = await client.post('/system/brief/now')
    return data
  },

  getOpportunities: async (params?: {
    status?: string
    decision?: string
    action_priority?: string
    limit?: number
    offset?: number
  }): Promise<ListResponse<Opportunity>> => {
    const { data } = await client.get('/opportunities', { params })
    return data
  },

  getOpportunity: async (id: string): Promise<Opportunity> => {
    const { data } = await client.get(`/opportunities/${id}`)
    return data
  },

  approveOpportunity: async (id: string) => {
    const { data } = await client.patch(`/opportunities/${id}/approve`)
    return data
  },

  skipOpportunity: async (id: string) => {
    const { data } = await client.patch(`/opportunities/${id}/skip`)
    return data
  },

  getDrafts: async (status = 'pending'): Promise<ListResponse<Draft>> => {
    const { data } = await client.get('/drafts', { params: { status } })
    return data
  },

  getDraft: async (id: string): Promise<Draft> => {
    const { data } = await client.get(`/drafts/${id}`)
    return data
  },

  approveDraft: async (id: string) => {
    const { data } = await client.patch(`/drafts/${id}/approve`)
    return data
  },

  rejectDraft: async (id: string, reason?: string) => {
    const { data } = await client.patch(`/drafts/${id}/reject`, { reason: reason ?? '' })
    return data
  },

  getApprovals: async (params?: {
    status?: string
    batch_key?: string
    limit?: number
    offset?: number
  }): Promise<ListResponse<ApprovalRequest>> => {
    const { data } = await client.get('/approvals', { params })
    return data
  },

  approveApproval: async (id: string, note?: string): Promise<ApprovalDecisionResponse> => {
    const { data } = await client.patch(`/approvals/${id}/approve`, null, {
      params: note ? { note } : undefined,
    })
    return data
  },

  rejectApproval: async (id: string, note?: string): Promise<ApprovalDecisionResponse> => {
    const { data } = await client.patch(`/approvals/${id}/reject`, null, {
      params: note ? { note } : undefined,
    })
    return data
  },

  getCognitiveToday: async (): Promise<CognitiveState> => {
    const { data } = await client.get('/cognitive/today')
    return data
  },

  checkin: async (state: {
    energy: number
    stress: number
    available_hours_this_week: number
    exam_pressure?: number
    mood_note?: string
  }): Promise<CognitiveState> => {
    const { data } = await client.post('/cognitive/checkin', state)
    return data
  },

  getMetrics: async (limit = 12): Promise<WeeklyMetric[]> => {
    const { data } = await client.get('/metrics', { params: { limit } })
    return data
  },

  getContacts: async (params?: {
    q?: string
    contact_type?: string
    min_value_score?: number
    followup_due_only?: boolean
    limit?: number
    offset?: number
  }): Promise<ListResponse<Contact>> => {
    const { data } = await client.get('/contacts', { params })
    return data
  },

  getContactStats: async (): Promise<ContactStats> => {
    const { data } = await client.get('/contacts/stats')
    return data
  },

  createContact: async (contact: Partial<Contact>): Promise<Contact> => {
    const { data } = await client.post('/contacts', contact)
    return data
  },

  updateContact: async (contactId: string, contact: Partial<Contact>): Promise<Contact> => {
    const { data } = await client.patch(`/contacts/${contactId}`, contact)
    return data
  },

  deleteContact: async (contactId: string) => {
    const { data } = await client.delete(`/contacts/${contactId}`)
    return data
  },

  getJobs: async (params?: {
    status?: string
    source_platform?: string
    job_type?: string
    min_score?: number
    limit?: number
    offset?: number
  }): Promise<ListResponse<JobPosting>> => {
    const { data } = await client.get('/jobs', { params })
    return data
  },

  getJobStats: async (): Promise<JobStats> => {
    const { data } = await client.get('/jobs/stats')
    return data
  },

  getEmailThreads: async (params?: {
    category?: string
    status?: string
    unread_only?: boolean
    limit?: number
    offset?: number
  }): Promise<ListResponse<EmailThread>> => {
    const { data } = await client.get('/email-threads', { params })
    return data
  },

  getEmailStats: async (): Promise<EmailStats> => {
    const { data } = await client.get('/email-threads/stats')
    return data
  },

  markThreadRead: async (threadId: string) => {
    const { data } = await client.patch(`/email-threads/${threadId}/mark-read`)
    return data
  },

  getTasks: async (params?: {
    status?: string
    priority_min?: number
    task_type?: string
    limit?: number
    offset?: number
  }): Promise<ListResponse<AssistantTask>> => {
    const { data } = await client.get('/tasks', { params })
    return data
  },

  getTaskStats: async (): Promise<TaskStats> => {
    const { data } = await client.get('/tasks/stats')
    return data
  },

  updateTask: async (taskId: string, payload: Partial<AssistantTask>) => {
    const { data } = await client.patch(`/tasks/${taskId}`, payload)
    return data
  },

  completeTask: async (taskId: string) => {
    const { data } = await client.patch(`/tasks/${taskId}/complete`)
    return data
  },

  getCostsSummary: async (): Promise<CostsSummary> => {
    const { data } = await client.get('/costs/summary')
    return data
  },

  getCostsUsage: async (params?: { days?: number }): Promise<CostsUsage> => {
    const { data } = await client.get('/costs/usage', { params })
    return data
  },

  getCostsForecast: async (): Promise<CostsForecast> => {
    const { data } = await client.get('/costs/forecast')
    return data
  },

  getEventStats: async (): Promise<EventStats> => {
    const { data } = await client.get('/events/stats')
    return data
  },

  getFailedEvents: async (): Promise<{ total: number; events: FailedEvent[] }> => {
    const { data } = await client.get('/events/failed')
    return data
  },

  getEventHealth: async (): Promise<EventBusHealth> => {
    const { data } = await client.get('/events/health')
    return data
  },

  replayFailedEvent: async (index: number) => {
    const { data } = await client.post(`/events/replay/${index}`)
    return data
  },

  removeFailedEvent: async (index: number) => {
    const { data } = await client.delete(`/events/failed/${index}`)
    return data
  },

  clearFailedEvents: async () => {
    const { data } = await client.delete('/events/failed')
    return data
  },

  socialLogin: async (token: string, provider: string): Promise<AuthResponse> => {
    const { data } = await publicClient.post<AuthResponse>('/auth/social-login', {
      token,
      provider,
    })
    return data
  },
}

export default api
